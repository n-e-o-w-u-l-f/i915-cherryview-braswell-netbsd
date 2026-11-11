/*	$NetBSD: linux_kthread.c,v 1.9 2021/12/19 12:43:05 riastradh Exp $	*/

/*-
 * Copyright (c) 2021 The NetBSD Foundation, Inc.
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

#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD: linux_kthread.c,v 1.9 2021/12/19 12:43:05 riastradh Exp $");

#include <sys/types.h>

#include <sys/param.h>
#include <sys/condvar.h>
#include <sys/errno.h>
#include <sys/intr.h>
#include <sys/systm.h>
#include <sys/kmem.h>
#include <sys/kthread.h>
#include <sys/lwp.h>
#include <sys/mutex.h>
#include <sys/specificdata.h>

#include <linux/err.h>
#include <linux/kthread.h>
#include <linux/sched.h>
#include <linux/spinlock.h>

#include <drm/drm_wait_netbsd.h>

struct linux_kthread {
	struct task_struct *kt_task;
	struct kthread_worker *kt_worker;
	bool kt_attached;
	kmutex_t	kt_lock;
	kcondvar_t	kt_cv;
	bool		kt_shouldstop:1;
	bool		kt_shouldpark:1;
	bool		kt_parked:1;
	bool		kt_exited:1;
	int		kt_ret;

	int		(*kt_func)(void *);
	void		*kt_cookie;
	spinlock_t	*kt_interlock;
	drm_waitqueue_t	*kt_wq;
	struct lwp	*kt_lwp;
};

int
linux_kthread_init(void)
{

	return linux_task_system_init();
}

void
linux_kthread_fini(void)
{
	int error;

	error = linux_task_system_fini();
	KASSERT(error == 0);
}

#define linux_kthread() _linux_kthread(__func__)
static struct linux_kthread *
_linux_kthread(const char *caller)
{
	struct task_struct *task = linux_current_task();
	struct linux_kthread *K;

	KASSERTMSG(task != NULL && task->lt_kthread != NULL,
	    "%s must be called from Linux kthread", caller);
	K = task->lt_kthread;
	return K;
}

static void
linux_kthread_start(void *cookie)
{
	struct linux_kthread *T = cookie;
	int ret;

	linux_task_attach_current(T->kt_task);
	mutex_enter(&T->kt_lock);
	T->kt_attached = true;
	cv_broadcast(&T->kt_cv);
	mutex_exit(&T->kt_lock);

	ret = (*T->kt_func)(T->kt_cookie);

	/*
	 * Mark the thread exited, set the return value, and wake any
	 * waiting kthread_stop.
	 */
	mutex_enter(&T->kt_lock);
	T->kt_exited = true;
	T->kt_ret = ret;
	cv_broadcast(&T->kt_cv);
	mutex_exit(&T->kt_lock);

	/* Exit the (NetBSD) kthread.  */
	kthread_exit(0);
}

static struct linux_kthread *
kthread_alloc(int (*func)(void *), void *cookie, spinlock_t *interlock,
    drm_waitqueue_t *wq)
{
	struct linux_kthread *T;

	T = kmem_zalloc(sizeof(*T), KM_SLEEP);
	T->kt_task = linux_task_alloc();
	if (T->kt_task == NULL) {
		kmem_free(T, sizeof(*T));
		return NULL;
	}
	T->kt_task->lt_kthread = T; /* Not yet published. */

	mutex_init(&T->kt_lock, MUTEX_DEFAULT, IPL_VM);
	cv_init(&T->kt_cv, "lnxkthrd");

	T->kt_shouldstop = false;
	T->kt_shouldpark = false;
	T->kt_parked = false;
	T->kt_exited = false;
	T->kt_ret = 0;

	T->kt_func = func;
	T->kt_cookie = cookie;
	T->kt_interlock = interlock;
	T->kt_wq = wq;

	return T;
}

static void
kthread_free(struct linux_kthread *T)
{

	unsigned long flags;
	struct task_struct *task = T->kt_task;

	/* Native create failure does not create a runnable LWP. */
	KASSERT(T->kt_exited || T->kt_lwp == NULL);
	raw_spin_lock_irqsave(&task->lt_lock, flags);
	KASSERT(task->lt_kthread == T);
	task->lt_kthread = NULL;
	raw_spin_unlock_irqrestore(&task->lt_lock, flags);

	cv_destroy(&T->kt_cv);
	mutex_destroy(&T->kt_lock);
	kmem_free(T, sizeof(*T));
	put_task_struct(task);
}

