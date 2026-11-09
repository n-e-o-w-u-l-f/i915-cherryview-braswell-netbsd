/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Real references for UAO page-cache pages. One native wire and UAO reference
 * belong to each live sidecar; get/put update its Linux ownership, not the
 * immutable native struct page layout. Last put only enqueues preallocated
 * work: native object locking, unwire and detach run on a sleepable worker.
 */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/mutex.h>
#include <sys/rwlock.h>
#include <sys/systm.h>
#include <sys/workqueue.h>
#include <machine/vmparam.h>
#include <uvm/uvm.h>
#include <uvm/uvm_ddb.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_aobj.h>
#include <uvm/uvm_object.h>
#include <uvm/uvm_page.h>
#include <uvm/uvm_page_array.h>
#include <uvm/uvm_pager.h>
#include <linux/err.h>
#include <linux/file_netbsd.h>
#include <linux/pagemap_netbsd.h>
#include <linux/mapping_netbsd.h>

#define LINUX_PAGE_BUCKETS 256U
struct linux_page_owner {
    struct work work;
    struct page *page;
    struct linux_address_space *mapping;
    struct uvm_object *object;
    voff_t offset;
    linux_pgoff_t index;
    unsigned int refs;
    bool detached;
    bool paused;
    struct linux_folio folio;
    struct linux_page_owner *next;
};
static kmutex_t page_owner_lock;
static struct linux_page_owner *page_owners[LINUX_PAGE_BUCKETS];
static struct workqueue *page_release_queue;
static unsigned int page_owner_count;
int uao_set_pgfl_future(struct uvm_object *, int);

static unsigned int
linux_page_bucket(const struct page *page)
{
    return ((uintptr_t)page >> 6) & (LINUX_PAGE_BUCKETS - 1U);
}

static struct linux_page_owner *
linux_page_find(struct page *page)
{
    struct linux_page_owner *owner;
    KASSERT(mutex_owned(&page_owner_lock));
    for (owner = page_owners[linux_page_bucket(page)]; owner != NULL;
         owner = owner->next)
        if (owner->page == page && owner->refs != 0)
            return owner;
    return NULL;
}

static void
linux_page_release(struct work *work, void *cookie)
{
    struct linux_page_owner *owner = container_of(work, struct linux_page_owner, work);
    struct linux_page_owner **link;
    struct uvm_object *object;
    struct vm_page *native = &owner->page->p_vmp;
    unsigned int bucket = linux_page_bucket(owner->page);
    (void)cookie;
    ASSERT_SLEEPABLE();
    for (;;) {
        /* The former UAO remains a real pin and serialization owner for
         * detached private pages. Validate the published owner again after
         * locking; no freed object is reached through a stale snapshot. */
        mutex_enter(&page_owner_lock);
        object = owner->object;
        uao_reference(object);
        mutex_exit(&page_owner_lock);
        rw_enter(object->vmobjlock, RW_WRITER);
        mutex_enter(&page_owner_lock);
        if (owner->object != object) {
            mutex_exit(&page_owner_lock);
            rw_exit(object->vmobjlock);
            uao_detach(object);
            continue;
        }
        if (owner->mapping != NULL && mapping_unevictable(owner->mapping)) {
            /* Keep the real physical wire, not just a metadata flag, until
             * the mapping owner clears its unevictable requirement. */
            owner->paused = true;
            mutex_exit(&page_owner_lock);
            rw_exit(object->vmobjlock);
            uao_detach(object); /* Temporary snapshot guard only. */
            return;
        }
        if (owner->refs != 0 ||
            (!owner->detached && (native->uobject != object ||
            native->offset != owner->offset)) ||
            (owner->detached && native->uobject != NULL))
            panic("linux_page_release: native page ownership mismatch");
        for (link = &page_owners[bucket]; *link != owner; link = &(*link)->next)
            if (*link == NULL)
                panic("linux_page_release: missing page owner");
        *link = owner->next;
        if (page_owner_count == 0)
            panic("linux_page_release: owner count underflow");
        page_owner_count--;
        mutex_exit(&page_owner_lock);
        uvm_pagelock(native);
        if (owner->detached && native->wire_count == 1) {
            /* No active-object lookup or other wire can reach this private
             * page now. Native pagefree resets its final wire/accounting. */
            uvm_pageunlock(native);
            uvm_pagefree(native);
        } else {
            uvm_pageunwire(native);
            uvm_pageunlock(native);
        }
        rw_exit(object->vmobjlock);
        uao_detach(object); /* Sidecar owner. */
        uao_detach(object); /* Temporary lock-acquisition guard. */
        kmem_free(owner, sizeof(*owner));
        linux_file_reservation_leave();
        return;
    }
}

