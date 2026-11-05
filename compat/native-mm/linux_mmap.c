/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/mman.h>
#include <sys/proc.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_map.h>
#include <uvm/uvm_object.h>
#include <uvm/uvm_pager.h>
#include <uvm/uvm_pmap.h>
#include <linux/fs_netbsd.h>
#include <linux/file_api_netbsd.h>
#include <linux/shmem_fs_netbsd.h>
#include <linux/task_netbsd.h>
#include "linux_vma_internal.h"

struct linux_mmap_request {
	struct uvm_mmap_request request;
	struct linux_file *original;
	int flags;
	bool shmem;
};

static vm_flags_t
linux_vma_access(vm_prot_t protection, vm_prot_t maximum, bool shared)
{
	return protection | ((vm_flags_t)maximum << 4) |
	    (shared ? VM_SHARED | VM_MAYSHARE : 0);
}

static int
linux_vma_offset(linux_pgoff_t page, voff_t *offset)
{
	if ((uintmax_t)page > ((uintmax_t)__type_max(voff_t) >> PAGE_SHIFT))
		return EOVERFLOW;
	*offset = (voff_t)((uintmax_t)page << PAGE_SHIFT);
	return 0;
}

int
linux_vma_mapping_ready(struct linux_vma_owner *owner)
{
	struct vm_area_struct *vma = &owner->vma;
	struct linux_file *file = vma->vm_file;
	voff_t offset;
	int error;

	if (file == NULL || file->f_mapping == NULL)
		return ENODEV;
	if (owner->mapping.mapping != NULL) {
		/* An initial mapper may change vm_file before installing pages.
		 * Changing registry identity after installation needs a separate
		 * Native backing transaction; never leave PTEs on a freed mapping. */
		return owner->mapping.mapping == file->f_mapping ? 0 : EOPNOTSUPP;
	}
	error = linux_vma_offset(vma->vm_pgoff, &offset);
	if (error != 0)
		return error;
	get_file(file); /* Registry identity survives vma_set_file/unwind. */
	error = linux_mapping_register(file->f_mapping, &owner->mapping,
	    owner->map, vma->vm_start, vma->vm_end, offset,
	    owner->entry->protection, owner->entry->max_protection,
	    (vma->vm_flags & (VM_SHARED | VM_MAYWRITE)) ==
	    (VM_SHARED | VM_MAYWRITE));
	if (error != 0) {
		fput(file);
		return error;
	}
	owner->registered_file = file;
	/* The Native map writer exclusively owns this reserved interval.
	 * remap_pfn_range is allowed during the actual driver mmap callback. */
	linux_mapping_activate(&owner->mapping);
	owner->active = true;
	return 0;
}

int
linux_vma_context_enter(struct linux_vma_owner *owner,
    struct linux_vma_context *context)
{
	struct linux_mapping_snapshot snapshot;
	int error = linux_vma_mapping_ready(owner);

	if (error != 0)
		return error;
	if (!linux_mapping_snapshot(&owner->mapping, &snapshot))
		return ERESTART;
	context->lwp = curlwp;
	context->generation = snapshot.generation;
	mutex_enter(&owner->context_lock);
	LIST_INSERT_HEAD(&owner->contexts, context, link);
	mutex_exit(&owner->context_lock);
	return 0;
}

void
linux_vma_context_leave(struct linux_vma_owner *owner,
    struct linux_vma_context *context)
{
	mutex_enter(&owner->context_lock);
	LIST_REMOVE(context, link);
	mutex_exit(&owner->context_lock);
}

int
linux_vma_context_generation(struct linux_vma_owner *owner,
    uint64_t *generation)
{
	struct linux_vma_context *context;
	struct linux_mapping_snapshot snapshot;
	int error = EPERM;

	if (owner->preparing_lwp == curlwp) {
		error = linux_vma_mapping_ready(owner);
		if (error != 0)
			return error;
		if (!linux_mapping_snapshot(&owner->mapping, &snapshot))
			return ERESTART;
		*generation = snapshot.generation;
		return 0;
	}

	mutex_enter(&owner->context_lock);
	LIST_FOREACH(context, &owner->contexts, link) {
		if (context->lwp == curlwp) {
			*generation = context->generation;
			error = 0;
			break;
		}
	}
	mutex_exit(&owner->context_lock);
	return error;
}

