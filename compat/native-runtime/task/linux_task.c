/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * Isolated candidate, not installed. Explicit per-LWP task identity and
 * TASK_INTERRUPTIBLE/TASK_UNINTERRUPTIBLE scheduling for Linux callbacks.
 * Atomic task admission; fatal-only sleeps remain a separate backend gate.
 * Native kernel execution, cold/VM/IO and entry/code-owner drain remain OPEN.
 */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/condvar.h>
#include <sys/intr.h>
#include <sys/kmem.h>
#include <sys/lwp.h>
#include <sys/proc.h>
#include <sys/signalvar.h>
#include <sys/sleepq.h>
#include <sys/specificdata.h>
#include <sys/systm.h>

#include <linux/kthread.h>
#include <linux/sched.h>

static specificdata_key_t task_key = (specificdata_key_t)-1;
static volatile unsigned int task_count;
static raw_spinlock_t task_system_lock;
enum task_system_state { TASK_SYSTEM_OPEN, TASK_SYSTEM_QUIESCED };
static enum task_system_state task_system_state;

/* Reserve before native specificdata/KM_SLEEP. Count covers construction,
 * entry lookup and all resource lifetime until notifier teardown finishes.
 */
static bool
linux_task_reserve(void)
{
    unsigned long flags;
    bool admitted = false;

    raw_spin_lock_irqsave(&task_system_lock, flags);
    if (task_system_state == TASK_SYSTEM_OPEN && task_count != UINT_MAX) {
        atomic_inc_uint(&task_count);
        admitted = true;
    }
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
    return admitted;
}

static void
linux_task_unreserve(void)
{
    unsigned long flags;

    raw_spin_lock_irqsave(&task_system_lock, flags);
    KASSERT(task_count != 0);
    atomic_dec_uint(&task_count);
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
}


/* Per-task notifier: state is published before it is scheduled. The sleep
 * mutex covers the waiter's condition check and native CV enqueue/release.
 * A hardware/queue callback only takes lt_lock and schedules this softint.
 */
static void
linux_task_notify(void *cookie)
{
    struct task_struct *task = cookie;

    spin_lock(&task->lt_sleep_lock);
    cv_signal(&task->lt_sleep_cv);
    spin_unlock(&task->lt_sleep_lock);
}

static void
linux_task_owner_exit(void *cookie)
{
    struct task_struct *task = cookie;
    unsigned long flags;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_lwp == curlwp);
    task->lt_lwp = NULL;
    task->lt_exited = true;
    task->__state = TASK_DEAD;
    membar_sync();
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    /* Do not dereference the independently owned kthread backend. */
    put_task_struct(task);
}

int
linux_task_system_init(void)
{
    int error;

    KASSERT(task_key == (specificdata_key_t)-1);
    KASSERT(task_count == 0);
    raw_spin_lock_init(&task_system_lock);
    task_system_state = TASK_SYSTEM_QUIESCED;
    error = lwp_specific_key_create(&task_key, linux_task_owner_exit);
    if (error != 0) {
        raw_spin_lock_destroy(&task_system_lock);
        return error;
    }
    linux_task_system_resume();
    return 0;
}

bool
linux_task_system_busy(void)
{
    /* Observation only. Quiesce performs the atomic admission transaction. */
    return atomic_load_acquire(&task_count) != 0;
}

int
linux_task_system_quiesce(void)
{
    unsigned long flags;
    int error = 0;

    raw_spin_lock_irqsave(&task_system_lock, flags);
    if (task_count != 0)
        error = EBUSY;
    else
        task_system_state = TASK_SYSTEM_QUIESCED;
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
    return error;
}

void
linux_task_system_resume(void)
{
    unsigned long flags;

    raw_spin_lock_irqsave(&task_system_lock, flags);
    KASSERT(task_system_state == TASK_SYSTEM_QUIESCED && task_count == 0);
    KASSERT(task_key != (specificdata_key_t)-1);
    task_system_state = TASK_SYSTEM_OPEN;
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
}

int
linux_task_system_fini(void)
{
    int error;

    error = linux_task_system_quiesce();
    if (error != 0)
        return error;
    /* Native module/entry owners must separately prevent calls into unmapped
     * code. Closed admission and zero reservations protect key/task resources.
     */
    lwp_specific_key_delete(task_key);
    task_key = (specificdata_key_t)-1;
    raw_spin_lock_destroy(&task_system_lock);
    return 0;
}

