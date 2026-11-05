/* SPDX-License-Identifier: BSD-2-Clause */
/* Global non-per-CPU native worker: no per-task notifier allocation. */
static struct workqueue *task_notify_queue;
static struct work task_notify_barrier;

/* Called under lt_lock. Pending includes both queued and running work.
 * The native queue interlock is IPL_HIGH, matching this raw lock. */
static void
linux_task_notify_locked(struct task_struct *task)
{
    task->lt_notify_again = true;
    if (!task->lt_notify_pending) {
        task->lt_notify_pending = true;
        workqueue_enqueue(task_notify_queue, &task->lt_notify_work, NULL);
    }
}

static void
linux_task_notify(struct work *work, void *cookie)
{
    struct task_struct *task;
    unsigned long flags;

    (void)cookie;
    if (work == &task_notify_barrier)
        return;
    task = (struct task_struct *)((char *)work -
        __builtin_offsetof(struct task_struct, lt_notify_work));
    for (;;) {
        /* Waiters take sleep_lock before lt_lock. Preserve that order. */
        spin_lock(&task->lt_sleep_lock);
        raw_spin_lock_irqsave(&task->lt_lock, flags);
        KASSERT(task->lt_notify_pending);
        if (task->lt_refs == 0) {
            KASSERT(task->lt_lwp == NULL && task->lt_kthread == NULL);
            task->lt_notify_pending = false;
            raw_spin_unlock_irqrestore(&task->lt_lock, flags);
            spin_unlock(&task->lt_sleep_lock);
            ASSERT_SLEEPABLE();
            KASSERT(!cv_has_waiters(&task->lt_sleep_cv));
            cv_destroy(&task->lt_sleep_cv);
            spin_lock_destroy(&task->lt_sleep_lock);
            raw_spin_lock_destroy(&task->lt_lock);
            kmem_free(task, sizeof(*task));
            /* Keep key/queue resources charged through actual destruction. */
            linux_task_unreserve();
            return;
        }
        task->lt_notify_again = false;
        raw_spin_unlock_irqrestore(&task->lt_lock, flags);
        cv_signal(&task->lt_sleep_cv);
        spin_unlock(&task->lt_sleep_lock);

        raw_spin_lock_irqsave(&task->lt_lock, flags);
        if (task->lt_notify_again) {
            raw_spin_unlock_irqrestore(&task->lt_lock, flags);
            continue;
        }
        task->lt_notify_pending = false;
        raw_spin_unlock_irqrestore(&task->lt_lock, flags);
        /* A later wake/last-put may enqueue this work again. Native's single
         * worker caches its list-next before this callback, permits a running
         * work to be queued, and never runs two callbacks concurrently. Do
         * not dereference task after releasing the final lifetime interlock. */
        return;
    }
}
