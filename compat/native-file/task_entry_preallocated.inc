/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Include in the actual linux_task.c after linux_task_alloc(), with the
 * declaration installed in linux/task_netbsd.h or the companion header.
 * Static task_key and the existing real task reference/attachment functions
 * are intentional owners. This is not a second task or specificdata runtime.
 */
void
linux_task_entry_enter_preallocated(struct task_struct **handle,
    struct task_struct **sparep)
{
	struct task_struct *spare, *task;
	unsigned long flags;
	bool valid;

	ASSERT_SLEEPABLE();
	if (handle == NULL || *handle != NULL || sparep == NULL ||
	    (spare = *sparep) == NULL)
		panic("linux_task_entry_enter_preallocated: invalid handle/spare");
	/*
	 * A successfully allocated spare retains its original reservation until
	 * final put. linux_task_system_quiesce cannot delete the key while this
	 * reservation exists. Do not introduce a new, fallible admission here.
	 */
	if (task_key == (specificdata_key_t)-1)
		panic("linux_task_entry_enter_preallocated: task key not initialized");
	raw_spin_lock_irqsave(&spare->lt_lock, flags);
	valid = spare->lt_refs == 1 && spare->lt_lwp == NULL &&
	    spare->lt_kthread == NULL && !spare->lt_exited;
	raw_spin_unlock_irqrestore(&spare->lt_lock, flags);
	if (!valid)
		panic("linux_task_entry_enter_preallocated: spare is not exclusively unattached");

	task = lwp_getspecific(task_key);
	if (task != NULL) {
		/* Current LWP ownership keeps this task alive through the lookup. */
		get_task_struct(task);
		*handle = task;
		*sparep = NULL;
		put_task_struct(spare);
		return;
	}

	/*
	 * All fallible task/notifier allocation happened before publication.
	 * attach_current may sleep in native specificdata setup; it cannot
	 * return an allocation/admission error. It adds the LWP owner reference.
	 * The spare's original reference becomes this entry's handle reference.
	 */
	linux_task_attach_current(spare);
	*sparep = NULL;
	*handle = spare;
}
