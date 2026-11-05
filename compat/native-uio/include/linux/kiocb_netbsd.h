/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef _NB_LINUX_KIOCB_H_
#define _NB_LINUX_KIOCB_H_
#include <linux/types.h>
struct linux_file;
struct wait_page_queue;
/* Source adapter to the synchronous pinned Linux callback interface.
 * No Linux object-layout or async submission/completion ABI is asserted. */
struct kiocb {
    struct linux_file *ki_filp;
    loff_t ki_pos;
    void (*ki_complete)(struct kiocb *, long);
    void *private;
    int ki_flags;
    u16 ki_ioprio;
    u8 ki_write_stream;
    struct wait_page_queue *ki_waitq;
};
/* Values from fd179f8 include/linux/fs.h + include/uapi/linux/fs.h. */
#define IOCB_HIPRI       0x00000001
#define IOCB_DSYNC       0x00000002
#define IOCB_SYNC        0x00000004
#define IOCB_NOWAIT      0x00000008
#define IOCB_APPEND      0x00000010
#define IOCB_ATOMIC      0x00000040
#define IOCB_DONTCACHE   0x00000080
#define IOCB_NOSIGNAL    0x00000100
#define IOCB_EVENTFD     (1 << 16)
#define IOCB_DIRECT      (1 << 17)
#define IOCB_WRITE       (1 << 18)
#define IOCB_WAITQ       (1 << 19)
#define IOCB_NOIO        (1 << 20)
#define IOCB_ALLOC_CACHE (1 << 21)
#define IOCB_AIO_RW      (1 << 22)
#define IOCB_HAS_METADATA (1 << 23)
void init_sync_kiocb(struct kiocb *, struct linux_file *);
static inline bool is_sync_kiocb(struct kiocb *iocb)
{
    return iocb->ki_complete == NULL;
}
#endif