static void
linux_mmap_finish(struct uvm_mmap_request *request)
{
	struct linux_mmap_request *state = request->data;

	KASSERT(request == &state->request);
	/* Original DRM FD ownership ends here even if mmap replaced vm_file
	 * with the actual device-owned singleton. Each VMA owns its final file. */
	fput(state->original);
	kmem_free(state, sizeof(*state));
}

int
linux_uvm_mmap_prepare(struct linux_file *file, off_t *offset, size_t length,
    int prot, int *flags, int *advice, struct uvm_object **object,
    int *maximum, struct uvm_mmap_request **request)
{
	struct linux_mmap_request *state;
	struct uvm_object *backing;
	vm_prot_t maxprot;

	*object = NULL;
	*request = NULL;
	if (file == NULL || file->f_op == NULL || length == 0 ||
	    *offset < 0 || ((*offset | length) & (PAGE_SIZE - 1)) != 0 ||
	    (uintmax_t)length > (uintmax_t)__type_max(voff_t) - *offset ||
	    ((*flags & (MAP_SHARED | MAP_PRIVATE)) != MAP_SHARED &&
	    (*flags & (MAP_SHARED | MAP_PRIVATE)) != MAP_PRIVATE))
		return EINVAL;
	if (file->f_op->mmap == NULL && file->f_op->mmap_prepare == NULL)
		return ENODEV;
	if (!shmem_file(file) && (*flags & MAP_SHARED) == 0)
		return EOPNOTSUPP; /* Device-PFN COW needs a real page-copy owner. */
	if ((file->f_mode & FMODE_READ) == 0)
		return EACCES;
	maxprot = VM_PROT_READ | VM_PROT_EXECUTE;
	if ((*flags & MAP_SHARED) == 0 || (file->f_mode & FMODE_WRITE) != 0)
		maxprot |= VM_PROT_WRITE;
	if ((prot & maxprot) != prot)
		return EACCES;
	state = kmem_zalloc(sizeof(*state), KM_SLEEP);
	state->original = get_file(file);
	state->shmem = shmem_file(file);
	state->flags = *flags;
	state->request.entry_ops = &linux_vma_entry_ops;
	state->request.data = state;
	state->request.finish = linux_mmap_finish;
	if (state->shmem) {
		backing = file->f_mapping->netbsd_uobj;
		KASSERT(backing != NULL && UVM_OBJ_IS_AOBJ(backing));
		(*backing->pgops->pgo_reference)(backing);
	} else {
		backing = kmem_zalloc(sizeof(*backing), KM_SLEEP);
		uvm_obj_init(backing, &linux_pfn_pager_ops, true, 1);
	}
	*object = backing;
	*request = &state->request;
	*maximum = maxprot;
	*advice = UVM_ADV_NORMAL;
	return 0;
}

