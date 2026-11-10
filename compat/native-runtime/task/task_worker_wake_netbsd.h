/* SPDX-License-Identifier: BSD-2-Clause */
/* Declaration: ../worker/worker_header.inc; definition: ../worker/worker.inc. */
#ifndef _NB_NATIVE_TASK_WORKER_WAKE_NETBSD_H_
#define _NB_NATIVE_TASK_WORKER_WAKE_NETBSD_H_

struct task_struct;

/* Caller holds task->lt_lock, as asserted by the actual worker implementation. */
int linux_kthread_wake_locked(struct task_struct *);

#endif /* _NB_NATIVE_TASK_WORKER_WAKE_NETBSD_H_ */
