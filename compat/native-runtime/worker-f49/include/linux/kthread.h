/*	$NetBSD: kthread.h,v 1.4 2021/12/19 12:42:25 riastradh Exp $	*/

/*-
 * Copyright (c) 2013 The NetBSD Foundation, Inc.
 * All rights reserved.
 *
 * This code is derived from software contributed to The NetBSD Foundation
 * by Taylor R. Campbell.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE NETBSD FOUNDATION, INC. AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
 * TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE FOUNDATION OR CONTRIBUTORS
 * BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef _LINUX_KTHREAD_H_
#define _LINUX_KTHREAD_H_

#include <linux/spinlock.h>
#include <linux/list.h>
#include <linux/task_netbsd.h>

#include <drm/drm_wait_netbsd.h>

struct task_struct;

#define	__kthread_should_park	linux___kthread_should_park
#define	kthread_park		linux_kthread_park
#define	kthread_parkme		linux_kthread_parkme
#define	kthread_run		linux_kthread_run
#define	kthread_should_park	linux_kthread_should_park
#define	kthread_should_stop	linux_kthread_should_stop
#define	kthread_stop		linux_kthread_stop
#define	kthread_unpark		linux_kthread_unpark

struct task_struct *kthread_run(int (*)(void *), void *, const char *,
    spinlock_t *, drm_waitqueue_t *);

int kthread_stop(struct task_struct *);
int kthread_should_stop(void);

void kthread_park(struct task_struct *);
void kthread_unpark(struct task_struct *);
int __kthread_should_park(struct task_struct *);
int kthread_should_park(void);
void kthread_parkme(void);

int linux_kthread_init(void);
void linux_kthread_fini(void);

/* Immediate kthread workers, backed by a native joinable LWP. */
struct kthread_work;
typedef void (*kthread_work_func_t)(struct kthread_work *);

enum {
	KTW_FREEZABLE = 1U << 0,
};

struct kthread_work {
	struct list_head node;
	kthread_work_func_t func;
	struct kthread_worker *worker;
	unsigned int canceling;
};

struct kthread_worker {
	unsigned int flags;
	raw_spinlock_t lock;
	struct list_head work_list;
	struct task_struct *task;
	struct kthread_work *current_work;

	/* Native fields: no queue-lock -> sleep-lock acquisition. */
	spinlock_t kw_sleep_lock;
	drm_waitqueue_t kw_wq;
	void *kw_softint;
	bool kw_started;
	bool kw_destroying;
};

#define KTHREAD_WORK_INIT(work, fn) {				\
	.node = LIST_HEAD_INIT((work).node),			\
	.func = (fn),						\
}
#define DEFINE_KTHREAD_WORK(work, fn)				\
	struct kthread_work work = KTHREAD_WORK_INIT(work, fn)

static inline void
kthread_init_work(struct kthread_work *work, kthread_work_func_t func)
{
	INIT_LIST_HEAD(&work->node);
	work->func = func;
	work->worker = NULL;
	work->canceling = 0;
}

#define kthread_create_worker	linux_kthread_create_worker
#define kthread_run_worker	linux_kthread_run_worker
#define kthread_queue_work	linux_kthread_queue_work
#define kthread_cancel_work_sync	linux_kthread_cancel_work_sync
#define kthread_flush_work	linux_kthread_flush_work
#define kthread_flush_worker	linux_kthread_flush_worker
#define kthread_destroy_worker	linux_kthread_destroy_worker

struct kthread_worker *kthread_create_worker(unsigned int, const char *, ...)
	__printflike(2, 3);
struct kthread_worker *kthread_run_worker(unsigned int, const char *, ...)
	__printflike(2, 3);
bool kthread_queue_work(struct kthread_worker *, struct kthread_work *);
bool kthread_cancel_work_sync(struct kthread_work *);
void kthread_flush_work(struct kthread_work *);
void kthread_flush_worker(struct kthread_worker *);
void kthread_destroy_worker(struct kthread_worker *);

/* The scheduler calls the locked variant while holding task->lt_lock. */
int linux_kthread_wake_locked(struct task_struct *);
int linux_kthread_wake(struct task_struct *);

#endif  /* _LINUX_KTHREAD_H_ */