static int
linux_vma_prepare(struct vm_map *map, struct vm_map_entry *entry)
{
	struct linux_mmap_request *state = entry->uobj_mmap_request->data;
	struct linux_vma_owner *owner;
	struct vm_area_struct *vma;
	struct task_struct *task = NULL;
	struct linux_file *file;
	int error;

	/* An explicit Native vmspace owner is required for arbitrary user-map
	 * copies. Initial mmap must target this real process's actual map. */
	if (map != &curproc->p_vmspace->vm_map || VM_MAP_IS_KERNEL(map))
		return EOPNOTSUPP;
	owner = kmem_zalloc(sizeof(*owner), KM_SLEEP);
	mutex_init(&owner->context_lock, MUTEX_DEFAULT, IPL_NONE);
	LIST_INIT(&owner->contexts);
	owner->entry = entry;
	owner->map = map;
	owner->native_offset = entry->offset;
	owner->shmem = state->shmem;
	entry->uobj_private = owner; /* Native abort now owns every failure. */
	vma = &owner->vma;
	vma->netbsd_owner = owner;
	vma->vm_start = entry->start;
	vma->vm_end = entry->end;
	vma->vm_pgoff = (linux_pgoff_t)entry->offset >> PAGE_SHIFT;
	vma->vm_flags = linux_vma_access(entry->protection,
	    entry->max_protection, (state->flags & MAP_SHARED) != 0);
	vma->vm_page_prot = vma_get_page_prot(vma);
	vma->vm_file = get_file(state->original);
	vma->vm_mm = linux_mm_identity_get(curproc->p_vmspace);
	if (vma->vm_mm == NULL)
		return EBUSY;
	owner->close_spare = linux_task_alloc();
	if (owner->close_spare == NULL)
		return ENOMEM;
	error = linux_task_entry_enter(&task);
	if (error != 0)
		return error;
	file = vma->vm_file;
	owner->preparing_lwp = curlwp;
	/* The selected i915 fops uses the real legacy mmap callback. A modern
	 * descriptor requires the same backing class through the Native object
	 * handoff; replacement across UAO/device classes is rejected explicitly. */
	if (file->f_op->mmap_prepare != NULL) {
		struct vm_area_desc desc = {
			.mm = vma->vm_mm, .file = file,
			.start = vma->vm_start, .end = vma->vm_end,
			.pgoff = vma->vm_pgoff, .vm_file = file,
			.vma_flags = vma->flags, .page_prot = vma->vm_page_prot,
		};
		error = (*file->f_op->mmap_prepare)(&desc);
		if (error != 0)
			goto callback_done;
		if (desc.vm_file != file) {
			/* Actual frozen descriptor contract transfers the changed
			 * file reference; unchanged file already owns one here. */
			vma->vm_file = desc.vm_file;
			fput(file);
		}
		vma->vm_pgoff = desc.pgoff;
		vma->flags = desc.vma_flags;
		vma->vm_page_prot = desc.page_prot;
		if (vma->vm_file == NULL ||
		    shmem_file(vma->vm_file) != owner->shmem ||
		    desc.action.type != MMAP_NOTHING) {
			error = -EOPNOTSUPP;
			goto callback_done;
		}
		file = vma->vm_file;
		error = file->f_op->mmap != NULL ?
		    (*file->f_op->mmap)(file, vma) : 0;
		if (error == 0) {
			vma->vm_ops = desc.vm_ops;
			vma->vm_private_data = desc.private_data;
		}
	} else {
		error = (*file->f_op->mmap)(file, vma);
	}
callback_done:
	owner->preparing_lwp = NULL;
	if (error == 0) {
		owner->opened = true;
		if (vma->vm_start != entry->start || vma->vm_end != entry->end ||
		    vma->vm_file == NULL ||
		    (vma->vm_ops != NULL && (vma->vm_ops->may_split != NULL ||
		    vma->vm_ops->mremap != NULL || vma->vm_ops->mprotect != NULL)))
			error = -EOPNOTSUPP;
	}
	if (error == 0 && vma->vm_ops != NULL && vma->vm_ops->mapped != NULL)
		error = (*vma->vm_ops->mapped)(vma->vm_start, vma->vm_end,
		    vma->vm_pgoff, vma->vm_file, &vma->vm_private_data);
	linux_task_entry_leave(&task);
	if (error != 0)
		return error < 0 ? -error : error;
	entry->max_protection &= (vma->vm_flags >> 4) & VM_PROT_ALL;
	if (vma->vm_flags & VM_DONTCOPY)
		entry->inheritance = UVM_INH_NONE;
	if (vma->vm_flags & VM_WIPEONFORK)
		return EOPNOTSUPP; /* No silent special-PFN zero inheritance. */
	return linux_vma_mapping_ready(owner);
}

static void
linux_vma_link(struct vm_map *map, struct vm_map_entry *entry)
{
	struct linux_vma_owner *owner = entry->uobj_private;
	KASSERT(owner->mapping.map == map);
	if (!owner->active) {
		linux_mapping_activate(&owner->mapping);
		owner->active = true;
	}
}

static void
linux_vma_unlink(struct vm_map *map, struct vm_map_entry *entry)
{
	struct linux_vma_owner *owner = entry->uobj_private;
	if (owner->mapping.mapping != NULL) {
		KASSERT(owner->mapping.map == map);
		linux_mapping_deactivate(&owner->mapping);
		owner->active = false;
	}
}

