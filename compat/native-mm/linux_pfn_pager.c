/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/proc.h>
#include <uvm/uvm.h>
#include <linux/fs_netbsd.h>
#include <linux/task_netbsd.h>
#include "linux_vma_internal.h"

static void
linux_pfn_reference(struct uvm_object *object)
{
	rw_enter(object->vmobjlock, RW_WRITER);
	if (__predict_false(object->uo_refs == UINT_MAX))
		panic("Linux PFN pager reference overflow");
	KASSERT(object->uo_refs != 0);
	object->uo_refs++;
	rw_exit(object->vmobjlock);
}

static void
linux_pfn_detach(struct uvm_object *object)
{
	bool last;
	rw_enter(object->vmobjlock, RW_WRITER);
	KASSERT(object->uo_refs != 0 && object->uo_npages == 0);
	last = --object->uo_refs == 0;
	rw_exit(object->vmobjlock);
	if (last) {
		uvm_obj_destroy(object, true);
		kmem_free(object, sizeof(*object));
	}
}

static int
linux_pfn_fault(struct uvm_faultinfo *ufi, vaddr_t start,
    struct vm_page **pages, int count, int center, vm_prot_t access, int flags)
{
	struct vm_map_entry *entry = ufi->entry;
	struct linux_vma_owner *owner = entry->uobj_private;
	struct uvm_object *object = entry->object.uvm_obj;
	struct vm_amap *amap = entry->aref.ar_amap;
	struct linux_vma_context context;
	struct task_struct *task = NULL;
	struct vm_fault fault;
	paddr_t physical;
	vm_fault_t result;
	int error;

	(void)start;
	(void)pages;
	KASSERT(flags & PGO_LOCKED);
	KASSERT(count == 1 && center == 0);
	KASSERT(owner != NULL && !owner->shmem);
	/* Device callbacks follow Linux's actual map-read lock contract, but
	 * must not run beneath Native amap/object locks. Source TTM receives
	 * RETRY_NOWAIT, so its retry branches retain this actual map lock. */
	rw_exit(object->vmobjlock);
	if (amap != NULL)
		amap_unlock(amap);
	if (UVM_ET_ISCOPYONWRITE(entry)) {
		/* Native anonymous COW requires real vm_pages; a GPU aperture PTE
		 * cannot be substituted with a fake anonymous allocation. */
		error = EOPNOTSUPP;
		goto unlock;
	}
	if (owner->vma.vm_ops == NULL || owner->vma.vm_ops->fault == NULL) {
		error = EFAULT;
		goto unlock;
	}
	error = linux_task_entry_enter(&task);
	if (error != 0)
		goto unlock;
	error = linux_vma_context_enter(owner, &context);
	if (error != 0)
		goto leave;
	memset(&fault, 0, sizeof(fault));
	fault.vma = &owner->vma; /* The durable published VMA, never stack-made. */
	fault.gfp_mask = GFP_KERNEL;
	fault.address = ufi->orig_rvaddr;
	fault.real_address = ufi->orig_rvaddr;
	fault.pgoff = owner->vma.vm_pgoff +
	    ((fault.address - owner->vma.vm_start) >> PAGE_SHIFT);
	fault.flags = FAULT_FLAG_ALLOW_RETRY | FAULT_FLAG_RETRY_NOWAIT;
	if (access & VM_PROT_WRITE)
		fault.flags |= FAULT_FLAG_WRITE;
	if (access & VM_PROT_EXECUTE)
		fault.flags |= FAULT_FLAG_INSTRUCTION;
	result = (*owner->vma.vm_ops->fault)(&fault);
	if (result & VM_FAULT_OOM)
		error = ENOMEM;
	else if (result & VM_FAULT_SIGSEGV)
		error = EACCES;
	else if (result & VM_FAULT_ERROR)
		error = EINVAL; /* Actual Native amd64 SIGBUS/BUS_ADRERR. */
	else if (result & VM_FAULT_RETRY)
		error = ERESTART;
	else if (result & (VM_FAULT_LOCKED | VM_FAULT_DONE_COW |
	    VM_FAULT_COMPLETED) || fault.page != NULL)
		error = EOPNOTSUPP;
	else
		/* A NOPAGE/0 result alone is not evidence of mapping success.
		 * Require an actual PTE from this exact live generation. */
		error = linux_mapping_extract(&owner->mapping, context.generation,
		    fault.address, &physical) ? 0 : ERESTART;
	linux_vma_context_leave(owner, &context);
leave:
	linux_task_entry_leave(&task);
unlock:
	uvmfault_unlockmaps(ufi, false);
	if (error == ERESTART)
		kpause("lnxpfault", false, 1, NULL);
	return error;
}

const struct uvm_pagerops linux_pfn_pager_ops = {
	.pgo_reference = linux_pfn_reference,
	.pgo_detach = linux_pfn_detach,
	.pgo_fault = linux_pfn_fault,
};
