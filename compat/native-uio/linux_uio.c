/* SPDX-License-Identifier: BSD-2-Clause */
/* Source adapters, not Linux object-layout or asynchronous I/O emulation. */
#ifdef NATIVE_UIO_TEST
#include "test_model.h"
#else
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/fcntl.h>
#include <sys/proc.h>
#include <sys/systm.h>
#include <machine/vmparam.h>
#include <linux/fs_netbsd.h>
#endif
#include <linux/uio_netbsd.h>

static bool
linux_uio_range(const void *buffer, size_t bytes, bool user)
{
    uintptr_t address = (uintptr_t)buffer;

    if (bytes == 0)
        return true;
    if (bytes > UINTPTR_MAX - address)
        return false;
    if (user)
        return address < VM_MAXUSER_ADDRESS &&
            bytes <= (uintptr_t)VM_MAXUSER_ADDRESS - address;
    /* Actual mapping/protection faults are handled by Native kcopy below;
     * excluding user addresses prevents a KVEC from relabelling user memory. */
    return address >= VM_MAXUSER_ADDRESS;
}

void
init_sync_kiocb(struct kiocb *iocb, struct linux_file *file)
{
    unsigned int flags;
    int iocb_flags = 0;

    if (iocb == NULL || file == NULL)
        panic("init_sync_kiocb: missing native file/request");
    flags = atomic_load_relaxed(&file->f_flags);
    if (flags & O_APPEND) iocb_flags |= IOCB_APPEND;
    if (flags & O_DIRECT) iocb_flags |= IOCB_DIRECT;
    if (flags & O_DSYNC) iocb_flags |= IOCB_DSYNC;
    if (flags & O_SYNC) iocb_flags |= IOCB_SYNC | IOCB_DSYNC;
    *iocb = (struct kiocb) { .ki_filp = file, .ki_flags = iocb_flags };
    /* ki_complete NULL is synchronous. ki_ioprio=0 is no explicit Linux
     * override: the real Native backend retains Native scheduling policy.
     * Linux task ioprio inheritance and asynchronous submission are OPEN. */
}

static void
linux_iter_check(const struct iov_iter *iter)
{
    if (iter == NULL || (iter->iter_type != ITER_UBUF && iter->iter_type != ITER_KVEC) ||
        iter->netbsd_consumed > iter->netbsd_capacity ||
        iter->count > iter->netbsd_capacity - iter->netbsd_consumed)
        panic("native iov_iter: invalid or unsupported owner");
}

void
iov_iter_ubuf(struct iov_iter *iter, unsigned int direction, void *buffer, size_t count)
{
    ASSERT_SLEEPABLE();
    if (iter == NULL || direction > ITER_SOURCE)
        panic("iov_iter_ubuf: invalid direction/iterator");
    *iter = (struct iov_iter) { .iter_type = ITER_UBUF,
        .data_source = direction, .ubuf = buffer, .count = count, .nr_segs = 1,
        .netbsd_capacity = count, .netbsd_vmspace = curproc->p_vmspace };
}

void
iov_iter_kvec(struct iov_iter *iter, unsigned int direction,
    const struct kvec *vectors, unsigned long segments, size_t count)
{
    size_t total = 0;
    unsigned long segment;
    struct kvec vector;

    ASSERT_SLEEPABLE();
    if (iter == NULL || direction > ITER_SOURCE || segments > SIZE_MAX / sizeof(*vectors) ||
        !linux_uio_range(vectors, segments * sizeof(*vectors), false))
        panic("iov_iter_kvec: invalid kernel vector owner");
    for (segment = 0; segment < segments; segment++) {
        if (kcopy(vectors + segment, &vector, sizeof(vector)) != 0)
            panic("iov_iter_kvec: inaccessible vector owner");
        if (vector.iov_len > SIZE_MAX - total)
            panic("iov_iter_kvec: overflowing vector lengths");
        total += vector.iov_len;
    }
    if (count > total)
        panic("iov_iter_kvec: count exceeds borrowed vectors");
    *iter = (struct iov_iter) { .iter_type = ITER_KVEC,
        .data_source = direction, .kvec = vectors, .count = count, .nr_segs = segments,
        .netbsd_vectors = vectors, .netbsd_vector_count = segments, .netbsd_capacity = count };
}

/* Reconstruct from the owned original vector range. No pointer arithmetic
 * before its beginning when reverting across empty or fully consumed vectors. */
static void
linux_iter_position(struct iov_iter *iter)
{
    size_t skip = iter->netbsd_consumed;
    unsigned long segment = 0;

    if (iter_is_ubuf(iter)) {
        iter->iov_offset = skip;
        return;
    }
    while (segment < iter->netbsd_vector_count &&
        skip >= iter->netbsd_vectors[segment].iov_len) {
        skip -= iter->netbsd_vectors[segment].iov_len;
        segment++;
    }
    iter->kvec = iter->netbsd_vectors == NULL ? NULL : iter->netbsd_vectors + segment;
    iter->nr_segs = iter->netbsd_vector_count - segment;
    iter->iov_offset = skip;
}

