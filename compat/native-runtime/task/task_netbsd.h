/* SPDX-License-Identifier: BSD-2-Clause */
/* Candidate common per-LWP Linux task identity; not installed. */
#ifndef _LINUX_TASK_NETBSD_H_
#define _LINUX_TASK_NETBSD_H_

#include <sys/param.h>
#include <sys/condvar.h>
#include <sys/lwp.h>
#include <linux/raw_spinlock.h>
#include <linux/spinlock.h>

struct task_struct {
    raw_spinlock_t lt_lock;
    spinlock_t lt_sleep_lock;
    kcondvar_t lt_sleep_cv;
    void *lt_softint;
    struct lwp *lt_lwp;
    volatile unsigned int __state;
    volatile unsigned int lt_refs;
    bool lt_exited;
    /* Worker owner sets/clears this only under lt_lock. */
    void *lt_kthread;
    /* Native identity metadata; Linux PID namespace parity is OPEN. */
    pid_t pid;
    pid_t tgid;
    char comm[16];
};

int linux_task_system_init(void);
bool linux_task_system_busy(void);
int linux_task_system_quiesce(void);
void linux_task_system_resume(void);
int linux_task_system_fini(void);
struct task_struct *linux_task_alloc(void);
void linux_task_attach_current(struct task_struct *);
struct task_struct *linux_task_enter_current(void);
struct task_struct *linux_current_task(void);
void linux_get_task_struct(struct task_struct *);
void linux_put_task_struct(struct task_struct *);
struct lwp *linux_task_lwp(struct task_struct *);
void linux_set_current_state(unsigned int);
int linux_task_wake_state(struct task_struct *, unsigned int);
int linux_wake_up_process(struct task_struct *);
long linux_schedule_timeout(long);
void linux_schedule(void);
void linux_sched_set_fifo(struct task_struct *);
bool linux_signal_pending(struct task_struct *);
bool linux_fatal_signal_pending(struct task_struct *);
bool linux_signal_pending_state(unsigned int, struct task_struct *);

#define get_task_struct linux_get_task_struct
#define put_task_struct linux_put_task_struct

#endif
