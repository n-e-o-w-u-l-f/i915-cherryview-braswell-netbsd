/* SPDX-License-Identifier: BSD-2-Clause */
/* Candidate Linux task-state scheduler over real NetBSD LWP sleep queues. */
#ifndef _LINUX_SCHED_H_
#define _LINUX_SCHED_H_

#include <sys/param.h>
#include <sys/kernel.h>
#include <sys/proc.h>
#include <sys/sched.h>
#include <sys/systm.h>
#include <machine/limits.h>
#include <asm/barrier.h>
#include <asm/param.h>
#include <asm/processor.h>
#include <linux/errno.h>
#include <linux/task_netbsd.h>

/* Values and wake masks from the frozen Linux include/linux/sched.h. */
#define TASK_RUNNING         0x00000000
#define TASK_INTERRUPTIBLE   0x00000001
#define TASK_UNINTERRUPTIBLE  0x00000002
#define TASK_PARKED          0x00000040
#define TASK_DEAD            0x00000080
#define TASK_WAKEKILL        0x00000100
#define TASK_WAKING          0x00000200
#define TASK_NOLOAD          0x00000400
#define TASK_NEW             0x00000800
#define TASK_KILLABLE        (TASK_WAKEKILL | TASK_UNINTERRUPTIBLE)
#define TASK_IDLE            (TASK_UNINTERRUPTIBLE | TASK_NOLOAD)
#define TASK_NORMAL          (TASK_INTERRUPTIBLE | TASK_UNINTERRUPTIBLE)
#define TASK_COMM_LEN        16
#define MAX_SCHEDULE_TIMEOUT LONG_MAX

#define current linux_current_task()
#define set_current_state linux_set_current_state
#define __set_current_state linux_set_current_state
#define schedule linux_schedule
#define schedule_timeout linux_schedule_timeout
#define wake_up_process linux_wake_up_process
#define signal_pending linux_signal_pending
#define fatal_signal_pending linux_fatal_signal_pending
#define signal_pending_state linux_signal_pending_state
#define sched_set_fifo linux_sched_set_fifo

static inline long
schedule_timeout_interruptible(long timeout)
{
    set_current_state(TASK_INTERRUPTIBLE);
    return schedule_timeout(timeout);
}

static inline long
schedule_timeout_uninterruptible(long timeout)
{
    set_current_state(TASK_UNINTERRUPTIBLE);
    return schedule_timeout(timeout);
}

/* IO scheduling uses the real task wait. Native IO accounting is OPEN. */
static inline long
io_schedule_timeout(long timeout)
{
    return schedule_timeout(timeout);
}

static inline void
io_schedule(void)
{
    schedule();
}

static inline bool
need_resched(void)
{
    return preempt_needed();
}

static inline void
cond_resched(void)
{
    preempt_point();
}

/* Retains native process IDs; Linux thread/PID namespace parity is OPEN. */
static inline pid_t
task_pid_nr(struct task_struct *task)
{
    return task->pid;
}

static inline pid_t
task_pid_vnr(struct task_struct *task)
{
    return task_pid_nr(task);
}

#endif
