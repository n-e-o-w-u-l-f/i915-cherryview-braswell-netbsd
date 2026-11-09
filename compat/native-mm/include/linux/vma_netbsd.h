/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/* Source-facing VMA contracts from Linux fd179f8a, backed by native owners.
 * This is not the Linux binary VMA/page-table layout.  Native page/PTE types
 * and the old native struct page are not replaced or fabricated here.
 */
#ifndef _LINUX_VMA_NETBSD_H_
#define _LINUX_VMA_NETBSD_H_

#include <sys/types.h>
#include <linux/types.h>
#include <linux/gfp.h>
#include <linux/mm_types.h>
#include <linux/mm_identity_netbsd.h>
#include <linux/mm_abi_types_netbsd.h>

#if __SIZEOF_LONG__ != 8
#error "The reviewed HP native VMA flag contract requires 64-bit unsigned long"
#endif

struct linux_file;
struct linux_vma_owner;
struct page;
struct vm_area_struct;
struct vm_fault;
typedef unsigned long vm_flags_t;
typedef unsigned int vm_fault_t;
typedef int vma_flag_t;
typedef struct { unsigned long __vma_flags[1]; } vma_flags_t;
#define NUM_VMA_FLAG_BITS 64
#define EMPTY_VMA_FLAGS ((vma_flags_t){ { 0 } })

/* These bit numbers are the actual frozen mm.h enum, not host mmap bits. */
enum {
	VMA_READ_BIT = 0, VMA_WRITE_BIT = 1, VMA_EXEC_BIT = 2,
	VMA_SHARED_BIT = 3, VMA_MAYREAD_BIT = 4, VMA_MAYWRITE_BIT = 5,
	VMA_MAYEXEC_BIT = 6, VMA_MAYSHARE_BIT = 7, VMA_GROWSDOWN_BIT = 8,
	VMA_UFFD_MISSING_BIT = 9, VMA_PFNMAP_BIT = 10,
	VMA_MAYBE_GUARD_BIT = 11, VMA_UFFD_WP_BIT = 12, VMA_LOCKED_BIT = 13,
	VMA_IO_BIT = 14, VMA_SEQ_READ_BIT = 15, VMA_RAND_READ_BIT = 16,
	VMA_DONTCOPY_BIT = 17, VMA_DONTEXPAND_BIT = 18,
	VMA_LOCKONFAULT_BIT = 19, VMA_ACCOUNT_BIT = 20, VMA_NORESERVE_BIT = 21,
	VMA_HUGETLB_BIT = 22, VMA_SYNC_BIT = 23, VMA_ARCH_1_BIT = 24,
	VMA_WIPEONFORK_BIT = 25, VMA_DONTDUMP_BIT = 26, VMA_SOFTDIRTY_BIT = 27,
	VMA_MIXEDMAP_BIT = 28, VMA_HUGEPAGE_BIT = 29, VMA_NOHUGEPAGE_BIT = 30,
	VMA_MERGEABLE_BIT = 31, VMA_ALLOW_ANY_UNCACHED_BIT = 39,
	VMA_DROPPABLE_BIT = 40, VMA_UFFD_MINOR_BIT = 41, VMA_SEALED_BIT = 42,
	VMA_UFFD_RWP_BIT = 43,
};
#define VM_NONE 0UL
#define VM_READ (1UL << VMA_READ_BIT)
#define VM_WRITE (1UL << VMA_WRITE_BIT)
#define VM_EXEC (1UL << VMA_EXEC_BIT)
#define VM_SHARED (1UL << VMA_SHARED_BIT)
#define VM_MAYREAD (1UL << VMA_MAYREAD_BIT)
#define VM_MAYWRITE (1UL << VMA_MAYWRITE_BIT)
#define VM_MAYEXEC (1UL << VMA_MAYEXEC_BIT)
#define VM_MAYSHARE (1UL << VMA_MAYSHARE_BIT)
#define VM_GROWSDOWN (1UL << VMA_GROWSDOWN_BIT)
#define VM_PFNMAP (1UL << VMA_PFNMAP_BIT)
#define VM_LOCKED (1UL << VMA_LOCKED_BIT)
#define VM_IO (1UL << VMA_IO_BIT)
#define VM_SEQ_READ (1UL << VMA_SEQ_READ_BIT)
#define VM_RAND_READ (1UL << VMA_RAND_READ_BIT)
#define VM_DONTCOPY (1UL << VMA_DONTCOPY_BIT)
#define VM_DONTEXPAND (1UL << VMA_DONTEXPAND_BIT)
#define VM_LOCKONFAULT (1UL << VMA_LOCKONFAULT_BIT)
#define VM_ACCOUNT (1UL << VMA_ACCOUNT_BIT)
#define VM_NORESERVE (1UL << VMA_NORESERVE_BIT)
#define VM_HUGETLB (1UL << VMA_HUGETLB_BIT)
#define VM_SYNC (1UL << VMA_SYNC_BIT)
#define VM_WIPEONFORK (1UL << VMA_WIPEONFORK_BIT)
#define VM_DONTDUMP (1UL << VMA_DONTDUMP_BIT)
#define VM_MIXEDMAP (1UL << VMA_MIXEDMAP_BIT)
#define VM_HUGEPAGE (1UL << VMA_HUGEPAGE_BIT)
#define VM_NOHUGEPAGE (1UL << VMA_NOHUGEPAGE_BIT)
#define VM_SPECIAL (VM_IO | VM_DONTEXPAND | VM_PFNMAP | VM_MIXEDMAP)
#define VM_ACCESS_FLAGS (VM_READ | VM_WRITE | VM_EXEC)

