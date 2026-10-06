/* SPDX-License-Identifier: BSD-2-Clause */
/* Sleepable native driver entry; one caller reference per accepted call.
 * LWP identity remains stable until its actual native exit. No per-call
 * synthetic TASK_DEAD or TLS removal may replace that lifetime.
 */
int
linux_task_entry_enter(struct task_struct **handle)
{
    struct task_struct *task;

    ASSERT_SLEEPABLE();
    if (handle == NULL || *handle != NULL)
        return EINVAL;
    if (!linux_task_reserve())
        return EBUSY;
    KASSERT(task_key != (specificdata_key_t)-1);
    task = lwp_getspecific(task_key);
    if (task != NULL) {
        /* Reservation keeps the key alive through lookup and reference. */
        get_task_struct(task);
        linux_task_unreserve();
    } else {
        task = linux_task_alloc_reserved();
        if (task == NULL)
            return ENOMEM;
        linux_task_attach_current(task);
        /* Keep allocation's initial reference as this entry's handle;
         * the separately added LWP reference outlives the driver call.
         */
    }
    *handle = task;
    return 0;
}

void
linux_task_entry_leave(struct task_struct **handle)
{
    struct task_struct *task;

    ASSERT_SLEEPABLE();
    KASSERT(handle != NULL && *handle != NULL);
    task = *handle;
    KASSERT(task == lwp_getspecific(task_key));
    KASSERT(task->lt_lwp == curlwp && !task->lt_exited);
    *handle = NULL;
    put_task_struct(task);
}
