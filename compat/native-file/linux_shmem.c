/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/fcntl.h>
#include <sys/file.h>
#include <sys/kmem.h>
#include <sys/mutex.h>
#include <sys/rwlock.h>
#include <sys/stat.h>
#include <sys/systm.h>
#include <sys/uio.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_object.h>
#include <uvm/uvm_page.h>
#include <uvm/uvm_page_array.h>
#include <uvm/uvm_pager.h>
#include <linux/err.h>
#include <linux/file_netbsd.h>
#include <linux/shmem_fs_netbsd.h>

/* Exact expanded declarations from frozen Native linux/highmem.h. Importing
 * that legacy convenience header also imports the legacy Linux MM namespace
 * and redefines PAGE_MASK. Call the existing native provider explicitly;
 * this declares no modern Linux highmem or local-map ABI. */
void *linux_kmap(struct page *);
void linux_kunmap(struct page *);

static ssize_t linux_shmem_read_iter(struct kiocb *, struct iov_iter *);
static ssize_t linux_shmem_write_iter(struct kiocb *, struct iov_iter *);
static loff_t linux_shmem_llseek(struct linux_file *, loff_t, int);
static const struct file_operations linux_shmem_operations = {
    .llseek = linux_shmem_llseek,
    .read_iter = linux_shmem_read_iter,
    .write_iter = linux_shmem_write_iter,
    .mmap = linux_shmem_mmap,
    .get_unmapped_area = linux_shmem_get_unmapped_area,
};
static volatile uint64_t shmem_inode_number = 2;

bool
linux_shmem_file(const struct linux_file *file)
{
    return file != NULL && file->f_op == &linux_shmem_operations;
}

bool
shmem_mapping(const struct linux_address_space *mapping)
{
    return mapping != NULL && mapping->host != NULL &&
        mapping->host->netbsd_shmem;
}

struct linux_file *
shmem_file_setup(const char *name, loff_t size, vma_flags_t flags)
{
    struct linux_inode *inode;
    struct linux_file *file;
    uint64_t number;
    int error;
    number = atomic_inc_64_nv(&shmem_inode_number);
    if (number < 3)
        panic("shmem_file_setup: inode identity exhausted");
    inode = linux_inode_alloc_size(0, number, S_IFREG | 0777, size);
    if (IS_ERR(inode))
        return ERR_CAST(inode);
    inode->netbsd_shmem = true;
    inode->netbsd_noreserve = (flags.__vma_flags[0] & VM_NORESERVE) != 0;
    error = linux_shmem_commit_set(inode, size);
    if (error != 0) {
        iput(inode);
        return ERR_PTR(-error);
    }
    file = linux_file_alloc_named(inode, &linux_shmem_operations, NULL, O_RDWR, name);
    iput(inode); /* Private constructor retained its own inode on success. */
    return file;
}

struct page *
shmem_read_mapping_page_gfp(struct linux_address_space *mapping, linux_pgoff_t index,
    gfp_t gfp)
{
    if (!shmem_mapping(mapping))
        return ERR_PTR(-EINVAL);
    return linux_page_wire_mapping(mapping, index, gfp);
}

struct linux_folio *
shmem_read_folio_gfp(struct linux_address_space *mapping, linux_pgoff_t index, gfp_t gfp)
{
    struct page *page = shmem_read_mapping_page_gfp(mapping, index, gfp);
    return IS_ERR(page) ? ERR_CAST(page) : page_folio(page);
}

static loff_t
linux_shmem_llseek(struct linux_file *file, loff_t offset, int whence)
{
    loff_t base;
    switch (whence) {
    case SEEK_SET: base = 0; break;
    case SEEK_CUR: base = file->f_pos; break;
    case SEEK_END: base = i_size_read(file->f_inode); break;
    default: return -EINVAL;
    }
    if ((offset > 0 && base > INT64_MAX - offset) ||
        (offset < 0 && (uint64_t)base < 0 - (uint64_t)offset))
        return -EINVAL;
    offset += base;
    if (offset < 0)
        return -EINVAL;
    file->f_pos = offset;
    return offset;
}

