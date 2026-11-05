/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef _LINUX_MMAP_LOCK_NETBSD_H_
#define _LINUX_MMAP_LOCK_NETBSD_H_
#include <linux/mm_identity_netbsd.h>
/* The underlying Native map locks are non-interruptible; taking that real
 * lock to completion is a valid successful killable acquisition. */
static inline int mmap_write_lock_killable(struct mm_struct *mm)
{ mmap_write_lock(mm); return 0; }
static inline int mmap_read_lock_killable(struct mm_struct *mm)
{ mmap_read_lock(mm); return 0; }
#endif
