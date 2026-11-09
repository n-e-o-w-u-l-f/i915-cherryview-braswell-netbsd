/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Real Linux callback wait-queue registrations feed native selinfo/knote.
 * Entries remain until final Linux file release; native dup/fork and multiple
 * native containers must not tear each other's registrations down.
 */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/event.h>
#include <sys/file.h>
#include <sys/kmem.h>
#include <sys/lwp.h>
#include <sys/mutex.h>
#include <sys/poll.h>
#include <sys/select.h>
#include <sys/systm.h>
#include <linux/file_netbsd.h>
#include <linux/poll_netbsd.h>
#include <linux/task_netbsd.h>

struct linux_poll_registration {
    wait_queue_entry_t wait;
    wait_queue_head_t *head;
    struct linux_file_poll *state;
    struct linux_poll_registration *next;
};
struct linux_file_poll {
    kmutex_t lock;
    struct selinfo sel;
    struct linux_poll_registration *registrations;
    unsigned int descriptors;
    __poll_t hints;
    uint64_t generation;
};
struct linux_native_poll_table {
    poll_table table;
    struct linux_file_poll *state;
    int error;
};

static int
linux_poll_to_native(__poll_t mask)
{
    int events = 0;
    if (mask & EPOLLIN) events |= POLLIN;
    if (mask & EPOLLPRI) events |= POLLPRI;
    if (mask & EPOLLOUT) events |= POLLOUT;
    if (mask & EPOLLERR) events |= POLLERR;
    if (mask & EPOLLHUP) events |= POLLHUP;
    if (mask & EPOLLNVAL) events |= POLLNVAL;
    if (mask & EPOLLRDNORM) events |= POLLRDNORM;
    if (mask & EPOLLRDBAND) events |= POLLRDBAND;
    if (mask & EPOLLWRNORM) events |= POLLWRNORM;
    if (mask & EPOLLWRBAND) events |= POLLWRBAND;
    /* Native poll has no separate half-close event. */
    if (mask & EPOLLRDHUP) events |= POLLHUP;
    return events;
}

static __poll_t
linux_poll_from_native(int events)
{
    __poll_t mask = 0;
    if (events & POLLIN) mask |= EPOLLIN;
    if (events & POLLPRI) mask |= EPOLLPRI;
    if (events & POLLOUT) mask |= EPOLLOUT | EPOLLWRNORM;
    if (events & POLLRDNORM) mask |= EPOLLRDNORM;
    if (events & POLLRDBAND) mask |= EPOLLRDBAND;
    if (events & POLLWRBAND) mask |= EPOLLWRBAND;
    return mask | EPOLLERR | EPOLLHUP;
}

static int
linux_poll_wake(wait_queue_entry_t *wait, unsigned int mode, int flags, void *key)
{
    struct linux_poll_registration *registration =
        container_of(wait, struct linux_poll_registration, wait);
    struct linux_file_poll *state = registration->state;
    __poll_t mask = key != NULL ? (__poll_t)(uintptr_t)key : ~(__poll_t)0;
    (void)mode;
    (void)flags;
    /* Linux calls this under the wait head lock. No driver callback may be
     * invoked here: e.g. DRM already holds its event_lock on this path. */
    mutex_enter(&state->lock);
    state->hints |= mask & ~POLLFREE;
    state->generation++;
    if (mask & POLLFREE) {
        list_del_init(&wait->entry);
        atomic_store_release(&registration->head, NULL);
    }
    selnotify(&state->sel, linux_poll_to_native(mask), NOTE_SUBMIT);
    mutex_exit(&state->lock);
    return 1;
}

