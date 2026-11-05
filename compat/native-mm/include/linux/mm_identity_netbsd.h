/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _LINUX_MM_IDENTITY_NETBSD_H_
#define _LINUX_MM_IDENTITY_NETBSD_H_

#include <sys/types.h>
#include <sys/workqueue.h>
#include <linux/atomic.h>

struct vmspace;
struct proc;

/* One identity for an actual native process address space.  Structure-only
 * references (including VMA/task ownership) do not retain the native address
 * space and cannot prevent exit from unmapping its entries.  mmget references
 * separately pin the actual native vmspace.  The native exec/free hooks retire
 * the identity before its borrowed vmspace pointer can be reused or freed.
 */
struct mm_struct {
	struct vmspace *netbsd_vmspace;
	atomic_t mm_count;
	struct work netbsd_release_work;
};

int linux_mm_identity_init(void);
int linux_mm_identity_quiesce(void);
void linux_mm_identity_resume(void);
int linux_mm_identity_fini(void);
struct mm_struct *linux_mm_identity_get(struct vmspace *);
struct mm_struct *linux_mm_identity_get_current(void);
/* Caller retains the native process.  Returns an actual address-space user
 * reference, acquired under native p_reflock against exec; finish with mmput.
 */
struct mm_struct *linux_mm_identity_get_proc(struct proc *);
void mmgrab(struct mm_struct *);
void mmdrop(struct mm_struct *);
bool mmget_not_zero(struct mm_struct *);
void mmget(struct mm_struct *);
void mmput(struct mm_struct *);
/* Read the actual host counter; there is no unsynchronized shadow field. */
int linux_mm_users(const struct mm_struct *);
void mmap_read_lock(struct mm_struct *);
void mmap_read_unlock(struct mm_struct *);
void mmap_write_lock(struct mm_struct *);
void mmap_write_unlock(struct mm_struct *);

#endif /* _LINUX_MM_IDENTITY_NETBSD_H_ */