static struct task_struct *
linux_task_alloc_reserved(void)
{
    struct task_struct *task;

    ASSERT_SLEEPABLE();
    KASSERT(task_key != (specificdata_key_t)-1);
    task = kmem_zalloc(sizeof(*task), KM_SLEEP);
    raw_spin_lock_init(&task->lt_lock);
    spin_lock_init(&task->lt_sleep_lock);
    cv_init(&task->lt_sleep_cv, "lnxtask");
    task->__state = TASK_RUNNING;
    task->lt_refs = 1;
    task->lt_softint = softint_establish(SOFTINT_CLOCK | SOFTINT_MPSAFE,
        linux_task_notify, task);
    if (task->lt_softint == NULL) {
        cv_destroy(&task->lt_sleep_cv);
        spin_lock_destroy(&task->lt_sleep_lock);
        raw_spin_lock_destroy(&task->lt_lock);
        kmem_free(task, sizeof(*task));
        linux_task_unreserve();
        return NULL;
    }
    return task;
}

struct task_struct *
linux_task_alloc(void)
{
    ASSERT_SLEEPABLE();
    if (!linux_task_reserve())
        return NULL;
    return linux_task_alloc_reserved();
}

void
linux_task_attach_current(struct task_struct *task)
{
    unsigned long flags;

    /* Native lwp_setspecific can allocate with KM_SLEEP. It must never be
     * hidden in current, prepare_to_wait, or a callback/queue critical area.
     */
    ASSERT_SLEEPABLE();
    KASSERT(task_key != (specificdata_key_t)-1);
    KASSERT(lwp_getspecific(task_key) == NULL);
    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_lwp == NULL && !task->lt_exited);
    KASSERT(task->lt_refs != 0 && task->lt_refs != UINT_MAX);
    task->lt_refs++;
    task->lt_lwp = curlwp;
    task->pid = curproc->p_pid;
    task->tgid = curproc->p_pid;
    strlcpy(task->comm, curproc->p_comm, sizeof(task->comm));
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    lwp_setspecific(task_key, task);
}

struct task_struct *
linux_task_enter_current(void)
{
    struct task_struct *task;

    ASSERT_SLEEPABLE();
    if (!linux_task_reserve())
        return NULL;
    KASSERT(task_key != (specificdata_key_t)-1);
    task = lwp_getspecific(task_key);
    if (task != NULL) {
        linux_task_unreserve();
        return task;
    }
    task = linux_task_alloc_reserved();
    if (task == NULL)
        return NULL;
    linux_task_attach_current(task);
    put_task_struct(task); /* LWP owner now retains the task. */
    return task;
}

struct task_struct *
linux_current_task(void)
{
    struct task_struct *task;

    KASSERT(task_key != (specificdata_key_t)-1);
    task = lwp_getspecific(task_key);
    KASSERTMSG(task != NULL,
        "Linux task was not attached at the sleepable native entry boundary");
    return task;
}

void
linux_get_task_struct(struct task_struct *task)
{
    unsigned long flags;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_refs != 0 && task->lt_refs != UINT_MAX);
    task->lt_refs++;
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
}

void
linux_put_task_struct(struct task_struct *task)
{
    unsigned long flags;
    bool last;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_refs != 0);
    last = --task->lt_refs == 0;
    if (last) {
        KASSERT(task->lt_lwp == NULL);
        KASSERT(task->lt_kthread == NULL);
    }
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    if (!last)
        return;
    /* Last release is sleepable: native disestablish drains all CPUs.
     * Callback users must release their last external reference later in
     * thread context. Broader arbitrary-context task-ref parity is OPEN.
     */
    ASSERT_SLEEPABLE();
    softint_disestablish(task->lt_softint);
    KASSERT(!cv_has_waiters(&task->lt_sleep_cv));
    cv_destroy(&task->lt_sleep_cv);
    spin_lock_destroy(&task->lt_sleep_lock);
    raw_spin_lock_destroy(&task->lt_lock);
    kmem_free(task, sizeof(*task));
    linux_task_unreserve();
}

struct lwp *
linux_task_lwp(struct task_struct *task)
{
    struct lwp *lwp;
    unsigned long flags;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    lwp = task->lt_lwp;
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    /* Borrowed pointer: caller must hold a MUSTJOIN/native lifetime guard. */
    return lwp;
}

void
linux_set_current_state(unsigned int state)
{
    struct task_struct *task = current;
    unsigned long flags;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    KASSERT(task->lt_lwp == curlwp && !task->lt_exited);
    task->__state = state;
    /* Full store/load barrier required by lockless waitqueue_active and
     * GuC must_wait_woken, not merely the lock's release barrier.
     */
    membar_sync();
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
}

int
linux_task_wake_state(struct task_struct *task, unsigned int mode)
{
    unsigned long flags;
    int woke = 0;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    membar_sync();
    KASSERT(task->lt_refs != 0);
    if (!task->lt_exited && (task->__state & mode) != 0) {
        task->__state = TASK_RUNNING;
        membar_sync();
        /* Holding the raw native lock satisfies kpreempt_disabled(). */
        softint_schedule(task->lt_softint);
        woke = 1;
    }
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    return woke;
}