int
linux_page_system_init(void)
{
    int error;
    memset(page_owners, 0, sizeof(page_owners));
    page_owner_count = 0;
    mutex_init(&page_owner_lock, MUTEX_DEFAULT, IPL_HIGH);
    error = workqueue_create(&page_release_queue, "linuxpage",
        linux_page_release, NULL, PRI_NONE, IPL_HIGH, WQ_MPSAFE);
    if (error != 0)
        mutex_destroy(&page_owner_lock);
    return error;
}

void
linux_page_system_fini(void)
{
    ASSERT_SLEEPABLE();
    mutex_enter(&page_owner_lock);
    if (page_owner_count != 0)
        panic("linux_page_system_fini: live physical page owners");
    mutex_exit(&page_owner_lock);
    workqueue_destroy(page_release_queue);
    page_release_queue = NULL;
    mutex_destroy(&page_owner_lock);
}

static int
linux_page_fetch_wire(struct uvm_object *object, voff_t offset, gfp_t gfp,
    struct vm_page **result)
{
    struct vm_page *page = NULL, *replacement;
    int count = 1, error;
    bool blocking = gfpflags_allow_blocking(gfp);
    ASSERT_SLEEPABLE();
    if (blocking)
        rw_enter(object->vmobjlock, RW_WRITER);
    else if (!rw_tryenter(object->vmobjlock, RW_WRITER))
        return EAGAIN;
    if (gfp & __GFP_DMA32)
        (void)uao_set_pgfl_future(object, VM_FREELIST_FIRST4G);
    if (blocking) {
        /* Native pgo_get consumes the object lock, including on failure. */
        error = (*object->pgops->pgo_get)(object, offset, &page, &count, 0,
            VM_PROT_READ | VM_PROT_WRITE, UVM_ADV_RANDOM, PGO_SYNCIO);
        if (error != 0)
            return error;
        rw_enter(object->vmobjlock, RW_WRITER);
        if (count != 1 || page == NULL)
            panic("linux_page_fetch_wire: incomplete native pager result");
    } else {
        page = uvm_pagelookup(object, offset);
        if (page == NULL || (page->flags & PG_BUSY) != 0 ||
            page->loan_count != 0) {
            rw_exit(object->vmobjlock);
            return ENOMEM;
        }
        page->flags |= PG_BUSY;
        UVM_PAGE_OWN(page, "linux shmem nowait");
    }
    while (page->loan_count != 0) {
        replacement = uvm_loanbreak(page);
        if (replacement == NULL) {
            rw_exit(object->vmobjlock);
            uvm_wait("linuxpage");
            rw_enter(object->vmobjlock, RW_WRITER);
            continue;
        }
        page = replacement;
    }
    if ((gfp & __GFP_DMA32) != 0 &&
        VM_PAGE_TO_PHYS(page) >= (UINT64_C(1) << 32)) {
        /* A GFP change does not retroactively migrate an old cached page.
         * Report allocation failure rather than returning an illegal DMA
         * page. Fresh allocations use the actual restricted UAO freelist. */
        uvm_page_unbusy(&page, 1);
        rw_exit(object->vmobjlock);
        return ENOMEM;
    }
    uvm_pagemarkdirty(page, UVM_PAGE_STATUS_DIRTY);
    /* The frozen generic wire helper uses chunk-local i here. Use the
     * actual page offset so another page's swap slot is never discarded. */
    uao_dropswap(object, page->offset >> PAGE_SHIFT);
    uvm_pagelock(page);
    uvm_pagewire(page);
    uvm_pageunlock(page);
    uvm_page_unbusy(&page, 1);
    rw_exit(object->vmobjlock);
    *result = page;
    return 0;
}

