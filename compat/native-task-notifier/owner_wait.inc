/* SPDX-License-Identifier: BSD-2-Clause */
/* Internal reference cloning, never a reopening of external admission. */
struct task_struct *
linux_task_alloc_owner_wait(struct task_struct *parent_spare)
{
    unsigned long flags;
    bool valid;

    ASSERT_SLEEPABLE();
    if (parent_spare == NULL)
        panic("linux_task_alloc_owner_wait: missing parent owner");
    /* Caller retains this exclusively unattached spare throughout the call,
     * serialized by its owning VMA/object lock. It already pins all resources.
     * No task lock is held across the sleepable child allocation. */
    raw_spin_lock_irqsave(&parent_spare->lt_lock, flags);
    valid = parent_spare->lt_refs == 1 && parent_spare->lt_lwp == NULL &&
        parent_spare->lt_kthread == NULL && !parent_spare->lt_exited;
    raw_spin_unlock_irqrestore(&parent_spare->lt_lock, flags);
    if (!valid)
        panic("linux_task_alloc_owner_wait: invalid parent spare");

    raw_spin_lock_irqsave(&task_system_lock, flags);
    if (task_count == 0 || task_count == UINT_MAX ||
        task_key == (specificdata_key_t)-1 || task_notify_queue == NULL)
        panic("linux_task_alloc_owner_wait: invalid/overflowed runtime owner");
    atomic_inc_uint(&task_count);
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
    /* Native KM_SLEEP cannot return an allocation failure; the global queue
     * was created fallibly before admission opened. No per-task establish. */
    return linux_task_alloc_reserved();
}
