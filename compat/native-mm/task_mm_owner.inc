/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/* Actual LWP entry may follow native exec. Refresh only at this sleepable
 * boundary; unattached allocation reserves no opener process/MM identity. */
static void
linux_task_refresh_mm(struct task_struct *task)
{
    struct mm_struct *next, *previous;
    unsigned long flags;

    ASSERT_SLEEPABLE();
    next = linux_mm_identity_get_current();
    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_lwp == NULL || task->lt_lwp == curlwp);
    KASSERT(task->lt_refs != 0 && !task->lt_exited);
    previous = task->mm;
    task->mm = next; /* Transfer the new structure-only reference. */
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    if (previous != NULL)
        mmdrop(previous);
}

struct mm_struct *
linux_get_task_mm(struct task_struct *task)
{
    struct mm_struct *mm;
    unsigned long flags;

    /* mmget_not_zero is atomic-safe: actual IPL_HIGH interlock plus native
     * vm_refcnt CAS. No adaptive lock or allocation beneath lt_lock. */
    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_refs != 0);
    mm = task->lt_exited ? NULL : task->mm;
    if (mm != NULL && !mmget_not_zero(mm))
        mm = NULL;
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    return mm;
}