static struct page *
linux_page_wire_common(struct linux_address_space *mapping, linux_pgoff_t index,
    gfp_t gfp, bool backing)
{
    struct linux_page_owner *candidate, *owner;
    struct uvm_object *object = mapping->netbsd_uobj;
    struct vm_page *native;
    struct page *page;
    voff_t offset;
    int error;
    ASSERT_SLEEPABLE();
    if (index > ((uint64_t)INT64_MAX - PAGE_SIZE) >> PAGE_SHIFT ||
        (uint64_t)index >= howmany(backing ?
        (uint64_t)mapping->host->netbsd_backing_size :
        (uint64_t)i_size_read(mapping->host), PAGE_SIZE))
        return ERR_PTR(-EINVAL);
    offset = (voff_t)index << PAGE_SHIFT;
    error = linux_file_reservation_enter();
    if (error != 0)
        return ERR_PTR(-error);
    candidate = kmem_zalloc(sizeof(*candidate), KM_NOSLEEP);
    if (candidate == NULL) {
        linux_file_reservation_leave();
        return ERR_PTR(-ENOMEM);
    }
    uao_reference(object);
    error = linux_page_fetch_wire(object, offset, gfp, &native);
    if (error != 0) {
        uao_detach(object);
        kmem_free(candidate, sizeof(*candidate));
        linux_file_reservation_leave();
        return ERR_PTR(-error);
    }
    page = container_of(native, struct page, p_vmp);
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    if (owner == NULL) {
        for (owner = page_owners[linux_page_bucket(page)]; owner != NULL;
             owner = owner->next)
            if (owner->page == page && owner->paused)
                break;
    }
    if (owner != NULL) {
        if (owner->refs == UINT_MAX)
            panic("linux_page_wire_mapping: page reference overflow");
        owner->refs++;
        owner->paused = false;
        mutex_exit(&page_owner_lock);
        uvm_obj_unwirepages(object, offset, offset + PAGE_SIZE);
        uao_detach(object);
        kmem_free(candidate, sizeof(*candidate));
        linux_file_reservation_leave();
    } else {
        candidate->page = page;
        candidate->mapping = mapping;
        candidate->object = object;
        candidate->offset = offset;
        candidate->index = index;
        candidate->refs = 1;
        candidate->folio.netbsd_page = page;
        candidate->folio.mapping = mapping;
        candidate->folio.index = index;
        candidate->next = page_owners[linux_page_bucket(page)];
        page_owners[linux_page_bucket(page)] = candidate;
        page_owner_count++;
        mutex_exit(&page_owner_lock);
    }
    return page;
}

struct page *
linux_page_wire_mapping_locked(struct linux_address_space *mapping, linux_pgoff_t index,
    gfp_t gfp)
{
    return linux_page_wire_common(mapping, index, gfp, false);
}

struct page *
linux_page_wire_backing_locked(struct linux_address_space *mapping, linux_pgoff_t index,
    gfp_t gfp)
{
    KASSERT(mutex_owned(&mapping->host->netbsd_size_lock));
    return linux_page_wire_common(mapping, index, gfp, true);
}

struct page *
linux_page_wire_mapping(struct linux_address_space *mapping, linux_pgoff_t index,
    gfp_t gfp)
{
    struct page *page;
    down_read(&mapping->invalidate_lock);
    page = linux_page_wire_mapping_locked(mapping, index, gfp);
    up_read(&mapping->invalidate_lock);
    return page;
}