static void
linux_vma_detach(struct vm_map_entry *entry)
{
	struct linux_vma_owner *owner = entry->uobj_private;
	struct task_struct *task = NULL;

	ASSERT_SLEEPABLE();
	KASSERT(!owner->active && LIST_EMPTY(&owner->contexts));
	if (owner->mapping.mapping != NULL)
		linux_mapping_unregister(&owner->mapping);
	if (owner->opened && owner->vma.vm_ops != NULL &&
	    owner->vma.vm_ops->close != NULL) {
		linux_task_entry_enter_preallocated(&task, &owner->close_spare);
		(*owner->vma.vm_ops->close)(&owner->vma);
		linux_task_entry_leave(&task);
	}
	if (owner->close_spare != NULL)
		put_task_struct(owner->close_spare);
	if (owner->registered_file != NULL)
		fput(owner->registered_file);
	if (owner->vma.vm_file != NULL)
		fput(owner->vma.vm_file);
	if (owner->vma.vm_mm != NULL)
		mmdrop(owner->vma.vm_mm);
	mutex_destroy(&owner->context_lock);
	kmem_free(owner, sizeof(*owner));
	entry->uobj_private = NULL;
}

/* Definitions below are kept with the entry factory so Native ownership,
 * source VMA callbacks and real address-space identity cannot diverge. */
static linux_pgoff_t
linux_vma_adjust_pgoff(const struct linux_vma_owner *owner,
    const struct vm_map_entry *entry)
{
	uintmax_t delta;
	KASSERT(entry->offset >= owner->native_offset);
	delta = (uintmax_t)(entry->offset - owner->native_offset) >> PAGE_SHIFT;
	if (__predict_false(delta > ULONG_MAX - owner->vma.vm_pgoff))
		panic("Linux copied VMA page offset overflow");
	return owner->vma.vm_pgoff + (linux_pgoff_t)delta;
}

static void
linux_vma_copy(struct vm_map *map, const struct vm_map_entry *source,
    struct vm_map_entry *entry)
{
	struct linux_vma_owner *parent = source->uobj_private, *owner;
	struct task_struct *open_spare, *task = NULL;
	voff_t offset;

	if (map->vmspace_owner == NULL) {
		/* Prechecked Native kernel extraction of actual UAO/amap pages.
		 * These Native backing refs are owned by the extraction entry;
		 * there is no fabricated kernel mm or Linux VMA lifetime. */
		KASSERT(parent->shmem && VM_MAP_IS_KERNEL(map));
		entry->uobj_entry_ops = NULL;
		return;
	}
	owner = kmem_zalloc(sizeof(*owner), KM_SLEEP);
	mutex_init(&owner->context_lock, MUTEX_DEFAULT, IPL_NONE);
	LIST_INIT(&owner->contexts);
	owner->vma = parent->vma;
	owner->vma.netbsd_owner = owner;
	owner->vma.vm_start = entry->start;
	owner->vma.vm_end = entry->end;
	owner->vma.vm_pgoff = linux_vma_adjust_pgoff(parent, entry);
	owner->vma.vm_file = get_file(parent->vma.vm_file);
	owner->vma.vm_mm = linux_mm_identity_get(map->vmspace_owner);
	if (__predict_false(owner->vma.vm_mm == NULL))
		panic("Linux retained VMA copy lost native MM admission");
	owner->entry = entry;
	owner->map = map;
	owner->native_offset = entry->offset;
	owner->shmem = parent->shmem;
	/* Parent's exclusive never-attached close spare pins the actual task
	 * runtime even during external quiesce. Internal copy cannot fail. */
	open_spare = linux_task_alloc_owner_wait(parent->close_spare);
	owner->close_spare = linux_task_alloc_owner_wait(parent->close_spare);
	linux_task_entry_enter_preallocated(&task, &open_spare);
	if (owner->vma.vm_ops != NULL && owner->vma.vm_ops->open != NULL)
		(*owner->vma.vm_ops->open)(&owner->vma);
	owner->opened = true;
	linux_task_entry_leave(&task);
	KASSERT(owner->vma.vm_file->f_mapping == parent->mapping.mapping);
	if (__predict_false(linux_vma_offset(owner->vma.vm_pgoff, &offset) != 0))
		panic("Linux copied VMA offset outside native range");
	owner->registered_file = get_file(owner->vma.vm_file);
	linux_mapping_clone_register(&parent->mapping, &owner->mapping, map,
	    entry->start, entry->end, offset, entry->protection,
	    entry->max_protection);
	entry->uobj_private = owner;
}