static struct task_struct *
linux_kthread_spawn(int (*func)(void *), void *cookie, const char *name,
    spinlock_t *interlock, drm_waitqueue_t *wq,
    struct kthread_worker *worker, int native_flags)
{
	struct linux_kthread *T;
	int error;

	T = kthread_alloc(func, cookie, interlock, wq);
	if (T == NULL)
		return ERR_PTR(-ENOMEM);
	T->kt_worker = worker;
	if (worker != NULL)
		worker->task = T->kt_task;
	error = kthread_create(PRI_NONE,
	    KTHREAD_MPSAFE|KTHREAD_MUSTJOIN|native_flags, NULL,
	    linux_kthread_start, T, &T->kt_lwp, "%s", name);
	if (error) {
		if (worker != NULL)
			worker->task = NULL;
		kthread_free(T);
		return ERR_PTR(-error); /* XXX errno NetBSD->Linux */
	}

	/* Publish a common task with TLS/LWP identity already attached. */
	mutex_enter(&T->kt_lock);
	while (!T->kt_attached)
		cv_wait(&T->kt_cv, &T->kt_lock);
	mutex_exit(&T->kt_lock);
	return T->kt_task;
}

struct task_struct *
kthread_run(int (*func)(void *), void *cookie, const char *name,
    spinlock_t *interlock, drm_waitqueue_t *wq)
{

	return linux_kthread_spawn(func, cookie, name, interlock, wq,
	    NULL, 0);
}

int
kthread_stop(struct task_struct *task)
{
	struct linux_kthread *T = task->lt_kthread;
	int ret;

	KASSERT(T != NULL);

	/* Lock order: interlock, then kthread lock.  */
	spin_lock(T->kt_interlock);
	mutex_enter(&T->kt_lock);

	/*
	 * Notify the thread that it's stopping, and wake it if it's
	 * parked or sleeping on its own waitqueue.
	 */
	T->kt_shouldpark = false;
	T->kt_shouldstop = true;
	cv_broadcast(&T->kt_cv);
	DRM_SPIN_WAKEUP_ALL(T->kt_wq, T->kt_interlock);

	/* Release the interlock while we wait for thread to finish.  */
	spin_unlock(T->kt_interlock);

	/* Also wake callbacks sleeping on the common Linux task CV. */
	(void)linux_wake_up_process(task);

	/* Wait for the thread to finish.  */
	while (!T->kt_exited)
		cv_wait(&T->kt_cv, &T->kt_lock);

	/* Grab the return code and release the lock -- we're done.  */
	ret = T->kt_ret;
	mutex_exit(&T->kt_lock);

	/* Drain the native MUSTJOIN LWP before reclaiming its backend. */
	(void)kthread_join(T->kt_lwp);

	/* Free the (Linux) kthread.  */
	kthread_free(T);

	/* Return what the thread returned.  */
	return ret;
}

int
kthread_should_stop(void)
{
	struct linux_kthread *T = linux_kthread();
	bool shouldstop;

	mutex_enter(&T->kt_lock);
	shouldstop = T->kt_shouldstop;
	mutex_exit(&T->kt_lock);

	return shouldstop;
}

void
kthread_park(struct task_struct *task)
{
	struct linux_kthread *T = task->lt_kthread;

	/* Lock order: interlock, then kthread lock.  */
	spin_lock(T->kt_interlock);
	mutex_enter(&T->kt_lock);

	/* Caller must not ask to park if they've already asked to stop.  */
	KASSERT(!T->kt_shouldstop);

	/* Ask the thread to park.  */
	T->kt_shouldpark = true;

	/*
	 * Ensure the thread is not sleeping on its condvar.  After
	 * this point, we are done with the interlock, which we must
	 * not hold while we wait on the kthread condvar.
	 */
	DRM_SPIN_WAKEUP_ALL(T->kt_wq, T->kt_interlock);
	spin_unlock(T->kt_interlock);
	(void)linux_wake_up_process(task);

	/*
	 * Wait until the thread has issued kthread_parkme, unless we
	 * are already the thread, which Linux allows and interprets to
	 * mean don't wait.
	 */
	if (T->kt_lwp != curlwp) {
		while (!T->kt_parked)
			cv_wait(&T->kt_cv, &T->kt_lock);
	}

	/* Release the kthread lock too.  */
	mutex_exit(&T->kt_lock);
}

void
kthread_unpark(struct task_struct *task)
{
	struct linux_kthread *T = task->lt_kthread;

	mutex_enter(&T->kt_lock);
	T->kt_shouldpark = false;
	cv_broadcast(&T->kt_cv);
	mutex_exit(&T->kt_lock);
}