static ssize_t
linux_shmem_iter(struct kiocb *iocb, struct iov_iter *iter, bool writing)
{
    struct linux_file *file = iocb->ki_filp;
    struct linux_inode *inode = file->f_inode;
    struct linux_address_space *mapping = file->f_mapping;
    struct page *page;
    void *address;
    char *bounce = NULL;
    loff_t position, size;
    size_t requested = iov_iter_count(iter), done = 0, length, copied, in_page;
    int error = 0;

    ASSERT_SLEEPABLE();
    if (!shmem_mapping(mapping) || !is_sync_kiocb(iocb) ||
        (writing ? !iter->data_source : iter->data_source))
        return -EINVAL;
    /* UAO has no Linux direct-I/O or async page-wait submission interface.
     * These explicit request modes are rejected rather than simulated. */
    if (iocb->ki_flags & (IOCB_DIRECT | IOCB_ATOMIC | IOCB_WAITQ))
        return -EOPNOTSUPP;
    if ((iocb->ki_flags & IOCB_NOWAIT) != 0)
        return -EAGAIN;
    if (requested > SSIZE_MAX || iocb->ki_pos < 0 ||
        requested > (uint64_t)INT64_MAX - (uint64_t)iocb->ki_pos)
        return -EINVAL;
    if (requested == 0)
        return 0;
    if (requested != 0) {
        bounce = kmem_alloc(PAGE_SIZE, KM_NOSLEEP);
        if (bounce == NULL)
            return -ENOMEM;
    }
    mutex_enter(&inode->netbsd_size_lock);
    position = writing && (iocb->ki_flags & IOCB_APPEND) ?
        i_size_read(inode) : iocb->ki_pos;
    if (requested > (uint64_t)INT64_MAX - (uint64_t)position) {
        error = EFBIG;
        goto out_size;
    }
    if (writing) {
        error = linux_inode_ensure_capacity_locked(inode, position + requested);
        if (error != 0)
            goto out_size;
    }
    down_read(&mapping->invalidate_lock);
    while (done < requested) {
        size = i_size_read(inode);
        if (!writing && position >= size)
            break;
        in_page = (size_t)position & (PAGE_SIZE - 1);
        length = MIN(PAGE_SIZE - in_page, requested - done);
        if (!writing)
            length = MIN(length, (size_t)(size - position));
        page = writing ? linux_page_wire_backing_locked(mapping,
            (linux_pgoff_t)position >> PAGE_SHIFT, mapping_gfp_mask(mapping)) :
            linux_page_wire_mapping_locked(mapping,
            (linux_pgoff_t)position >> PAGE_SHIFT, mapping_gfp_mask(mapping));
        if (IS_ERR(page)) {
            error = (int)-PTR_ERR(page);
            break;
        }
        address = linux_kmap(page);
        if (address == NULL) {
            put_page(page);
            error = ENOMEM;
            break;
        }
        if (writing) {
            /* A same-file user buffer may fault through the native entry
             * guard. Never recursively hold invalidate across usercopy.
             * Size mutex + real page wire/kmap retain the byte owner. */
            up_read(&mapping->invalidate_lock);
            copied = copy_from_iter(bounce, length, iter);
            down_read(&mapping->invalidate_lock);
            /* A failed copy modifies only the private bounce buffer. The
             * confirmed prefix is committed to actual page bytes once. */
            if (copied != 0) {
                memcpy((char *)address + in_page, bounce, copied);
                (void)set_page_dirty(page);
            }
        } else {
            memcpy(bounce, (char *)address + in_page, length);
            up_read(&mapping->invalidate_lock);
            copied = copy_to_iter(bounce, length, iter);
            down_read(&mapping->invalidate_lock);
        }
        linux_kunmap(page);
        put_page(page);
        position += copied;
        done += copied;
        if (copied != length) {
            error = EFAULT;
            break;
        }
    }
    iocb->ki_pos = position;
    up_read(&mapping->invalidate_lock);
    if (writing && done != 0 && position > i_size_read(inode)) {
        down_write(&mapping->invalidate_lock);
        atomic_store_release((volatile uint64_t *)&inode->i_size, (uint64_t)position);
        up_write(&mapping->invalidate_lock);
    }
out_size:
    if (writing)
        (void)linux_shmem_commit_set(inode, i_size_read(inode));
    mutex_exit(&inode->netbsd_size_lock);
    if (bounce != NULL)
        kmem_free(bounce, PAGE_SIZE);
    return done != 0 ? (ssize_t)done : -(ssize_t)error;
}

