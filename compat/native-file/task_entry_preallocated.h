/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _LINUX_TASK_ENTRY_PREALLOCATED_H_
#define _LINUX_TASK_ENTRY_PREALLOCATED_H_

struct task_struct;

/*
 * Guaranteed sleepable entry for a non-failing final-release boundary.
 *
 * Before publishing an owning object, allocate its spare with the real
 * linux_task_alloc(). Keep that one unattached reference until final release.
 * This reservation protects the native task key and notifier resources; it
 * does not replace the object's separate callback/module lifetime owner.
 *
 * handle must initially be NULL. spare must designate one exclusively owned,
 * never-attached task without a kthread backend. This function consumes spare
 * and supplies one handle reference. It reuses the current LWP's real task,
 * or attaches the prepared task to the current LWP. No new notifier or task
 * allocation occurs. Native lwp_setspecific may sleep with KM_SLEEP.
 *
 * Finish with the existing linux_task_entry_leave(). LWP identity remains
 * attached until actual LWP exit, including nested entry/leave operations.
 * Programming errors are fatal; there is no recoverable final-release error.
 * This API is not valid in an interrupt, spinlocked or non-sleepable context.
 */
void linux_task_entry_enter_preallocated(struct task_struct **,
    struct task_struct **);
/* Shared leave API defined by compat/native-entry/task_entry.inc. */
void linux_task_entry_leave(struct task_struct **);
/* Close admission only after an object subsystem has drained; permit its
 * one retained native worker task to finish actual LWP exit before fini. */
int linux_task_system_quiesce_retained(struct task_struct *);

#endif /* _LINUX_TASK_ENTRY_PREALLOCATED_H_ */