int
__kthread_should_park(struct task_struct *task)
{
	struct linux_kthread *T = task->lt_kthread;
	bool shouldpark;

	mutex_enter(&T->kt_lock);
	shouldpark = T->kt_shouldpark;
	mutex_exit(&T->kt_lock);

	return shouldpark;
}

int
kthread_should_park(void)
{
	struct linux_kthread *T = linux_kthread();

	return __kthread_should_park(T->kt_task);
}

void
kthread_parkme(void)
{
	struct linux_kthread *T = linux_kthread();

	assert_spin_locked(T->kt_interlock);

	spin_unlock(T->kt_interlock);
	mutex_enter(&T->kt_lock);
	while (T->kt_shouldpark) {
		linux_set_current_state(TASK_PARKED);
		T->kt_parked = true;
		cv_broadcast(&T->kt_cv);
		cv_wait(&T->kt_cv, &T->kt_lock);
		T->kt_parked = false;
	}
	linux_set_current_state(TASK_RUNNING);
	mutex_exit(&T->kt_lock);
	spin_lock(T->kt_interlock);
}

/*
 * Native immediate-work kthread worker implementation.
 *
 * Queue state is protected by an IPL_HIGH raw lock.  Native CV waiting
 * uses kw_sleep_lock, a separate IPL_VM interlock.  Only the consumer
 * takes sleep_lock -> queue_lock.  IRQ producers never take sleep_lock:
 * they schedule a CLOCK softint under queue_lock, while preemption is
 * disabled, and that notifier takes sleep_lock and broadcasts kw_wq.
 *
 * The consumer checks the predicate while holding sleep_lock.  A notifier
 * scheduled before that check either has already signalled (the consumer
 * sees the queued work), or waits for sleep_lock.  A notifier scheduled
 * after the check cannot acquire sleep_lock until cv_wait has enqueued
 * the consumer and released it.  Thus notification coalescing is safe
 * and the check-to-sleep interval cannot lose a wakeup.
 *
 * Worker and work lifetime follows Linux: queue/cancel/flush users retain
 * the worker until their call returns; work ownership must prevent freeing
 * work during cancellation/flush.  The worker itself does not dereference
 * a work item after invoking its callback, so callbacks may free their
 * own unqueued work.
 */

static void
linux_kthread_worker_notify(void *cookie)
{
	struct kthread_worker *worker = cookie;

	spin_lock(&worker->kw_sleep_lock);
	cv_broadcast(&worker->kw_wq);
	spin_unlock(&worker->kw_sleep_lock);
}

static void
linux_kthread_worker_signal(struct kthread_worker *worker)
{

	KASSERT(mutex_owned(&worker->lock.rsl_lock));
	softint_schedule(worker->kw_softint);
}

/* Caller holds task->lt_lock, which protects the backend's lifetime. */
int
linux_kthread_wake_locked(struct task_struct *task)
{
	struct linux_kthread *K = task->lt_kthread;
	struct kthread_worker *worker;
	unsigned long flags;
	int changed;

	KASSERT(mutex_owned(&task->lt_lock.rsl_lock));
	if (K == NULL || (worker = K->kt_worker) == NULL)
		return 0;

	raw_spin_lock_irqsave(&worker->lock, flags);
	changed = !worker->kw_started;
	worker->kw_started = true;
	linux_kthread_worker_signal(worker);
	raw_spin_unlock_irqrestore(&worker->lock, flags);
	return changed;
}

int
linux_kthread_wake(struct task_struct *task)
{
	unsigned long flags;
	int changed;

	raw_spin_lock_irqsave(&task->lt_lock, flags);
	changed = linux_kthread_wake_locked(task);
	raw_spin_unlock_irqrestore(&task->lt_lock, flags);
	return changed;
}

