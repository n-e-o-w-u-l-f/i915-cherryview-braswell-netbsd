/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/mutex.h>
#include <sys/stat.h>
#include <sys/systm.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_object.h>
#include <uvm/uvm_pager.h>
#include <machine/vmparam.h>
#include <linux/err.h>
#include <linux/file_netbsd.h>
#include <linux/mapping_netbsd.h>
#include <linux/pagemap_netbsd.h>

/* Actual same-object UVM extension, native_aobj_grow.inc. */
int uao_grow(struct uvm_object *, voff_t);
int uao_set_pgfl_future(struct uvm_object *, int);

static struct linux_inode *
linux_inode_allocate(dev_t dev, uint64_t number, mode_t mode, loff_t size,
    bool admitted)
{
    struct linux_inode *inode;
    voff_t capacity;
    int error;
    ASSERT_SLEEPABLE();
    if (size < 0 || (uint64_t)size > (uint64_t)INT64_MAX - (PAGE_SIZE - 1))
        return ERR_PTR(-EINVAL);
    if ((uint64_t)size > (uint64_t)INT_MAX * PAGE_SIZE)
        return ERR_PTR(-EFBIG); /* Actual UAO pager uses int swap page indices. */
    if (admitted) {
        error = linux_file_reservation_enter();
        if (error != 0)
            return ERR_PTR(-error);
    }
    capacity = MAX((voff_t)PAGE_SIZE, (((voff_t)size + (PAGE_SIZE - 1)) & ~(voff_t)(PAGE_SIZE - 1)));
    inode = kmem_zalloc(sizeof(*inode), KM_NOSLEEP);
    if (inode == NULL) {
        if (admitted)
            linux_file_reservation_leave();
        return ERR_PTR(-ENOMEM);
    }
    mutex_init(&inode->netbsd_size_lock, MUTEX_DEFAULT, IPL_NONE);
    inode->i_mode = mode;
    inode->i_rdev = dev;
    inode->i_ino = number;
    inode->i_size = size;
    inode->netbsd_refs = 1;
    inode->netbsd_admitted = admitted;
    inode->netbsd_backing_size = capacity;
    inode->i_mapping = &inode->i_data;
    inode->i_data.host = inode;
    inode->i_data.gfp_mask = GFP_KERNEL;
    /* Frozen UAO flags are zero for normal use; allocation is KM_SLEEP. */
    inode->i_data.netbsd_uobj = uao_create(capacity, 0);
    error = linux_mapping_registry_init(&inode->i_data);
    if (error != 0) {
        (*inode->i_data.netbsd_uobj->pgops->pgo_detach)(inode->i_data.netbsd_uobj);
        mutex_destroy(&inode->netbsd_size_lock);
        kmem_free(inode, sizeof(*inode));
        if (admitted)
            linux_file_reservation_leave();
        return ERR_PTR(-error);
    }
    return inode;
}

struct linux_inode *
linux_inode_alloc_size(dev_t dev, uint64_t number, mode_t mode, loff_t size)
{
    return linux_inode_allocate(dev, number, mode, size, true);
}

struct linux_inode *
linux_inode_alloc_system(dev_t dev, uint64_t number, mode_t mode)
{
    return linux_inode_allocate(dev, number, mode, 0, false);
}

struct linux_inode *
linux_inode_alloc(dev_t dev, uint64_t number, mode_t mode)
{
    return linux_inode_alloc_size(dev, number, mode, 0);
}

void
ihold(struct linux_inode *inode)
{
    unsigned int count = atomic_load_relaxed(&inode->netbsd_refs), old;
    for (;;) {
        if (count == 0 || count == UINT_MAX)
            panic("ihold: invalid inode reference count");
        old = atomic_cas_uint(&inode->netbsd_refs, count, count + 1);
        if (old == count)
            return;
        count = old;
    }
}

void
iput(struct linux_inode *inode)
{
    unsigned int count, old;
    int error;
    bool admitted;
    if (inode == NULL)
        return;
    membar_release();
    count = atomic_load_relaxed(&inode->netbsd_refs);
    for (;;) {
        if (count == 0)
            panic("iput: inode reference underflow");
        old = atomic_cas_uint(&inode->netbsd_refs, count, count - 1);
        if (old == count)
            break;
        count = old;
    }
    if (count != 1)
        return;
    membar_acquire();
    ASSERT_SLEEPABLE();
    admitted = inode->netbsd_admitted;
    error = linux_mapping_registry_destroy(&inode->i_data);
    if (error != 0)
        panic("iput: live mappings retained after final inode drop");
    linux_page_mapping_detach(&inode->i_data);
    (void)linux_shmem_commit_set(inode, 0);
    (*inode->i_data.netbsd_uobj->pgops->pgo_detach)(inode->i_data.netbsd_uobj);
    mutex_destroy(&inode->netbsd_size_lock);
    kmem_free(inode, sizeof(*inode));
    if (admitted)
        linux_file_reservation_leave();
}