enum vm_fault_reason {
	VM_FAULT_OOM = 0x000001, VM_FAULT_SIGBUS = 0x000002,
	VM_FAULT_MAJOR = 0x000004, VM_FAULT_HWPOISON = 0x000010,
	VM_FAULT_HWPOISON_LARGE = 0x000020, VM_FAULT_SIGSEGV = 0x000040,
	VM_FAULT_NOPAGE = 0x000100, VM_FAULT_LOCKED = 0x000200,
	VM_FAULT_RETRY = 0x000400, VM_FAULT_FALLBACK = 0x000800,
	VM_FAULT_DONE_COW = 0x001000, VM_FAULT_NEEDDSYNC = 0x002000,
	VM_FAULT_COMPLETED = 0x004000, VM_FAULT_HINDEX_MASK = 0x0f0000,
};
#define VM_FAULT_ERROR (VM_FAULT_OOM | VM_FAULT_SIGBUS | VM_FAULT_SIGSEGV | \
    VM_FAULT_HWPOISON | VM_FAULT_HWPOISON_LARGE | VM_FAULT_FALLBACK)
enum fault_flag {
	FAULT_FLAG_WRITE = 1 << 0, FAULT_FLAG_MKWRITE = 1 << 1,
	FAULT_FLAG_ALLOW_RETRY = 1 << 2, FAULT_FLAG_RETRY_NOWAIT = 1 << 3,
	FAULT_FLAG_KILLABLE = 1 << 4, FAULT_FLAG_TRIED = 1 << 5,
	FAULT_FLAG_USER = 1 << 6, FAULT_FLAG_REMOTE = 1 << 7,
	FAULT_FLAG_INSTRUCTION = 1 << 8, FAULT_FLAG_INTERRUPTIBLE = 1 << 9,
	FAULT_FLAG_UNSHARE = 1 << 10, FAULT_FLAG_ORIG_PTE_VALID = 1 << 11,
	FAULT_FLAG_VMA_LOCK = 1 << 12,
};

struct vm_operations_struct {
	void (*open)(struct vm_area_struct *);
	void (*close)(struct vm_area_struct *);
	int (*mapped)(unsigned long, unsigned long, linux_pgoff_t,
	    const struct linux_file *, void **);
	int (*may_split)(struct vm_area_struct *, unsigned long);
	int (*mremap)(struct vm_area_struct *);
	int (*mprotect)(struct vm_area_struct *, unsigned long, unsigned long,
	    unsigned long);
	vm_fault_t (*fault)(struct vm_fault *);
	vm_fault_t (*huge_fault)(struct vm_fault *, unsigned int);
	vm_fault_t (*map_pages)(struct vm_fault *, linux_pgoff_t, linux_pgoff_t);
	unsigned long (*pagesize)(struct vm_area_struct *);
	vm_fault_t (*page_mkwrite)(struct vm_fault *);
	vm_fault_t (*pfn_mkwrite)(struct vm_fault *);
	int (*access)(struct vm_area_struct *, unsigned long, void *, int, int);
	const char *(*name)(struct vm_area_struct *);
};