static void
linux_poll_queue(struct linux_file *file, wait_queue_head_t *head,
    struct poll_table_struct *table)
{
    struct linux_native_poll_table *native =
        container_of(table, struct linux_native_poll_table, table);
    struct linux_file_poll *state = native->state;
    struct linux_poll_registration *entry, *candidate;
    (void)file;
    if (head == NULL) {
        native->error = EINVAL;
        return;
    }
    mutex_enter(&state->lock);
    for (entry = state->registrations; entry != NULL; entry = entry->next) {
        if (atomic_load_relaxed(&entry->head) == head) {
            mutex_exit(&state->lock);
            return;
        }
    }
    mutex_exit(&state->lock);
    candidate = kmem_zalloc(sizeof(*candidate), KM_NOSLEEP);
    if (candidate == NULL) {
        native->error = ENOMEM;
        return;
    }
    init_waitqueue_func_entry(&candidate->wait, linux_poll_wake);
    INIT_LIST_HEAD(&candidate->wait.entry);
    candidate->head = head;
    candidate->state = state;
    mutex_enter(&state->lock);
    for (entry = state->registrations; entry != NULL; entry = entry->next) {
        if (atomic_load_relaxed(&entry->head) == head) {
            mutex_exit(&state->lock);
            kmem_free(candidate, sizeof(*candidate));
            return;
        }
    }
    candidate->next = state->registrations;
    state->registrations = candidate;
    mutex_exit(&state->lock);
    /* Never take a wait head lock while holding the native state lock. */
    add_wait_queue(head, &candidate->wait);
    mutex_enter(&state->lock);
    /* A concurrent poller could have observed the published registration
     * before its addition to the Linux head. Request a full native rescan
     * after addition, closing that registration/wakeup gap. */
    /* Actual Native sel_setevents(events == 0) requests SEL_RESET, so
     * sleepers rescan without receiving fabricated readiness/error bits. */
    selnotify(&state->sel, 0, NOTE_SUBMIT);
    mutex_exit(&state->lock);
}

int
linux_file_poll_init(struct linux_file *file)
{
    struct linux_file_poll *state;
    if (file->netbsd_poll != NULL)
        return 0;
    state = kmem_zalloc(sizeof(*state), KM_NOSLEEP);
    if (state == NULL)
        return ENOMEM;
    mutex_init(&state->lock, MUTEX_DEFAULT, IPL_HIGH);
    selinit(&state->sel);
    file->netbsd_poll = state;
    return 0;
}

void
linux_file_fd_attach(struct linux_file *file)
{
    struct linux_file_poll *state = file->netbsd_poll;
    if (state == NULL)
        panic("linux_file_fd_attach: missing poll owner");
    mutex_enter(&state->lock);
    if (state->descriptors == UINT_MAX)
        panic("linux_file_fd_attach: descriptor owner overflow");
    if (state->descriptors++ == 0)
        state->hints &= ~EPOLLHUP;
    mutex_exit(&state->lock);
}

void
linux_file_fd_detach(struct linux_file *file)
{
    struct linux_file_poll *state = file->netbsd_poll;
    mutex_enter(&state->lock);
    if (state->descriptors == 0)
        panic("linux_file_fd_detach: descriptor owner underflow");
    if (--state->descriptors == 0) {
        state->hints |= EPOLLHUP;
        state->generation++;
        selnotify(&state->sel, POLLHUP, NOTE_SUBMIT);
    }
    mutex_exit(&state->lock);
}

void
linux_file_poll_fini(struct linux_file *file)
{
    struct linux_file_poll *state = file->netbsd_poll;
    struct linux_poll_registration *entry, *next;
    wait_queue_head_t *head;
    unsigned long flags;
    if (state == NULL)
        return;
    mutex_enter(&state->lock);
    if (state->descriptors != 0 || !SLIST_EMPTY(&state->sel.sel_klist))
        panic("linux_file_poll_fini: live descriptor or knote owner");
    entry = state->registrations;
    state->registrations = NULL;
    mutex_exit(&state->lock);
    for (; entry != NULL; entry = next) {
        next = entry->next;
        /* POLLFREE clears head while holding its lock. A wait-head owner
         * must observe the Linux RCU pollfree contract before freeing the
         * head, so a raced head lookup stays allocated until unlock. */
        rcu_read_lock();
        head = atomic_load_acquire(&entry->head);
        if (head != NULL) {
            spin_lock_irqsave(&head->lock, flags);
            if (atomic_load_relaxed(&entry->head) == head) {
                if (!list_empty(&entry->wait.entry))
                    list_del_init(&entry->wait.entry);
                atomic_store_release(&entry->head, NULL);
            }
            spin_unlock_irqrestore(&head->lock, flags);
        }
        rcu_read_unlock();
        kmem_free(entry, sizeof(*entry));
    }
    seldestroy(&state->sel);
    mutex_destroy(&state->lock);
    kmem_free(state, sizeof(*state));
    file->netbsd_poll = NULL;
}