static ssize_t
linux_shmem_read_iter(struct kiocb *iocb, struct iov_iter *iter)
{
    return linux_shmem_iter(iocb, iter, false);
}
static ssize_t
linux_shmem_write_iter(struct kiocb *iocb, struct iov_iter *iter)
{
    return linux_shmem_iter(iocb, iter, true);
}

int
linux_shmem_native_io(struct linux_file *file, off_t *offset, struct uio *uio,
    int flags, bool writing)
{
    struct linux_inode *inode = file->f_inode;
    struct linux_address_space *mapping = file->f_mapping;
    struct page *page;
    char *bounce = NULL;
    void *address;
    loff_t position, size;
    size_t original = uio->uio_resid, before, copied, length, in_page;
    int error = 0;

    ASSERT_SLEEPABLE();
    if (original > SSIZE_MAX || *offset < 0)
        return EINVAL;
    if (original == 0)
        return 0;
    if (uio->uio_iovcnt <= 0)
        return EINVAL;
    bounce = kmem_alloc(PAGE_SIZE, KM_NOSLEEP);
    if (bounce == NULL)
        return ENOMEM;
    mutex_lock(&file->f_pos_lock);
    mutex_enter(&inode->netbsd_size_lock);
    position = (flags & FOF_UPDATE_OFFSET) ? file->f_pos : *offset;
    if (writing && (file->f_flags & O_APPEND))
        position = i_size_read(inode);
    if (position < 0 || original > (uint64_t)INT64_MAX - (uint64_t)position) {
        error = EINVAL;
        goto out_size;
    }
    if (writing) {
        error = linux_inode_ensure_capacity_locked(inode, position + original);
        if (error != 0)
            goto out_size;
    }
    down_read(&mapping->invalidate_lock);
    while (uio->uio_resid != 0) {
        size = i_size_read(inode);
        if (!writing && position >= size)
            break;
        in_page = (size_t)position & (PAGE_SIZE - 1);
        length = MIN(PAGE_SIZE - in_page, uio->uio_resid);
        if (!writing)
            length = MIN(length, (size_t)(size - position));
        page = writing ? linux_page_wire_backing_locked(mapping,
            (linux_pgoff_t)position >> PAGE_SHIFT, mapping_gfp_mask(mapping)) :
            linux_page_wire_mapping_locked(mapping,
            (linux_pgoff_t)position >> PAGE_SHIFT, mapping_gfp_mask(mapping));
        if (IS_ERR(page)) {
            error = (int)-PTR_ERR(page);
            break;
        }
        before = uio->uio_resid;
        uio->uio_offset = position;
        address = linux_kmap(page);
        if (address == NULL) {
            put_page(page);
            error = ENOMEM;
            break;
        }
        if (writing) {
            up_read(&mapping->invalidate_lock);
            error = uiomove(bounce, length, uio);
            down_read(&mapping->invalidate_lock);
            copied = before - uio->uio_resid;
            if (copied != 0) {
                memcpy((char *)address + in_page, bounce, copied);
                (void)set_page_dirty(page);
            }
        } else {
            memcpy(bounce, (char *)address + in_page, length);
            up_read(&mapping->invalidate_lock);
            error = uiomove(bounce, length, uio);
            down_read(&mapping->invalidate_lock);
            copied = before - uio->uio_resid;
        }
        linux_kunmap(page);
        put_page(page);
        position += copied;
        if (error != 0 || copied != length)
            break;
    }
    if (flags & FOF_UPDATE_OFFSET)
        file->f_pos = position;
    *offset = position;
    uio->uio_offset = position;
    up_read(&mapping->invalidate_lock);
    if (writing && original != uio->uio_resid && position > i_size_read(inode)) {
        down_write(&mapping->invalidate_lock);
        atomic_store_release((volatile uint64_t *)&inode->i_size, (uint64_t)position);
        up_write(&mapping->invalidate_lock);
    }
out_size:
    if (writing)
        (void)linux_shmem_commit_set(inode, i_size_read(inode));
    mutex_exit(&inode->netbsd_size_lock);
    mutex_unlock(&file->f_pos_lock);
    if (bounce != NULL)
        kmem_free(bounce, PAGE_SIZE);
    return original != uio->uio_resid ? 0 : error;
}

/* This native API can report a busy mapping before the driver marks an
 * object purged. Callers must propagate it; the Linux void helper cannot. */