static void
linux_vma_update(struct vm_map *map, struct vm_map_entry *entry)
{
	struct linux_vma_owner *owner = entry->uobj_private;
	struct vm_area_struct *vma = &owner->vma;
	voff_t offset;
	vm_flags_t retained = vma->vm_flags &
	    ~(VM_ACCESS_FLAGS | VM_MAYREAD | VM_MAYWRITE | VM_MAYEXEC);

	KASSERT(owner->map == map);
	vma->vm_pgoff = linux_vma_adjust_pgoff(owner, entry);
	vma->vm_start = entry->start;
	vma->vm_end = entry->end;
	vma->vm_flags = retained | linux_vma_access(entry->protection,
	    entry->max_protection, (retained & VM_SHARED) != 0);
	vma->vm_page_prot = (vma->vm_page_prot & PMAP_CACHE_MASK) |
	    (vma_get_page_prot(vma) & VM_PROT_ALL);
	owner->native_offset = entry->offset;
	if (__predict_false(linux_vma_offset(vma->vm_pgoff, &offset) != 0))
		panic("Linux updated VMA offset outside native range");
	linux_mapping_update(&owner->mapping, vma->vm_start, vma->vm_end,
	    offset, entry->protection, entry->max_protection,
	    (vma->vm_flags & (VM_SHARED | VM_MAYWRITE)) ==
	    (VM_SHARED | VM_MAYWRITE));
}

static int
linux_vma_extract(struct vm_map *map, const struct vm_map_entry *entry,
    struct vm_map *destination, int flags)
{
	const struct linux_vma_owner *owner = entry->uobj_private;
	KASSERT(owner->map == map);
	if (destination->vmspace_owner == NULL)
		return owner->shmem && VM_MAP_IS_KERNEL(destination) ? 0 : EOPNOTSUPP;
	if (flags & (UVM_EXTRACT_PROT_ALL | UVM_EXTRACT_FIXPROT))
		return EACCES;
	return 0;
}

static int
linux_vma_fault_enter(struct vm_map *map, struct vm_map_entry *entry,
    vaddr_t address, vm_prot_t access, bool wiring)
{
	struct linux_vma_owner *owner = entry->uobj_private;
	struct vm_area_struct *vma = &owner->vma;
	uintmax_t offset, page;
	loff_t size;

	KASSERT(owner->map == map && address >= vma->vm_start &&
	    address < vma->vm_end);
	if ((access & entry->max_protection) != access)
		return EACCES;
	if (!owner->shmem) {
		/* Native mlock cannot manufacture UVM pages for GPU aperture PTEs. */
		return wiring ? EOPNOTSUPP : 0;
	}
	down_read(&vma->vm_file->f_mapping->invalidate_lock);
	page = vma->vm_pgoff + ((address - vma->vm_start) >> PAGE_SHIFT);
	offset = page << PAGE_SHIFT;
	size = i_size_read(vma->vm_file->f_mapping->host);
	if (size < 0 || offset >= (uintmax_t)size) {
		up_read(&vma->vm_file->f_mapping->invalidate_lock);
		/* Frozen amd64 trap.c maps Native EINVAL to SIGBUS/BUS_ADRERR;
		 * EFAULT would instead produce SIGSEGV/SEGV_MAPERR. */
		return EINVAL;
	}
	return 0;
}

static void
linux_vma_fault_leave(struct vm_map_entry *entry)
{
	struct linux_vma_owner *owner = entry->uobj_private;
	if (owner->shmem)
		up_read(&owner->vma.vm_file->f_mapping->invalidate_lock);
}

const struct uvm_pagerops linux_vma_entry_ops = {
	.pgo_entry_prepare = linux_vma_prepare,
	.pgo_entry_copy = linux_vma_copy,
	.pgo_entry_update = linux_vma_update,
	.pgo_entry_link = linux_vma_link,
	.pgo_entry_unlink = linux_vma_unlink,
	.pgo_entry_detach = linux_vma_detach,
	.pgo_entry_extract = linux_vma_extract,
	.pgo_entry_fault_enter = linux_vma_fault_enter,
	.pgo_entry_fault_leave = linux_vma_fault_leave,
};