void
linux_page_get(struct page *page)
{
    struct linux_page_owner *owner;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    if (owner == NULL || owner->refs == UINT_MAX)
        panic("get_page: missing or saturated native page owner");
    owner->refs++;
    mutex_exit(&page_owner_lock);
}

void
linux_page_put(struct page *page)
{
    struct linux_page_owner *owner;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    if (owner == NULL)
        panic("put_page: no live native page reference");
    if (--owner->refs != 0) {
        mutex_exit(&page_owner_lock);
        return;
    }
    mutex_exit(&page_owner_lock);
    /* All memory and native queue bookkeeping were allocated at adoption. */
    workqueue_enqueue(page_release_queue, &owner->work, NULL);
}

unsigned int
linux_page_count(struct page *page)
{
    struct linux_page_owner *owner;
    unsigned int refs;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    refs = owner != NULL ? owner->refs : 0;
    mutex_exit(&page_owner_lock);
    return refs;
}

struct linux_address_space *
linux_page_mapping(struct page *page)
{
    struct linux_page_owner *owner;
    struct linux_address_space *mapping;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    mapping = owner != NULL ? owner->mapping : NULL;
    mutex_exit(&page_owner_lock);
    return mapping;
}

linux_pgoff_t
linux_page_index(struct page *page)
{
    struct linux_page_owner *owner;
    linux_pgoff_t index;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    if (owner == NULL)
        panic("page_index: no live native page owner");
    index = owner->index;
    mutex_exit(&page_owner_lock);
    return index;
}

int
linux_page_set_dirty(struct page *page)
{
    struct linux_page_owner *owner;
    struct uvm_object *object;
    struct vm_page *native = &page->p_vmp;
    int changed;
    ASSERT_SLEEPABLE();
    for (;;) {
        mutex_enter(&page_owner_lock);
        owner = linux_page_find(page);
        if (owner == NULL)
            panic("set_page_dirty: missing native page owner");
        object = owner->object;
        uao_reference(object);
        mutex_exit(&page_owner_lock);
        rw_enter(object->vmobjlock, RW_WRITER);
        mutex_enter(&page_owner_lock);
        if (owner->object != object) {
            mutex_exit(&page_owner_lock);
            rw_exit(object->vmobjlock);
            uao_detach(object);
            continue;
        }
        mutex_exit(&page_owner_lock);
        changed = (native->flags & PG_CLEAN) != 0;
        if (owner->detached) {
            /* Removed from UVM's object/dirty counters. The private wired
             * page still has real bytes, but no page-cache writeback owner. */
            uvm_pagelock(native);
            native->flags = (native->flags & ~PG_CLEAN) | PG_DIRTY;
            uvm_pageunlock(native);
        } else {
            uvm_pagemarkdirty(native, UVM_PAGE_STATUS_DIRTY);
            uao_dropswap(object, native->offset >> PAGE_SHIFT);
        }
        rw_exit(object->vmobjlock);
        uao_detach(object);
        return changed;
    }
}

void
linux_page_mapping_detach(struct linux_address_space *mapping)
{
    struct linux_page_owner *owner;
    unsigned int bucket;
    mutex_enter(&page_owner_lock);
    for (bucket = 0; bucket < LINUX_PAGE_BUCKETS; bucket++)
        for (owner = page_owners[bucket]; owner != NULL; owner = owner->next)
            if (owner->mapping == mapping) {
                owner->mapping = owner->folio.mapping = NULL;
                if (owner->paused) {
                    owner->paused = false;
                    workqueue_enqueue(page_release_queue, &owner->work, NULL);
                }
            }
    mutex_exit(&page_owner_lock);
}


struct linux_folio *
linux_page_folio(struct page *page)
{
    struct linux_page_owner *owner;
    struct linux_folio *folio;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    if (owner == NULL)
        panic("page_folio: no live native base-page owner");
    folio = &owner->folio;
    mutex_exit(&page_owner_lock);
    return folio;
}

