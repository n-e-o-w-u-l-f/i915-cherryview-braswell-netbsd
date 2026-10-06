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