int
linux_shmem_mmap(struct linux_file *file, struct vm_area_struct *vma)
{
	struct linux_vma_owner *owner = vma->netbsd_owner;
	if (owner == NULL || !owner->shmem || !shmem_file(file) ||
	    vma->vm_file != file || !UVM_OBJ_IS_AOBJ(owner->entry->object.uvm_obj) ||
	    owner->entry->object.uvm_obj != file->f_mapping->netbsd_uobj)
		return -EINVAL;
	/* Real UAO pager and Native COW/amap carry ordinary page ownership.
	 * The per-entry early fault guard supplies Linux logical EOF. */
	return 0;
}

unsigned long
linux_shmem_get_unmapped_area(struct linux_file *file, unsigned long hint,
    unsigned long length, unsigned long pgoff, unsigned long flags)
{
	vaddr_t address = hint;
	vsize_t size = length;
	voff_t offset;
	int error;

	if (!shmem_file(file) || length == 0 ||
	    linux_vma_offset(pgoff, &offset) != 0)
		return (unsigned long)-EINVAL;
	if ((flags & MAP_FIXED) != 0)
		return hint;
	if ((hint & (PAGE_SIZE - 1)) != 0 ||
	    (length & (PAGE_SIZE - 1)) != 0)
		return (unsigned long)-EINVAL;
	/* Native uvm_map_findspace performs the real map search. It reserves
	 * nothing; the subsequent Native mapping transaction revalidates. */
	vm_map_lock(&curproc->p_vmspace->vm_map);
	error = uvm_map_findspace(&curproc->p_vmspace->vm_map, hint, size,
	    &address, NULL, offset, 0, 0) == NULL ? ENOMEM : 0;
	vm_map_unlock(&curproc->p_vmspace->vm_map);
	return error != 0 ? (unsigned long)-error : address;
}

unsigned long
vm_mmap(struct linux_file *file, unsigned long address, unsigned long length,
    unsigned long protection, unsigned long flags, unsigned long offset)
{
	struct uvm_mmap_request *request;
	struct uvm_object *object;
	off_t native_offset;
	int maximum, advice, native_flags, error;

	if (file == NULL || offset > (unsigned long)__type_max(off_t) ||
	    (flags & ~0x13UL) != 0 || protection > VM_PROT_ALL || length == 0 ||
	    length > ULONG_MAX - (PAGE_SIZE - 1))
		return (unsigned long)-EINVAL;
	length = round_page(length);
	native_offset = offset;
	/* Explicit source Linux MAP_SHARED/PRIVATE/FIXED values. Unsupported
	 * Linux bits must never accidentally select differently valued Native
	 * flags such as wiring, anonymous backing or semaphore behavior. */
	native_flags = (flags & 1 ? MAP_SHARED : 0) |
	    (flags & 2 ? MAP_PRIVATE : 0) | (flags & 0x10 ? MAP_FIXED : 0);
	error = linux_uvm_mmap_prepare(file, &native_offset, length,
	    protection, &native_flags, &advice, &object, &maximum, &request);
	if (error != 0)
		return (unsigned long)-error;
	error = uvm_mmap_object(curproc, &address, length, protection, maximum,
	    native_flags, advice, object, native_offset, request);
	return error != 0 ? (unsigned long)-error : address;
}

struct vm_area_struct *
find_vma(struct mm_struct *mm, unsigned long address)
{
	struct vm_map *map;
	struct vm_map_entry *entry;
	struct linux_vma_owner *owner;

	/* The source caller owns this mm's actual Native map read/write lock.
	 * Native non-Linux entries have no fabricated source VMA. */
	KASSERT(mm->netbsd_vmspace != NULL);
	map = &mm->netbsd_vmspace->vm_map;
	KASSERT(rw_lock_held(&map->lock));
	if (!uvm_map_lookup_entry(map, address, &entry))
		entry = entry->next;
	if (entry == &map->header || entry->uobj_private == NULL ||
	    entry->uobj_entry_ops != &linux_vma_entry_ops)
		return NULL;
	owner = entry->uobj_private;
	return &owner->vma;
}