unsigned long
linux_folio_pfn(const struct linux_folio *folio)
{
    return VM_PAGE_TO_PHYS(&folio->netbsd_page->p_vmp) >> PAGE_SHIFT;
}

void
linux_folio_mark_accessed(struct linux_folio *folio)
{
    struct linux_page_owner *owner;
    struct uvm_object *object;
    struct vm_page *native = &folio->netbsd_page->p_vmp;
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(folio->netbsd_page);
    if (owner == NULL)
        panic("folio_mark_accessed: no live native page owner");
    object = owner->object;
    uao_reference(object);
    mutex_exit(&page_owner_lock);
    rw_enter(object->vmobjlock, RW_WRITER);
    /* Native activation is deferred while wired; the actual last unwire
     * activates the page. This preserves the native page-queue contract. */
    uvm_pagelock(native);
    uvm_pageactivate(native);
    uvm_pageunlock(native);
    rw_exit(object->vmobjlock);
    uao_detach(object);
}

/*
 * Discard complete pages from an unmapped UAO. Partial byte edges are
 * handled by the shmem caller. Native UVM mlock/COW mappings require their
 * real per-entry revoke protocol first; EBUSY preserves all page data.
 * No allocations are made after preflight, including the pinned-page path.
 */
int
linux_page_discard_range_locked(struct linux_address_space *mapping, voff_t start,
    voff_t end)
{
    struct uvm_object *object = mapping->netbsd_uobj;
    struct uvm_page_array array;
    struct vm_page *native;
    struct linux_page_owner *owner;
    struct page *page;
    voff_t offset;
    unsigned int wires;
    int error = 0;

    ASSERT_SLEEPABLE();
    KASSERT(mutex_owned(&mapping->host->netbsd_size_lock));
    if ((start & (PAGE_SIZE - 1)) != 0 || (end & (PAGE_SIZE - 1)) != 0 ||
        start > end || end > mapping->host->netbsd_backing_size)
        return EINVAL;
    if (start == end)
        return 0;
    /* A pmap zap alone does not release native mlock wire ownership. Never
     * reassign those pages using a synthetic reference/count assumption. */
    if (mapping_mapped(mapping)) {
        return EBUSY;
    }
    rw_enter(object->vmobjlock, RW_WRITER);
    uvm_page_array_init(&array, object, 0);
    offset = start;
    while ((native = uvm_page_array_fill_and_peek(&array, offset, 0)) != NULL &&
        native->offset < end) {
        if ((native->flags & PG_BUSY) != 0 || native->loan_count != 0) {
            error = EBUSY;
            goto out;
        }
        page = container_of(native, struct page, p_vmp);
        wires = 0;
        mutex_enter(&page_owner_lock);
        for (owner = page_owners[linux_page_bucket(page)]; owner != NULL;
             owner = owner->next)
            if (owner->page == page && owner->object == object &&
                !owner->detached)
                wires++;
        mutex_exit(&page_owner_lock);
        if (native->wire_count != wires) {
            error = EBUSY;
            goto out;
        }
        offset = native->offset + PAGE_SIZE;
        uvm_page_array_advance(&array);
    }
    /* Object lock excludes native wiring/pageout; invalidate write lock
     * excludes new Linux page adoption until every old identity is gone. */
    uvm_page_array_clear(&array);
    offset = start;
    while ((native = uvm_page_array_fill_and_peek(&array, offset, 0)) != NULL &&
        native->offset < end) {
        offset = native->offset + PAGE_SIZE;
        uvm_page_array_advance(&array);
        page = container_of(native, struct page, p_vmp);
        pmap_page_protect(native, VM_PROT_NONE);
        if (native->wire_count == 0) {
            uao_dropswap(object, native->offset >> PAGE_SHIFT);
            uvm_pagefree(native);
            continue;
        }
        /* Public native reallocation removes the active radix identity
         * without allocating. The sidecars now own an actual private wired
         * page, equivalent to native caller-owned wired physical storage. */
        if (uvm_pagerealloc(native, NULL, 0) != 0)
            panic("linux_page_discard_range: native detach unexpectedly failed");
        uvm_pagelock(native);
        native->flags &= ~(PG_AOBJ | PG_FILE | PG_ANON);
        uvm_pageunlock(native);
        mutex_enter(&page_owner_lock);
        for (owner = page_owners[linux_page_bucket(page)]; owner != NULL;
             owner = owner->next) {
            if (owner->page == page && owner->object == object &&
                !owner->detached) {
                owner->mapping = owner->folio.mapping = NULL;
                owner->detached = true;
                if (owner->paused) {
                    owner->paused = false;
                    workqueue_enqueue(page_release_queue, &owner->work, NULL);
                }
            }
        }
        mutex_exit(&page_owner_lock);
    }
    uao_dropswap_range(object, start >> PAGE_SHIFT, end >> PAGE_SHIFT);
out:
    uvm_page_array_fini(&array);
    rw_exit(object->vmobjlock);
    return error;
}