int
linux_wake_up_process(struct task_struct *task)
{
    unsigned long flags;
    int woke = 0;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    membar_sync();
    KASSERT(task->lt_refs != 0);
    if (!task->lt_exited && (task->__state & TASK_NORMAL) != 0) {
        task->__state = TASK_RUNNING;
        membar_sync();
        softint_schedule(task->lt_softint);
        woke = 1;
    }
    /* Private backend binding and its teardown share this lifetime lock.
     * This opens worker deferred start independently of task wait state.
     */
    if (task->lt_kthread != NULL)
        woke |= linux_kthread_wake_locked(task);
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    return woke;
}

bool
linux_signal_pending(struct task_struct *task)
{
    KASSERT(task == current);
    return (atomic_load_relaxed(&curlwp->l_flag) & LW_PENDSIG) != 0 &&
        sigispending(curlwp, 0) != 0;
}

bool
linux_fatal_signal_pending(struct task_struct *task)
{
    KASSERT(task == current);
    /* Mirrors Linux's SIGKILL test, but native process-exit/group-fatal
     * translation has not yet been proved. Killable sleep is rejected.
     */
    return (atomic_load_relaxed(&curlwp->l_flag) & LW_PENDSIG) != 0 &&
        sigispending(curlwp, SIGKILL) != 0;
}

bool
linux_signal_pending_state(unsigned int state, struct task_struct *task)
{
    if ((state & (TASK_INTERRUPTIBLE | TASK_WAKEKILL)) == 0)
        return false;
    if (!signal_pending(task))
        return false;
    return (state & TASK_INTERRUPTIBLE) != 0 || fatal_signal_pending(task);
}

static unsigned int
linux_task_state(struct task_struct *task)
{
    unsigned long flags;
    unsigned int state;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    state = task->__state;
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    return state;
}

long
linux_schedule_timeout(long timeout)
{
    struct task_struct *task = current;
    unsigned int state;
    long remaining = timeout;

    if (timeout <= 0) {
        __set_current_state(TASK_RUNNING);
        return 0;
    }
    state = linux_task_state(task);
    if (state == TASK_RUNNING) {
        unsigned int start = getticks();
        yield();
        if (timeout == MAX_SCHEDULE_TIMEOUT)
            return timeout;
        return timeout - MIN(timeout,
            (long)((unsigned int)getticks() - start));
    }
    KASSERTMSG((state & TASK_WAKEKILL) == 0,
        "fatal-only native Linux task sleep backend remains unimplemented");
    KASSERTMSG(!sleepq_dontsleep(curlwp),
        "native Linux task cold/panic sleep is not accepted");

    spin_lock(&task->lt_sleep_lock);
    while (remaining != 0) {
        unsigned int start, elapsed;
        long slice;
        int error;

        state = linux_task_state(task);
        if (state == TASK_RUNNING || signal_pending_state(state, task))
            break;
        if (timeout == MAX_SCHEDULE_TIMEOUT) {
            if ((state & TASK_INTERRUPTIBLE) != 0)
                error = cv_wait_sig(&task->lt_sleep_cv,
                    &task->lt_sleep_lock.sl_lock);
            else {
                cv_wait(&task->lt_sleep_cv,
                    &task->lt_sleep_lock.sl_lock);
                error = 0;
            }
        } else {
            /* Native CV timer is signed int; keep the full long budget. */
            slice = MIN(remaining, (long)INT_MAX / 2);
            start = getticks();
            error = (state & TASK_INTERRUPTIBLE) != 0 ?
                cv_timedwait_sig(&task->lt_sleep_cv,
                    &task->lt_sleep_lock.sl_lock, (int)slice) :
                cv_timedwait(&task->lt_sleep_cv,
                    &task->lt_sleep_lock.sl_lock, (int)slice);
            elapsed = (unsigned int)getticks() - start;
            if (error == EWOULDBLOCK && elapsed < (unsigned long)slice)
                elapsed = (unsigned int)slice;
            remaining -= MIN(remaining, (long)elapsed);
        }
        /* A real task wake wins the signal/timeout race in the caller's
         * condition recheck; prepare_to_wait_event orders exclusive removal.
         */
        if (linux_task_state(task) == TASK_RUNNING)
            break;
        if (error == EINTR || error == ERESTART)
            break;
        KASSERT(error == 0 || error == EWOULDBLOCK);
    }
    __set_current_state(TASK_RUNNING);
    spin_unlock(&task->lt_sleep_lock);
    return remaining;
}

void
linux_schedule(void)
{
    (void)schedule_timeout(MAX_SCHEDULE_TIMEOUT);
}

void
linux_sched_set_fifo(struct task_struct *task)
{
    struct lwp *lwp;
    unsigned long flags;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    lwp = task->lt_lwp;
    KASSERTMSG(lwp != NULL && !task->lt_exited,
        "Linux FIFO task must be attached and alive");
    /* Keep task owner exit from retiring the LWP while we lock/update it. */
    lwp_lock(lwp);
    lwp->l_class = SCHED_FIFO;
    lwp_changepri(lwp, PRI_KERNEL_RT);
    lwp_unlock(lwp);
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
}
