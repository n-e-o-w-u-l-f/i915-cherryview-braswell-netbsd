/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/errno.h>
#include <uvm/uvm_pmap.h>
#include <linux/fs_netbsd.h>
#include "linux_vma_internal.h"

static int
linux_pfn_enter(struct vm_area_struct *vma, unsigned long address,
    unsigned long pfn, unsigned long length, pgprot_t protection)
{
	struct linux_vma_owner *owner = vma->netbsd_owner;
	uint64_t generation;
	paddr_t physical;
	int error;

	/* The source caller owns actual CPU-physical page/resource identity
	 * and revokes these PTEs before releasing it, just as remap_pfn_range
	 * requires. A DMA address or bus-space cookie is never a PFN here. */
	if (owner == NULL || owner->shmem || length == 0 ||
	    ((address | length) & (PAGE_SIZE - 1)) != 0 ||
	    address < vma->vm_start || address >= vma->vm_end ||
	    length > vma->vm_end - address ||
	    (uintmax_t)pfn > ((uintmax_t)__type_max(paddr_t) >> PAGE_SHIFT) ||
	    (protection & ~(VM_PROT_ALL | PMAP_CACHE_MASK)) != 0)
		return EINVAL;
	if ((vma->vm_flags & VM_SHARED) == 0)
		return EOPNOTSUPP; /* No direct writable bypass of Native COW. */
	physical = (paddr_t)((uintmax_t)pfn << PAGE_SHIFT);
	error = linux_vma_context_generation(owner, &generation);
	if (error != 0)
		return error;
	return linux_mapping_enter_pfn_range(&owner->mapping, generation,
	    address, physical, length, protection & VM_PROT_ALL,
	    protection & PMAP_CACHE_MASK);
}

int
remap_pfn_range(struct vm_area_struct *vma, unsigned long address,
    unsigned long pfn, unsigned long length, pgprot_t protection)
{
	int error;
	if (length == 0 || length > ULONG_MAX - (PAGE_SIZE - 1))
		return -EINVAL;
	length = round_page(length);
	vm_flags_set(vma, VM_IO | VM_PFNMAP | VM_DONTEXPAND | VM_DONTDUMP);
	error = linux_pfn_enter(vma, address, pfn, length, protection);
	return -error;
}

vm_fault_t
vmf_insert_pfn_prot(struct vm_area_struct *vma, unsigned long address,
    unsigned long pfn, pgprot_t protection)
{
	int error;
	if ((vma->vm_flags & (VM_PFNMAP | VM_MIXEDMAP)) == 0)
		return VM_FAULT_SIGBUS;
	error = linux_pfn_enter(vma, address, pfn, PAGE_SIZE, protection);
	if (error == 0)
		return VM_FAULT_NOPAGE;
	if (error == ENOMEM)
		return VM_FAULT_OOM;
	if (error == ERESTART)
		return VM_FAULT_RETRY;
	return VM_FAULT_SIGBUS;
}

vm_fault_t
vmf_insert_pfn(struct vm_area_struct *vma, unsigned long address,
    unsigned long pfn)
{
	return vmf_insert_pfn_prot(vma, address, pfn, vma->vm_page_prot);
}

void
zap_special_vma_range(struct vm_area_struct *vma, unsigned long address,
    unsigned long length)
{
	struct linux_vma_owner *owner = vma->netbsd_owner;
	KASSERT(owner != NULL && !owner->shmem &&
	    (vma->vm_flags & (VM_PFNMAP | VM_MIXEDMAP)) != 0);
	linux_mapping_zap(&owner->mapping, address, length);
}

void
zap_vma_ptes(struct vm_area_struct *vma, unsigned long address,
    unsigned long length)
{
	KASSERT((vma->vm_flags & VM_PFNMAP) != 0);
	zap_special_vma_range(vma, address, length);
}