loff_t
i_size_read(const struct linux_inode *inode)
{
    return (loff_t)atomic_load_acquire((const volatile uint64_t *)&inode->i_size);
}

int
linux_inode_ensure_capacity_locked(struct linux_inode *inode, loff_t size)
{
    int error = 0;
    uint64_t previous_charge;
    ASSERT_SLEEPABLE();
    KASSERT(mutex_owned(&inode->netbsd_size_lock));
    if (size < 0 || (uint64_t)size > (uint64_t)INT64_MAX - (PAGE_SIZE - 1))
        return EINVAL;
    if ((uint64_t)size > (uint64_t)INT_MAX * PAGE_SIZE)
        return EFBIG;
    previous_charge = inode->netbsd_commit_pages;
    error = linux_shmem_commit_set(inode, MAX(size, i_size_read(inode)));
    if (error != 0)
        return error;
    if ((voff_t)size > inode->netbsd_backing_size) {
        error = uao_grow(inode->i_data.netbsd_uobj, (voff_t)size);
        if (error == 0)
            inode->netbsd_backing_size = (((voff_t)size + (PAGE_SIZE - 1)) & ~(voff_t)(PAGE_SIZE - 1));
    }
    if (error != 0)
        (void)linux_shmem_commit_set(inode, (loff_t)(previous_charge * PAGE_SIZE));
    return error;
}

int
linux_inode_resize(struct linux_inode *inode, loff_t size)
{
    int error;
    mutex_enter(&inode->netbsd_size_lock);
    down_write(&inode->i_mapping->invalidate_lock);
    error = linux_inode_ensure_capacity_locked(inode, size);
    if (error == 0) {
        atomic_store_release((volatile uint64_t *)&inode->i_size, (uint64_t)size);
        (void)linux_shmem_commit_set(inode, size);
    }
    up_write(&inode->i_mapping->invalidate_lock);
    mutex_exit(&inode->netbsd_size_lock);
    return error;
}

void
i_size_write(struct linux_inode *inode, loff_t size)
{
    int error = linux_inode_resize(inode, size);
    if (error != 0)
        panic("i_size_write: invalid inode size");
}

void
mapping_set_gfp_mask(struct linux_address_space *mapping, gfp_t mask)
{
    struct uvm_object *object = mapping->netbsd_uobj;
    int error;
    rw_enter(object->vmobjlock, RW_WRITER);
    error = uao_set_pgfl_future(object,
        (mask & __GFP_DMA32) ? VM_FREELIST_FIRST4G : VM_NFREELIST);
    if (error != 0)
        panic("mapping_set_gfp_mask: invalid native object policy");
    atomic_store_relaxed(&mapping->gfp_mask, mask);
    rw_exit(object->vmobjlock);
}

int
mapping_map_writable(struct linux_address_space *mapping)
{
    int count = atomic_read(&mapping->i_mmap_writable), old;
    for (;;) {
        if (count < 0)
            return -EPERM;
        if (count == INT_MAX)
            return -EOVERFLOW;
        old = atomic_cmpxchg(&mapping->i_mmap_writable, count, count + 1);
        if (old == count)
            return 0;
        count = old;
    }
}

void
mapping_unmap_writable(struct linux_address_space *mapping)
{
    int count = atomic_read(&mapping->i_mmap_writable), old;
    for (;;) {
        if (count <= 0)
            panic("mapping_unmap_writable: unbalanced writable mapping");
        old = atomic_cmpxchg(&mapping->i_mmap_writable, count, count - 1);
        if (old == count)
            return;
        count = old;
    }
}

int
mapping_deny_writable(struct linux_address_space *mapping)
{
    int count = atomic_read(&mapping->i_mmap_writable), old;
    for (;;) {
        if (count > 0)
            return -EBUSY;
        if (count == INT_MIN)
            return -EOVERFLOW;
        old = atomic_cmpxchg(&mapping->i_mmap_writable, count, count - 1);
        if (old == count)
            return 0;
        count = old;
    }
}

void
mapping_allow_writable(struct linux_address_space *mapping)
{
    int count = atomic_read(&mapping->i_mmap_writable), old;
    for (;;) {
        if (count >= 0)
            panic("mapping_allow_writable: unbalanced write denial");
        old = atomic_cmpxchg(&mapping->i_mmap_writable, count, count + 1);
        if (old == count)
            return;
        count = old;
    }
}
