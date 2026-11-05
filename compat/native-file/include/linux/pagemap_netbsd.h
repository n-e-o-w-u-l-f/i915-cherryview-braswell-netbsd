/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _NB_LINUX_PAGEMAP_NETBSD_H_
#define _NB_LINUX_PAGEMAP_NETBSD_H_
#include <sys/types.h>
#include <linux/fs_netbsd.h>
#include <linux/mm_types.h>
#include <linux/vma_netbsd.h>
/* A native folio handle owns a reference to one actual UAO base page.
 * It is not overlaid on native vm_page or Linux binary folio storage. */
struct linux_folio {
    struct page *netbsd_page;
    struct linux_address_space *mapping;
    linux_pgoff_t index;
};
struct page *linux_page_wire_mapping(struct linux_address_space *, linux_pgoff_t, gfp_t);
/* Caller holds the actual mapping invalidate read lock through its I/O. */
struct page *linux_page_wire_mapping_locked(struct linux_address_space *,
    linux_pgoff_t, gfp_t);
/* Write path additionally holds inode size lock and ensured UAO capacity. */
struct page *linux_page_wire_backing_locked(struct linux_address_space *,
    linux_pgoff_t, gfp_t);
void linux_page_get(struct page *);
void linux_page_put(struct page *);
unsigned int linux_page_count(struct page *);
struct linux_address_space *linux_page_mapping(struct page *);
linux_pgoff_t linux_page_index(struct page *);
int linux_page_set_dirty(struct page *);
void linux_page_mapping_detach(struct linux_address_space *);
void linux_page_validate_wired(struct page *);
/* Pinned fd179f8a AS_UNEVICTABLE bit. The native page owner retains actual
 * wires on referenced pages; clearing wakes retained zero-ref wire owners. */
#define AS_UNEVICTABLE 3
static inline void mapping_set_unevictable(struct linux_address_space *mapping)
{ atomic_or_ulong(&mapping->flags, 1UL << AS_UNEVICTABLE); }
static inline bool mapping_unevictable(const struct linux_address_space *mapping)
{ return mapping != NULL && (atomic_load_relaxed(&mapping->flags) &
    (1UL << AS_UNEVICTABLE)) != 0; }
void mapping_clear_unevictable(struct linux_address_space *);
int linux_page_system_init(void);
void linux_page_system_fini(void);
struct linux_folio *linux_page_folio(struct page *);
unsigned long linux_folio_pfn(const struct linux_folio *);
void linux_folio_mark_accessed(struct linux_folio *);
int linux_page_discard_range(struct linux_address_space *, voff_t, voff_t);
/* Caller holds inode size mutex + mapping invalidate writer, in that order. */
int linux_page_discard_range_locked(struct linux_address_space *, voff_t, voff_t);
bool linux_page_has_backing(struct linux_address_space *, linux_pgoff_t);
#define get_page linux_page_get
#define put_page linux_page_put
#define page_count linux_page_count
#define page_mapping linux_page_mapping
#define page_index linux_page_index
#define set_page_dirty linux_page_set_dirty
#define set_page_dirty_lock linux_page_set_dirty
#define page_folio linux_page_folio
static inline struct page *folio_page(struct linux_folio *folio, size_t index)
{
    if (index != 0)
        panic("folio_page: index exceeds actual native base-page extent");
    return folio->netbsd_page;
}
static inline struct page *folio_file_page(struct linux_folio *folio,
    linux_pgoff_t index)
{
    if (index != folio->index)
        panic("folio_file_page: index exceeds actual native file extent");
    return folio->netbsd_page;
}
static inline linux_pgoff_t folio_next_index(const struct linux_folio *folio)
{ return folio->index + 1; }
static inline void folio_get(struct linux_folio *folio)
{ linux_page_get(folio->netbsd_page); }
static inline void folio_put(struct linux_folio *folio)
{ linux_page_put(folio->netbsd_page); }
static inline unsigned long folio_nr_pages(const struct linux_folio *folio)
{ (void)folio; return 1; }
static inline size_t folio_size(const struct linux_folio *folio)
{ (void)folio; return PAGE_SIZE; }
static inline unsigned int folio_order(const struct linux_folio *folio)
{ (void)folio; return 0; }
static inline unsigned long folio_pfn(const struct linux_folio *folio)
{ return linux_folio_pfn(folio); }
static inline int folio_mark_dirty(struct linux_folio *folio)
{ return linux_page_set_dirty(folio->netbsd_page); }
#define folio_mark_accessed linux_folio_mark_accessed
static inline struct page *read_mapping_page(struct linux_address_space *mapping,
    linux_pgoff_t index, void *data)
{
    (void)data;
    return linux_page_wire_mapping(mapping, index, mapping_gfp_mask(mapping));
}
#endif

