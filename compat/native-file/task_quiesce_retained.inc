/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/* Insert in the same actual task owner as task_entry_preallocated.inc.
 * Caller has closed its object admission and drained every live object.
 * retained is borrowed from a still-owned native worker LWP; joining that
 * worker is the only remaining operation which may release this task.
 * A nonzero result changes no admission state or resource. */
int
linux_task_system_quiesce_retained(struct task_struct *retained)
{
    unsigned long flags, taskflags;
    unsigned int expected = retained == NULL ? 0 : 1;
    bool valid = true;

    raw_spin_lock_irqsave(&task_system_lock, flags);
    if (retained != NULL) {
        raw_spin_lock_irqsave(&retained->lt_lock, taskflags);
        valid = retained->lt_refs == 1 && retained->lt_lwp != NULL &&
            retained->lt_kthread == NULL && !retained->lt_exited;
        raw_spin_unlock_irqrestore(&retained->lt_lock, taskflags);
    }
    if (!valid || task_count != expected) {
        raw_spin_unlock_irqrestore(&task_system_lock, flags);
        return EBUSY;
    }
    task_system_state = TASK_SYSTEM_QUIESCED;
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
    return 0;
}