static int
linux_kthread_worker_fn(void *cookie)
{
	struct kthread_worker *worker = cookie;
	struct kthread_work *work;
	kthread_work_func_t func;
	unsigned long flags;

	spin_lock(&worker->kw_sleep_lock);
	for (;;) {
		/* Existing kthread stop/park use this same sleep interlock. */
		if (kthread_should_park())
			kthread_parkme();
		if (kthread_should_stop()) {
			raw_spin_lock_irqsave(&worker->lock, flags);
			worker->current_work = NULL;
			worker->task = NULL;
			raw_spin_unlock_irqrestore(&worker->lock, flags);
			linux_set_current_state(TASK_RUNNING);
			spin_unlock(&worker->kw_sleep_lock);
			return 0;
		}

		/* Publish sleep state before the predicate; no worker raw lock held. */
		linux_set_current_state(TASK_INTERRUPTIBLE);
		raw_spin_lock_irqsave(&worker->lock, flags);
		if (!worker->kw_started || list_empty(&worker->work_list)) {
			worker->current_work = NULL;
			raw_spin_unlock_irqrestore(&worker->lock, flags);
			cv_wait(&worker->kw_wq, &worker->kw_sleep_lock.sl_lock);
			continue;
		}

		work = list_first_entry(&worker->work_list,
		    struct kthread_work, node);
		list_del_init(&work->node);
		worker->current_work = work;
		func = work->func;
		raw_spin_unlock_irqrestore(&worker->lock, flags);
		linux_set_current_state(TASK_RUNNING);
		spin_unlock(&worker->kw_sleep_lock);

		func(work);
		/* Never dereference work after its callback. */
		preempt_point();

		spin_lock(&worker->kw_sleep_lock);
		raw_spin_lock_irqsave(&worker->lock, flags);
		worker->current_work = NULL;
		raw_spin_unlock_irqrestore(&worker->lock, flags);
	}
}

/* Insert before pos.  Flusher markers deliberately bypass queue blocking. */
static void
linux_kthread_insert_work(struct kthread_worker *worker,
    struct kthread_work *work, struct list_head *pos)
{

	KASSERT(mutex_owned(&worker->lock.rsl_lock));
	KASSERT(list_empty(&work->node));
	KASSERTMSG(work->worker == NULL || work->worker == worker,
	    "work must be reinitialized before changing workers");
	list_add_tail(&work->node, pos);
	work->worker = worker;
	/* Linux queueing also wakes a created, not-yet-started worker. */
	worker->kw_started = true;
	linux_kthread_worker_signal(worker);
}

static struct kthread_worker *
linux_kthread_create_worker_va(unsigned int flags, const char *namefmt,
    va_list ap, bool run)
{
	struct kthread_worker *worker;
	struct task_struct *task;
	char name[MAXCOMLEN];

	/* Freezer and affinity semantics are outside this implementation. */
	if (flags != 0)
		return ERR_PTR(-EOPNOTSUPP);

	vsnprintf(name, sizeof(name), namefmt, ap);
	worker = kmem_zalloc(sizeof(*worker), KM_SLEEP);
	raw_spin_lock_init(&worker->lock);
	INIT_LIST_HEAD(&worker->work_list);
	spin_lock_init(&worker->kw_sleep_lock);
	cv_init(&worker->kw_wq, "lnxworker");
	worker->kw_softint = softint_establish(SOFTINT_CLOCK|SOFTINT_MPSAFE,
	    linux_kthread_worker_notify, worker);
	if (worker->kw_softint == NULL) {
		task = ERR_PTR(-ENOMEM);
		goto fail;
	}

	task = linux_kthread_spawn(linux_kthread_worker_fn, worker, name,
	    &worker->kw_sleep_lock, &worker->kw_wq, worker, KTHREAD_TS);
	if (IS_ERR(task))
		goto fail;

	if (run)
		linux_kthread_wake(task);
	return worker;

fail:
	if (worker->kw_softint != NULL)
		softint_disestablish(worker->kw_softint);
	cv_destroy(&worker->kw_wq);
	spin_lock_destroy(&worker->kw_sleep_lock);
	raw_spin_lock_destroy(&worker->lock);
	kmem_free(worker, sizeof(*worker));
	return ERR_CAST(task);
}

struct kthread_worker *
kthread_create_worker(unsigned int flags, const char *namefmt, ...)
{
	struct kthread_worker *worker;
	va_list ap;

	va_start(ap, namefmt);
	worker = linux_kthread_create_worker_va(flags, namefmt, ap, false);
	va_end(ap);
	return worker;
}

struct kthread_worker *
kthread_run_worker(unsigned int flags, const char *namefmt, ...)
{
	struct kthread_worker *worker;
	va_list ap;

	va_start(ap, namefmt);
	worker = linux_kthread_create_worker_va(flags, namefmt, ap, true);
	va_end(ap);
	return worker;
}

bool
kthread_queue_work(struct kthread_worker *worker, struct kthread_work *work)
{
	unsigned long flags;
	bool queued = false;

	raw_spin_lock_irqsave(&worker->lock, flags);
	if (!worker->kw_destroying && work->canceling == 0 &&
	    list_empty(&work->node)) {
		linux_kthread_insert_work(worker, work, &worker->work_list);
		queued = true;
	}
	raw_spin_unlock_irqrestore(&worker->lock, flags);
	return queued;
}