void
iov_iter_advance(struct iov_iter *iter, size_t bytes)
{
    linux_iter_check(iter);
    bytes = MIN(bytes, iter->count);
    iter->netbsd_consumed += bytes;
    iter->count -= bytes;
    linux_iter_position(iter);
}

void
iov_iter_revert(struct iov_iter *iter, size_t bytes)
{
    linux_iter_check(iter);
    if (bytes == 0)
        return;
    if (bytes > iter->netbsd_consumed || bytes > SIZE_MAX - iter->count)
        panic("iov_iter_revert: before borrowed range");
    iter->netbsd_consumed -= bytes;
    iter->count += bytes;
    linux_iter_position(iter);
}

void
iov_iter_truncate(struct iov_iter *iter, u64 count)
{
    linux_iter_check(iter);
    if (count < iter->count)
        iter->count = (size_t)count;
}

void
iov_iter_reexpand(struct iov_iter *iter, size_t count)
{
    linux_iter_check(iter);
    if (count > iter->netbsd_capacity - iter->netbsd_consumed)
        panic("iov_iter_reexpand: outside borrowed range");
    iter->count = count;
}

size_t
iov_iter_single_seg_count(const struct iov_iter *iter)
{
    linux_iter_check(iter);
    if (iter_is_ubuf(iter))
        return iter->count;
    if (iter->nr_segs == 0)
        return 0;
    return MIN(iter->count, iter->kvec->iov_len - iter->iov_offset);
}

/* Native copyin/out return errno, not a residual. On a failed bulk copy,
 * confirm the prefix byte by byte so only confirmed transfers are advanced.
 * As with Linux raw usercopy, this is ordinary memory, not MMIO access. */
static size_t
linux_user_copy(void *kernel, void *user, size_t bytes, bool writing)
{
    size_t done;
    int error;

    error = writing ? copyout(kernel, user, bytes) : copyin(user, kernel, bytes);
    if (error == 0)
        return bytes;
    for (done = 0; done < bytes; done++) {
        error = writing ? copyout((char *)kernel + done, (char *)user + done, 1) :
            copyin((char *)user + done, (char *)kernel + done, 1);
        if (error != 0)
            break;
    }
    return done;
}

static size_t
linux_kernel_copy(void *to, const void *from, size_t bytes)
{
    size_t done;

    if (kcopy(from, to, bytes) == 0)
        return bytes;
    for (done = 0; done < bytes; done++)
        if (kcopy((const char *)from + done, (char *)to + done, 1) != 0)
            break;
    return done;
}

static size_t
linux_iter_copy(void *kernel, size_t bytes, struct iov_iter *iter, bool writing)
{
    size_t done = 0, requested;

    ASSERT_SLEEPABLE();
    linux_iter_check(iter);
    if (iter->data_source == writing || iter->nofault)
        return 0;
    requested = MIN(bytes, iter->count);
    if (!linux_uio_range(kernel, requested, false))
        return 0;
    if (iter_is_ubuf(iter) && iter->netbsd_vmspace != curproc->p_vmspace)
        return 0;
    while (done < requested) {
        size_t length = MIN(requested - done, iov_iter_single_seg_count(iter));
        void *buffer;

        if (length == 0) {
            if (iter_is_ubuf(iter) || iter->nr_segs == 0)
                break;
            linux_iter_position(iter);
            continue;
        }
        if (iter_is_ubuf(iter)) {
            uintptr_t base = (uintptr_t)iter->ubuf;
            if (iter->iov_offset > UINTPTR_MAX - base)
                break;
            buffer = (void *)(base + iter->iov_offset);
            length = MIN(length, (size_t)PAGE_SIZE -
                ((uintptr_t)buffer & ((size_t)PAGE_SIZE - 1)));
            if (!linux_uio_range(buffer, length, true))
                break;
            size_t copied = linux_user_copy((char *)kernel + done, buffer, length, writing);
            iov_iter_advance(iter, copied);
            done += copied;
            if (copied != length)
                break;
        } else {
            uintptr_t base = (uintptr_t)iter->kvec->iov_base;
            if (iter->iov_offset > UINTPTR_MAX - base)
                break;
            buffer = (void *)(base + iter->iov_offset);
            length = MIN(length, (size_t)PAGE_SIZE);
            if (!linux_uio_range(buffer, length, false))
                break;
            size_t copied = writing ? linux_kernel_copy(buffer, (char *)kernel + done, length) :
                linux_kernel_copy((char *)kernel + done, buffer, length);
            iov_iter_advance(iter, copied);
            done += copied;
            if (copied != length)
                break;
        }
    }
    return done;
}

size_t
copy_to_iter(const void *kernel, size_t bytes, struct iov_iter *iter)
{
    return linux_iter_copy(__UNCONST(kernel), bytes, iter, true);
}

size_t
copy_from_iter(void *kernel, size_t bytes, struct iov_iter *iter)
{
    return linux_iter_copy(kernel, bytes, iter, false);
}
