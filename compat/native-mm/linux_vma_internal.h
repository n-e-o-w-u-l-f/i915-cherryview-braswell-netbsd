/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _LINUX_VMA_INTERNAL_H_
#define _LINUX_VMA_INTERNAL_H_
#include <sys/mutex.h>
#include <linux/mm_netbsd.h>

/* Native map locking protects the persistent VMA and its entry pointer.
 * Device faults release Native amap/object locks but retain the actual map
 * read lock, exactly as the source mmap_lock contract requires. */
struct linux_vma_owner {
	struct vm_area_struct vma;
	struct linux_native_mapping mapping;
	struct linux_file *registered_file;
	struct task_struct *close_spare;
	struct vm_map_entry *entry;
	struct vm_map *map;
	struct lwp *preparing_lwp;
	voff_t native_offset;
	bool shmem;
	bool active;
	bool opened;
	/* Per-LWP callback transaction, protected by context_lock. No VMA copy. */
	kmutex_t context_lock;
	LIST_HEAD(, linux_vma_context) contexts;
};

struct linux_vma_context {
	LIST_ENTRY(linux_vma_context) link;
	struct lwp *lwp;
	uint64_t generation;
};
int linux_vma_mapping_ready(struct linux_vma_owner *);
int linux_vma_context_enter(struct linux_vma_owner *, struct linux_vma_context *);
void linux_vma_context_leave(struct linux_vma_owner *, struct linux_vma_context *);
int linux_vma_context_generation(struct linux_vma_owner *, uint64_t *);
extern const struct uvm_pagerops linux_vma_entry_ops;
extern const struct uvm_pagerops linux_pfn_pager_ops;
#endif