int
linux_page_discard_range(struct linux_address_space *mapping, voff_t start,
    voff_t end)
{
    int error;
    mutex_enter(&mapping->host->netbsd_size_lock);
    down_write(&mapping->invalidate_lock);
    error = linux_page_discard_range_locked(mapping, start, end);
    up_write(&mapping->invalidate_lock);
    mutex_exit(&mapping->host->netbsd_size_lock);
    return error;
}

bool
linux_page_has_backing(struct linux_address_space *mapping, linux_pgoff_t index)
{
    struct uvm_object *object = mapping->netbsd_uobj;
    bool present;
    if (index > INT_MAX)
        return false;
    rw_enter(object->vmobjlock, RW_READER);
    present = uvm_pagelookup(object, (voff_t)index << PAGE_SHIFT) != NULL ||
        uao_find_swslot(object, (int)index) != 0;
    rw_exit(object->vmobjlock);
    return present;
}

void
linux_page_validate_wired(struct page *page)
{
    struct linux_page_owner *owner;
    struct uvm_object *object;
    struct vm_page *native = &page->p_vmp;
    ASSERT_SLEEPABLE();
retry:
    mutex_enter(&page_owner_lock);
    owner = linux_page_find(page);
    if (owner == NULL)
        panic("linux_page_validate_wired: no live page reference");
    object = owner->object;
    uao_reference(object);
    mutex_exit(&page_owner_lock);
    rw_enter(object->vmobjlock, RW_WRITER);
    mutex_enter(&page_owner_lock);
    if (owner->object != object) {
        mutex_exit(&page_owner_lock);
        rw_exit(object->vmobjlock);
        uao_detach(object);
        goto retry;
    }
    mutex_exit(&page_owner_lock);
    uvm_pagelock(native);
    if (native->wire_count == 0 ||
        (!owner->detached && native->uobject != object) ||
        (owner->detached && native->uobject != NULL))
        panic("linux_page_validate_wired: invalid native wire/object owner");
    uvm_pageunlock(native);
    rw_exit(object->vmobjlock);
    uao_detach(object);
}

void
mapping_clear_unevictable(struct linux_address_space *mapping)
{
    struct linux_page_owner *owner;
    unsigned int bucket;
    atomic_and_ulong(&mapping->flags, ~(1UL << AS_UNEVICTABLE));
    mutex_enter(&page_owner_lock);
    for (bucket = 0; bucket < LINUX_PAGE_BUCKETS; bucket++) {
        for (owner = page_owners[bucket]; owner != NULL; owner = owner->next) {
            if (owner->mapping == mapping && owner->paused) {
                if (owner->refs != 0)
                    panic("mapping_clear_unevictable: inconsistent paused owner");
                owner->paused = false;
                workqueue_enqueue(page_release_queue, &owner->work, NULL);
            }
        }
    }
    mutex_exit(&page_owner_lock);
}
