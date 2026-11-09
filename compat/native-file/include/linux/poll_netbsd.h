/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _NB_LINUX_POLL_NETBSD_H_
#define _NB_LINUX_POLL_NETBSD_H_
#include <sys/atomic.h>
#include <linux/fs_netbsd.h>
#include <linux/wait.h>

/* Frozen fd179f8a uapi eventpoll.h. Native sys/poll.h remains native: in
 * particular its POLLWRNORM/POLLWRBAND values are different. */
#ifndef EPOLLIN
#define EPOLLIN ((__poll_t)0x00000001U)
#define EPOLLPRI ((__poll_t)0x00000002U)
#define EPOLLOUT ((__poll_t)0x00000004U)
#define EPOLLERR ((__poll_t)0x00000008U)
#define EPOLLHUP ((__poll_t)0x00000010U)
#define EPOLLNVAL ((__poll_t)0x00000020U)
#define EPOLLRDNORM ((__poll_t)0x00000040U)
#define EPOLLRDBAND ((__poll_t)0x00000080U)
#define EPOLLWRNORM ((__poll_t)0x00000100U)
#define EPOLLWRBAND ((__poll_t)0x00000200U)
#define EPOLLMSG ((__poll_t)0x00000400U)
#define EPOLLRDHUP ((__poll_t)0x00002000U)
#endif
#ifndef POLLFREE
#define POLLFREE ((__poll_t)0x4000U)
#endif
#define LINUX_POLLWRNORM 0x0100U
#define LINUX_POLLWRBAND 0x0200U
#define DEFAULT_POLLMASK (EPOLLIN | EPOLLOUT | EPOLLRDNORM | EPOLLWRNORM)
typedef void (*poll_queue_proc)(struct linux_file *, wait_queue_head_t *,
    struct poll_table_struct *);
typedef struct poll_table_struct {
    poll_queue_proc _qproc;
    __poll_t _key;
} poll_table;
static inline void
poll_wait(struct linux_file *file, wait_queue_head_t *address, poll_table *table)
{
    if (table != NULL && table->_qproc != NULL) {
        table->_qproc(file, address, table);
        membar_sync();
    }
}
static inline __poll_t poll_requested_events(const poll_table *table)
{ return table != NULL ? table->_key : ~(__poll_t)0; }
static inline void init_poll_funcptr(poll_table *table, poll_queue_proc callback)
{ table->_qproc = callback; table->_key = ~(__poll_t)0; }
static inline bool file_can_poll(struct linux_file *file)
{ return file->f_op->poll != NULL; }
static inline __poll_t vfs_poll(struct linux_file *file, poll_table *table)
{ return file_can_poll(file) ? file->f_op->poll(file, table) : DEFAULT_POLLMASK; }
#endif

