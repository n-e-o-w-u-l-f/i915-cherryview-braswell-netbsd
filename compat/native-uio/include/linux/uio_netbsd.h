/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef _NB_LINUX_UIO_H_
#define _NB_LINUX_UIO_H_
#include <sys/types.h>
#include <linux/types.h>
#include <linux/kiocb_netbsd.h>
struct vmspace;
struct kvec { void *iov_base; size_t iov_len; };
/* Preserve pinned enum and direction values; only UBUF/KVEC have providers. */
enum iter_type { ITER_UBUF, ITER_IOVEC, ITER_BVEC, ITER_KVEC,
    ITER_FOLIOQ, ITER_XARRAY, ITER_DISCARD };
#define ITER_SOURCE 1
#define ITER_DEST 0
struct iov_iter {
    u8 iter_type;
    bool nofault;
    bool data_source;
    size_t iov_offset;
    size_t count;
    unsigned long nr_segs;
    union { void *ubuf; const struct kvec *kvec; };
    /* Borrowed, synchronous owners. Do not retain beyond the caller's
     * native entry, vector storage, or buffer lifetime. No native layout cast. */
    struct vmspace *netbsd_vmspace;
    const struct kvec *netbsd_vectors;
    unsigned long netbsd_vector_count;
    size_t netbsd_capacity;
    size_t netbsd_consumed;
};
void iov_iter_ubuf(struct iov_iter *, unsigned int, void *, size_t);
void iov_iter_kvec(struct iov_iter *, unsigned int, const struct kvec *, unsigned long, size_t);
void iov_iter_advance(struct iov_iter *, size_t);
void iov_iter_revert(struct iov_iter *, size_t);
void iov_iter_truncate(struct iov_iter *, u64);
void iov_iter_reexpand(struct iov_iter *, size_t);
size_t copy_to_iter(const void *, size_t, struct iov_iter *);
size_t copy_from_iter(void *, size_t, struct iov_iter *);
size_t iov_iter_single_seg_count(const struct iov_iter *);
static inline size_t iov_iter_count(const struct iov_iter *i) { return i->count; }
static inline enum iter_type iov_iter_type(const struct iov_iter *i) { return i->iter_type; }
static inline bool iter_is_ubuf(const struct iov_iter *i) { return i->iter_type == ITER_UBUF; }
static inline bool iov_iter_is_kvec(const struct iov_iter *i) { return i->iter_type == ITER_KVEC; }
static inline bool user_backed_iter(const struct iov_iter *i) { return iter_is_ubuf(i); }
static inline bool copy_to_iter_full(const void *p, size_t n, struct iov_iter *i)
{
    size_t done = copy_to_iter(p, n, i);
    if (done == n) return true;
    iov_iter_revert(i, done);
    return false;
}
static inline bool copy_from_iter_full(void *p, size_t n, struct iov_iter *i)
{
    size_t done = copy_from_iter(p, n, i);
    if (done == n) return true;
    iov_iter_revert(i, done);
    return false;
}
#endif