int
linux_shmem_truncate_range(struct linux_inode *inode, loff_t start, uint64_t end)
{
    struct linux_address_space *mapping = inode->i_mapping;
    struct page *first_page = NULL, *last_page = NULL;
    void *first_address = NULL, *last_address = NULL;
    voff_t limit, first, stop, full_first, full_stop;
    size_t first_offset = 0, first_length = 0, last_length = 0;
    linux_pgoff_t first_index, last_index;
    int error = 0;

    ASSERT_SLEEPABLE();
    if (!inode->netbsd_shmem || start < 0 || end < (uint64_t)start)
        return EINVAL;
    mutex_enter(&inode->netbsd_size_lock);
    limit = inode->netbsd_backing_size;
    first = MIN((voff_t)start, limit);
    stop = end >= (uint64_t)limit - 1 ? limit : (voff_t)end + 1;
    if (first >= stop)
        goto out_size;
    down_write(&mapping->invalidate_lock);
    if (mapping_mapped(mapping)) {
        error = EBUSY;
        goto out_mapping;
    }
    first_index = (linux_pgoff_t)first >> PAGE_SHIFT;
    last_index = ((linux_pgoff_t)stop - 1) >> PAGE_SHIFT;
    if ((first & (PAGE_SIZE - 1)) != 0 &&
        linux_page_has_backing(mapping, first_index)) {
        first_page = linux_page_wire_backing_locked(mapping, first_index,
            mapping_gfp_mask(mapping));
        if (IS_ERR(first_page)) {
            error = (int)-PTR_ERR(first_page);
            first_page = NULL;
            goto out_mapping;
        }
        first_address = linux_kmap(first_page);
        if (first_address == NULL) {
            error = ENOMEM;
            goto out_mapping;
        }
        first_offset = (size_t)first & (PAGE_SIZE - 1);
        first_length = MIN((size_t)(stop - first), PAGE_SIZE - first_offset);
    }
    if ((stop & (PAGE_SIZE - 1)) != 0 &&
        (last_index != first_index || (first & (PAGE_SIZE - 1)) == 0) &&
        linux_page_has_backing(mapping, last_index)) {
        last_page = linux_page_wire_backing_locked(mapping, last_index,
            mapping_gfp_mask(mapping));
        if (IS_ERR(last_page)) {
            error = (int)-PTR_ERR(last_page);
            last_page = NULL;
            goto out_mapping;
        }
        last_address = linux_kmap(last_page);
        if (last_address == NULL) {
            error = ENOMEM;
            goto out_mapping;
        }
        last_length = (size_t)stop & (PAGE_SIZE - 1);
    }
    full_first = (first + (PAGE_SIZE - 1)) & ~(voff_t)(PAGE_SIZE - 1);
    full_stop = stop & ~(voff_t)(PAGE_SIZE - 1);
    if (full_first > full_stop)
        full_first = full_stop;
    /* All fallible edge preparation precedes discard. The full-range
     * routine preflights every target before removing any page identity.
     * After it succeeds, only kernel-memory memset/dirty updates remain. */
    error = linux_page_discard_range_locked(mapping, full_first, full_stop);
    if (error != 0)
        goto out_mapping;
    if (first_address != NULL) {
        memset((char *)first_address + first_offset, 0, first_length);
        (void)set_page_dirty(first_page);
    }
    if (last_address != NULL) {
        memset(last_address, 0, last_length);
        (void)set_page_dirty(last_page);
    }
out_mapping:
    if (last_address != NULL)
        linux_kunmap(last_page);
    if (first_address != NULL)
        linux_kunmap(first_page);
    if (last_page != NULL)
        put_page(last_page);
    if (first_page != NULL)
        put_page(first_page);
    up_write(&mapping->invalidate_lock);
out_size:
    mutex_exit(&inode->netbsd_size_lock);
    return error;
}

void
linux_shmem_writeback(struct linux_address_space *mapping)
{
    struct uvm_object *object = mapping->netbsd_uobj;
    /* Real UAO clean/deactivate gives the native pagedaemon ownership of
     * reclaim. It does not claim Linux writeback_iter/xarray/LRU parity. */
    rw_enter(object->vmobjlock, RW_WRITER);
    (void)(*object->pgops->pgo_put)(object, 0, 0,
        PGO_CLEANIT | PGO_DEACTIVATE | PGO_ALLPAGES);
}