struct linux_kthread_flusher {
	struct kthread_work work;
	kmutex_t lock;
	kcondvar_t cv;
	bool done;
};

static void
linux_kthread_flusher_fn(struct kthread_work *work)
{
	struct linux_kthread_flusher *flusher =
	    container_of(work, struct linux_kthread_flusher, work);

	mutex_enter(&flusher->lock);
	flusher->done = true;
	cv_broadcast(&flusher->cv);
	mutex_exit(&flusher->lock);
	/* The waiting caller may destroy flusher as soon as lock is released. */
}

static void
linux_kthread_flusher_init(struct linux_kthread_flusher *flusher)
{

	kthread_init_work(&flusher->work, linux_kthread_flusher_fn);
	mutex_init(&flusher->lock, MUTEX_DEFAULT, IPL_VM);
	cv_init(&flusher->cv, "lnxflush");
	flusher->done = false;
}

static void
linux_kthread_flusher_fini(struct linux_kthread_flusher *flusher, bool wait)
{

	if (wait) {
		mutex_enter(&flusher->lock);
		while (!flusher->done)
			cv_wait(&flusher->cv, &flusher->lock);
		mutex_exit(&flusher->lock);
	}
	cv_destroy(&flusher->cv);
	mutex_destroy(&flusher->lock);
}

void
kthread_flush_work(struct kthread_work *work)
{
	struct kthread_worker *worker = work->worker;
	struct linux_kthread_flusher flusher;
	unsigned long flags;
	bool wait = true;

	if (worker == NULL)
		return;

	linux_kthread_flusher_init(&flusher);
	raw_spin_lock_irqsave(&worker->lock, flags);
	KASSERT(work->worker == worker);
	if (!list_empty(&work->node))
		linux_kthread_insert_work(worker, &flusher.work, work->node.next);
	else if (worker->current_work == work)
		linux_kthread_insert_work(worker, &flusher.work,
		    worker->work_list.next);
	else
		wait = false;
	raw_spin_unlock_irqrestore(&worker->lock, flags);
	linux_kthread_flusher_fini(&flusher, wait);
}

bool
kthread_cancel_work_sync(struct kthread_work *work)
{
	struct kthread_worker *worker = work->worker;
	unsigned long flags;
	bool canceled = false;

	if (worker == NULL)
		return false;

	raw_spin_lock_irqsave(&worker->lock, flags);
	KASSERT(work->worker == worker);
	if (!list_empty(&work->node)) {
		list_del_init(&work->node);
		canceled = true;
	}
	if (worker->current_work == work) {
		/* Count every concurrent canceler; none may enable requeue early. */
		KASSERT(work->canceling != UINT_MAX);
		work->canceling++;
		raw_spin_unlock_irqrestore(&worker->lock, flags);
		kthread_flush_work(work);
		raw_spin_lock_irqsave(&worker->lock, flags);
		KASSERT(work->canceling != 0);
		work->canceling--;
	}
	raw_spin_unlock_irqrestore(&worker->lock, flags);
	return canceled;
}

void
kthread_flush_worker(struct kthread_worker *worker)
{
	struct linux_kthread_flusher flusher;
	unsigned long flags;

	linux_kthread_flusher_init(&flusher);
	raw_spin_lock_irqsave(&worker->lock, flags);
	KASSERT(worker->task != NULL);
	/* Tail marker waits for the snapshot; later requeue stays after it. */
	linux_kthread_insert_work(worker, &flusher.work, &worker->work_list);
	raw_spin_unlock_irqrestore(&worker->lock, flags);
	linux_kthread_flusher_fini(&flusher, true);
}

void
kthread_destroy_worker(struct kthread_worker *worker)
{
	struct task_struct *task;
	unsigned long flags;

	raw_spin_lock_irqsave(&worker->lock, flags);
	KASSERT(!worker->kw_destroying);
	worker->kw_destroying = true;
	task = worker->task;
	KASSERT(task != NULL);
	raw_spin_unlock_irqrestore(&worker->lock, flags);

	/* Reject new work and self-requeue; drain every accepted work first. */
	kthread_unpark(task);
	kthread_flush_worker(worker);
	kthread_stop(task);
	/* No raw/sleep locks held: disestablish drains pending/running notifiers. */
	softint_disestablish(worker->kw_softint);
	KASSERT(list_empty(&worker->work_list));
	KASSERT(worker->current_work == NULL);
	cv_destroy(&worker->kw_wq);
	spin_lock_destroy(&worker->kw_sleep_lock);
	raw_spin_lock_destroy(&worker->lock);
	kmem_free(worker, sizeof(*worker));
}
