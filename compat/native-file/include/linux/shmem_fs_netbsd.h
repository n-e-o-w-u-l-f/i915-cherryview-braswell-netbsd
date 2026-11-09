/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _NB_LINUX_SHMEM_FS_NETBSD_H_
#define _NB_LINUX_SHMEM_FS_NETBSD_H_
#include <sys/uio.h>
#include <linux/file_api_netbsd.h>
#include <linux/pagemap_netbsd.h>
#include <linux/uio_netbsd.h>
struct vfsmount;
struct linux_file *shmem_file_setup(const char *, loff_t, vma_flags_t);
/* Nondefault Linux mount policy needs an actual policy/mount owner. The
 * default native base-page profile cannot manufacture a Linux mount. */
struct linux_file *shmem_file_setup_with_mnt(struct vfsmount *, const char *,
    loff_t, vma_flags_t);
struct linux_folio *shmem_read_folio_gfp(struct linux_address_space *, linux_pgoff_t, gfp_t);
struct page *shmem_read_mapping_page_gfp(struct linux_address_space *, linux_pgoff_t, gfp_t);
bool shmem_mapping(const struct linux_address_space *);
bool linux_shmem_file(const struct linux_file *);
int linux_shmem_truncate_range(struct linux_inode *, loff_t, uint64_t);
void linux_shmem_writeback(struct linux_address_space *);
int linux_shmem_native_io(struct linux_file *, off_t *, struct uio *, int, bool);
int linux_shmem_mmap(struct linux_file *, struct vm_area_struct *);
unsigned long linux_shmem_get_unmapped_area(struct linux_file *, unsigned long,
    unsigned long, unsigned long, unsigned long);
static inline struct page *
shmem_read_mapping_page(struct linux_address_space *mapping, linux_pgoff_t index)
{ return shmem_read_mapping_page_gfp(mapping, index, mapping_gfp_mask(mapping)); }
static inline struct linux_folio *
shmem_read_folio(struct linux_address_space *mapping, linux_pgoff_t index)
{ return shmem_read_folio_gfp(mapping, index, mapping_gfp_mask(mapping)); }
static inline bool shmem_file(const struct linux_file *file)
{ return linux_shmem_file(file); }
#endif