static __poll_t
linux_poll_query(struct linux_file *file, __poll_t requested, int *error)
{
    struct linux_native_poll_table table;
    struct linux_file_poll *state = file->netbsd_poll;
    __poll_t result;
    uint64_t generation;
    table.state = state;
    table.error = 0;
    init_poll_funcptr(&table.table, linux_poll_queue);
    table.table._key = requested;
    mutex_enter(&state->lock);
    generation = state->generation;
    mutex_exit(&state->lock);
    result = vfs_poll(file, &table.table);
    if (table.error != 0)
        result |= EPOLLERR;
    mutex_enter(&state->lock);
    if (generation == state->generation)
        state->hints = result;
    else
        state->hints |= result;
    mutex_exit(&state->lock);
    *error = table.error;
    return result;
}

int
linux_file_native_poll(struct file *native, int events)
{
    struct linux_file *file = native->f_data;
    struct linux_file_poll *state = file->netbsd_poll;
    __poll_t result;
    int error, ready;
    linux_file_sync_flags(file, native);
    /* Record before the real driver query; a concurrent wake then either
     * wakes this LWP or is visible to the subsequent driver query. */
    mutex_enter(&state->lock);
    selrecord(curlwp, &state->sel);
    mutex_exit(&state->lock);
    result = linux_poll_query(file, linux_poll_from_native(events), &error);
    ready = linux_poll_to_native(result);
    return ready & (events | POLLERR | POLLHUP | POLLNVAL);
}

static void
linux_poll_kqdetach(struct knote *knote)
{
    struct linux_file *file = knote->kn_hook;
    struct linux_file_poll *state = file->netbsd_poll;
    mutex_enter(&state->lock);
    (void)selremove_knote(&state->sel, knote);
    knote->kn_hook = NULL;
    mutex_exit(&state->lock);
    fput(file);
}

static int
linux_poll_kqevent(struct knote *knote, long hint)
{
    struct linux_file *file = knote->kn_hook;
    struct linux_file_poll *state = file->netbsd_poll;
    struct task_struct *task = NULL;
    __poll_t wanted = knote->kn_filter == EVFILT_READ ?
        EPOLLIN | EPOLLRDNORM | EPOLLRDBAND : EPOLLOUT | EPOLLWRNORM | EPOLLWRBAND;
    __poll_t ready;
    size_t bytes = 0;
    int error = 0;

    if (hint & NOTE_SUBMIT) {
        /* state->lock is held; driver locks and task entry are forbidden. */
        ready = state->hints;
    } else {
        error = linux_task_entry_enter(&task);
        if (error == 0) {
            ready = linux_poll_query(file, wanted | EPOLLERR | EPOLLHUP, &error);
            if (knote->kn_filter == EVFILT_READ &&
                (ready & wanted) != 0 && file->netbsd_event_size != NULL)
                bytes = (*file->netbsd_event_size)(file);
            linux_task_entry_leave(&task);
        } else {
            ready = EPOLLERR;
        }
        mutex_enter(&state->lock);
    }
    if (ready & (EPOLLHUP | EPOLLRDHUP))
        knote->kn_flags |= EV_EOF;
    knote->kn_data = bytes != 0 ? (int64_t)MIN(bytes, (size_t)INT64_MAX) :
        ((ready & wanted) != 0 ? 1 : 0);
    if ((hint & NOTE_SUBMIT) == 0)
        mutex_exit(&state->lock);
    /* Allocation/task admission errors are actual readiness errors, never
     * fabricated EOF. The attachment itself returns its construction error. */
    return error != 0 || (ready & (wanted | EPOLLERR | EPOLLHUP | EPOLLRDHUP)) != 0;
}

static const struct filterops linux_poll_filterops = {
    .f_flags = FILTEROP_ISFD | FILTEROP_MPSAFE,
    .f_detach = linux_poll_kqdetach,
    .f_event = linux_poll_kqevent,
};

int
linux_file_native_kqfilter(struct file *native, struct knote *knote)
{
    struct linux_file *file = native->f_data;
    struct linux_file_poll *state = file->netbsd_poll;
    int error;
    if (knote->kn_filter != EVFILT_READ && knote->kn_filter != EVFILT_WRITE)
        return EINVAL;
    linux_file_sync_flags(file, native);
    (void)linux_poll_query(file, ~(__poll_t)0, &error);
    if (error != 0)
        return error;
    get_file(file); /* Every registered knote independently pins its owner. */
    knote->kn_hook = file;
    knote->kn_fop = &linux_poll_filterops;
    mutex_enter(&state->lock);
    selrecord_knote(&state->sel, knote);
    mutex_exit(&state->lock);
    return 0;
}