struct vm_area_struct {
	unsigned long vm_start;
	unsigned long vm_end;
	struct mm_struct *vm_mm;
	union { vm_flags_t vm_flags; vma_flags_t flags; };
	pgprot_t vm_page_prot;
	const struct vm_operations_struct *vm_ops;
	linux_pgoff_t vm_pgoff;
	struct linux_file *vm_file;
	void *vm_private_data;
	struct linux_vma_owner *netbsd_owner;
};

struct vm_fault {
	struct vm_area_struct *vma;
	gfp_t gfp_mask;
	linux_pgoff_t pgoff;
	unsigned long address;
	unsigned long real_address;
	enum fault_flag flags;
	struct page *cow_page;
	struct page *page;
};

enum mmap_action_type {
	MMAP_NOTHING = 0, MMAP_REMAP_PFN, MMAP_IO_REMAP_PFN,
	MMAP_SIMPLE_IO_REMAP, MMAP_MAP_KERNEL_PAGES,
};
struct mmap_action {
	union {
		struct { unsigned long start, start_pfn, size; pgprot_t pgprot; } remap;
		struct { phys_addr_t start_phys_addr; unsigned long size; } simple_ioremap;
		struct { unsigned long start; struct page **pages;
		    unsigned long nr_pages; linux_pgoff_t pgoff; } map_kernel;
	};
	enum mmap_action_type type;
	int error_override;
	bool hide_from_rmap_until_complete;
};
struct vm_area_desc {
	struct mm_struct *mm;
	struct linux_file *file;
	unsigned long start, end;
	linux_pgoff_t pgoff;
	struct linux_file *vm_file;
	vma_flags_t vma_flags;
	pgprot_t page_prot;
	const struct vm_operations_struct *vm_ops;
	void *private_data;
	struct mmap_action action;
};

static inline unsigned long
vma_pages(const struct vm_area_struct *vma)
{
	return (vma->vm_end - vma->vm_start) >> PAGE_SHIFT;
}
static inline bool
fault_flag_allow_retry_first(enum fault_flag flags)
{
	return (flags & FAULT_FLAG_ALLOW_RETRY) && !(flags & FAULT_FLAG_TRIED);
}
static inline void
vm_flags_init(struct vm_area_struct *vma, vm_flags_t flags)
{
	vma->vm_flags = flags;
}
static inline void
vm_flags_set(struct vm_area_struct *vma, vm_flags_t flags)
{
	vma->vm_flags |= flags;
}
static inline void
vm_flags_clear(struct vm_area_struct *vma, vm_flags_t flags)
{
	vma->vm_flags &= ~flags;
}
static inline void
vma_flags_clear_all(vma_flags_t *flags)
{
	flags->__vma_flags[0] = 0;
}
static inline bool
vma_flags_empty(const vma_flags_t *flags)
{
	return flags->__vma_flags[0] == 0;
}
static inline vm_flags_t
vma_flags_to_legacy(vma_flags_t flags)
{
	return flags.__vma_flags[0];
}
static inline vma_flags_t
legacy_to_vma_flags(vm_flags_t flags)
{
	return (vma_flags_t){ { flags } };
}
void vma_set_file(struct vm_area_struct *, struct linux_file *);
pgprot_t vma_get_page_prot(const struct vm_area_struct *);
pgprot_t vm_get_page_prot(unsigned long);
pgprot_t pgprot_writecombine(pgprot_t);
pgprot_t pgprot_noncached(pgprot_t);
pgprot_t pgprot_decrypted(pgprot_t);
int remap_pfn_range(struct vm_area_struct *, unsigned long, unsigned long,
    unsigned long, pgprot_t);
vm_fault_t vmf_insert_pfn_prot(struct vm_area_struct *, unsigned long,
    unsigned long, pgprot_t);
vm_fault_t vmf_insert_pfn(struct vm_area_struct *, unsigned long,
    unsigned long);
void zap_vma_ptes(struct vm_area_struct *, unsigned long, unsigned long);
void zap_special_vma_range(struct vm_area_struct *, unsigned long,
    unsigned long);

#endif /* _LINUX_VMA_NETBSD_H_ */
