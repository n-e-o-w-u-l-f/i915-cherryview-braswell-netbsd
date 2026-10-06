/* SPDX-License-Identifier: BSD-2-Clause */
#include <linux/wait.h>
#include <linux/wait_bit.h>

long linux_wait_candidate_probe(struct task_struct *, spinlock_t *);

long
linux_wait_candidate_probe(struct task_struct *task, spinlock_t *lock)
{
    wait_queue_head_t head;
    wait_queue_entry_t entry;
    long ret;

    init_waitqueue_head(&head);
    init_waitqueue_entry(&entry, task);
    add_wait_queue(&head, &entry);
    wake_up_all(&head);
    remove_wait_queue(&head, &entry);
    ret = wait_event_timeout(head, true, (long)INT_MAX + 17);
    ret += wait_event_interruptible_timeout(head, true, 0);
    ret += wait_var_event_timeout(task, true, (long)INT_MAX + 17);
    spin_lock_irq(lock);
    wait_event_lock_irq(head, true, *lock);
    spin_unlock_irq(lock);
    destroy_waitqueue_head(&head);
    return ret;
}
