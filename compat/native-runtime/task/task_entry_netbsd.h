/* SPDX-License-Identifier: BSD-2-Clause */
/* Public entry APIs owned by the three same-Task translation fragments. */
#ifndef _NB_NATIVE_TASK_ENTRY_NETBSD_H_
#define _NB_NATIVE_TASK_ENTRY_NETBSD_H_

struct task_struct;

/* compat/native-entry/task_entry.inc */
int linux_task_entry_enter(struct task_struct **);
void linux_task_entry_leave(struct task_struct **);
/* compat/native-file/task_entry_preallocated.inc */
void linux_task_entry_enter_preallocated(struct task_struct **,
    struct task_struct **);
/* compat/native-file/task_quiesce_retained.inc */
int linux_task_system_quiesce_retained(struct task_struct *);

#endif /* _NB_NATIVE_TASK_ENTRY_NETBSD_H_ */
