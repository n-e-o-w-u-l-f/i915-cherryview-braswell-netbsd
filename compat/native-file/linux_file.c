/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/condvar.h>
#include <sys/errno.h>
#include <sys/fcntl.h>
#include <sys/file.h>
#include <sys/kauth.h>
#include <sys/kmem.h>
#include <sys/lwp.h>
#include <sys/module.h>
#include <sys/mutex.h>
#include <sys/proc.h>
#include <sys/systm.h>
#include <sys/workqueue.h>
#include <linux/err.h>
#include <linux/file_api_netbsd.h>
#include <linux/file_netbsd.h>
#include <linux/pagemap_netbsd.h>
#include <linux/sched.h>
#include <linux/task_netbsd.h>
#include "task_entry_preallocated.h"

static kmutex_t file_system_lock;
static kcondvar_t file_system_cv;
static struct workqueue *file_release_queue;
static struct task_struct *file_release_task;
static unsigned int file_live, file_pending;
static enum { FILE_SYSTEM_CLOSED, FILE_SYSTEM_OPEN, FILE_SYSTEM_CLOSING } file_state;

/* Actual task-owner extension; the retained native worker is joined before
 * key destruction. It is not an arbitrary exception to resource admission. */
int linux_task_system_quiesce_retained(struct task_struct *);

const struct file_operations *
linux_file_fops_get(const struct file_operations *ops)
{
    if (ops == NULL)
        return NULL;
    if (ops->owner != NULL)
        module_hold(ops->owner);
    return ops;
}

void
linux_file_fops_put(const struct file_operations *ops)
{
    if (ops != NULL && ops->owner != NULL)
        module_rele(ops->owner);
}

static void
linux_file_free_rcu(struct rcu_head *head)
{
    struct linux_file *file = container_of(head, struct linux_file, netbsd_rcu);
    /* Never take kernconfig_lock from the global RCU GC thread. Another
     * module may hold it while waiting for its own RCU callbacks. */
    workqueue_enqueue(file_release_queue, &file->netbsd_retire_work.native, NULL);
}

static void
linux_file_retire(struct linux_file *file)
{
    struct module *owner = file->f_op->owner;
    kmem_free(file, sizeof(*file));
    /* The callback module is pinned through release AND shell retirement.
     * module_rele runs on this native worker, not the global RCU GC thread.
     * file_live remains charged until it returns, so fini refuses before
     * attempting a queue/RCU drain under kernconfig. */
    if (owner != NULL)
        module_rele(owner);
    mutex_enter(&file_system_lock);
    if (file_live == 0)
        panic("linux_file_free_rcu: lifecycle underflow");
    file_live--;
    cv_broadcast(&file_system_cv);
    mutex_exit(&file_system_lock);
}

static void
linux_file_destroy(struct linux_file *file, bool queued)
{
    struct task_struct *entry = NULL;
    bool opened = file->netbsd_opened || (file->f_mode & FMODE_OPENED) != 0;

    ASSERT_SLEEPABLE();
    linux_task_entry_enter_preallocated(&entry, &file->netbsd_release_spare);
    if (queued)
        file_release_task = entry; /* Borrowed from this worker's LWP owner. */
    /* Detach registration callbacks before driver release destroys their
     * wait heads. This call is idempotent after the native FD was closed. */
    linux_file_poll_fini(file);
    if (opened && file->f_op->release != NULL)
        (void)(*file->f_op->release)(file->f_inode, file);
    iput(file->f_inode);
    kauth_cred_free(file->f_cred);
    if (file->netbsd_name != NULL)
        kmem_free(file->netbsd_name, file->netbsd_name_size);
    linux_mutex_destroy(&file->f_pos_lock);
    spin_lock_destroy(&file->f_lock);
    linux_task_entry_leave(&entry);
    mutex_enter(&file_system_lock);
    if (file_live == 0 || (queued && file_pending == 0))
        panic("linux_file_destroy: imbalanced lifecycle");
    if (queued)
        file_pending--;
    cv_broadcast(&file_system_cv);
    mutex_exit(&file_system_lock);
    /* File memory remains readable to get_file_active/get_file_rcu until
     * the actual native RCU backend observes its grace period. This is the
     * final access: the RCU callback may retire the shell immediately. */
    call_rcu(&file->netbsd_rcu, linux_file_free_rcu);
}

static void
linux_file_release_work(struct work *work, void *cookie)
{
    struct linux_file_work *record = container_of(work, struct linux_file_work, native);
    (void)cookie;
    if (record->retire)
        linux_file_retire(record->file);
    else
        linux_file_destroy(record->file, true);
}

int
linux_file_system_init(void)
{
    int error;
    ASSERT_SLEEPABLE();
    if (file_state != FILE_SYSTEM_CLOSED)
        return EBUSY;
    mutex_init(&file_system_lock, MUTEX_DEFAULT, IPL_HIGH);
    cv_init(&file_system_cv, "linuxfput");
    linux_fd_system_init();
    /* fput can run under Linux RCU/IRQ locks. The queue interlock must not
     * lower the caller's IPL; callbacks run in native sleepable context. */
    error = workqueue_create(&file_release_queue, "linuxfput",
        linux_file_release_work, NULL, PRI_NONE, IPL_HIGH, WQ_MPSAFE);
    if (error != 0) {
        linux_fd_system_fini();
        cv_destroy(&file_system_cv);
        mutex_destroy(&file_system_lock);
        return error;
    }
    file_live = file_pending = 0;
    file_release_task = NULL;
    error = linux_page_system_init();
    if (error != 0) {
        workqueue_destroy(file_release_queue);
        file_release_queue = NULL;
        linux_fd_system_fini();
        cv_destroy(&file_system_cv);
        mutex_destroy(&file_system_lock);
        return error;
    }
    linux_shmem_commit_init();
    error = linux_anon_inode_init();
    if (error != 0) {
        linux_shmem_commit_fini();
        linux_page_system_fini();
        workqueue_destroy(file_release_queue);
        file_release_queue = NULL;
        linux_fd_system_fini();
        cv_destroy(&file_system_cv);
        mutex_destroy(&file_system_lock);
        return error;
    }
    file_state = FILE_SYSTEM_OPEN;
    return 0;
}

unsigned int
linux_file_live_count(void)
{
    unsigned int count;
    mutex_enter(&file_system_lock);
    count = file_live;
    mutex_exit(&file_system_lock);
    return count;
}

int
linux_file_system_fini(void)
{
    int error;
    ASSERT_SLEEPABLE();
    mutex_enter(&file_system_lock);
    if (file_state != FILE_SYSTEM_OPEN || file_live != 0 ||
        file_pending != 0 || linux_fd_system_busy() || linux_anon_inode_busy()) {
        mutex_exit(&file_system_lock);
        return EBUSY;
    }
    file_state = FILE_SYSTEM_CLOSING;
    mutex_exit(&file_system_lock);
    /* All file shells already queued for retirement are reclaimed while
     * the common task system still admits ordinary callback work. */
    rcu_barrier();
    mutex_enter(&file_system_lock);
    error = linux_task_system_quiesce_retained(file_release_task);
    if (error != 0) {
        file_state = FILE_SYSTEM_OPEN;
        mutex_exit(&file_system_lock);
        return error;
    }
    mutex_exit(&file_system_lock);
    /* Worker exit invokes the existing native LWP task destructor; after
     * join it no longer retains a task-system reservation. */
    workqueue_destroy(file_release_queue);
    rcu_barrier();
    linux_anon_inode_fini();
    linux_shmem_commit_fini();
    linux_page_system_fini();
    file_release_queue = NULL;
    file_release_task = NULL;
    file_state = FILE_SYSTEM_CLOSED;
    linux_fd_system_fini();
    cv_destroy(&file_system_cv);
    mutex_destroy(&file_system_lock);
    return 0;
}

int
linux_file_reservation_enter(void)
{
    int error = 0;
    mutex_enter(&file_system_lock);
    if (file_state != FILE_SYSTEM_OPEN || file_live == UINT_MAX)
        error = EBUSY;
    else
        file_live++;
    mutex_exit(&file_system_lock);
    return error;
}

void
linux_file_reservation_leave(void)
{
    mutex_enter(&file_system_lock);
    if (file_live == 0)
        panic("linux_file_reservation_leave: admission underflow");
    file_live--;
    cv_broadcast(&file_system_cv);
    mutex_exit(&file_system_lock);
}

struct linux_file *
linux_file_alloc(struct linux_inode *inode, const struct file_operations *ops,
    void *private_data, unsigned int flags)
{
    struct linux_file *file;
    struct task_struct *spare;
    int error = ENOMEM;
    ASSERT_SLEEPABLE();
    if (inode == NULL || IS_ERR(inode) || ops == NULL)
        return ERR_PTR(-EINVAL);
    mutex_enter(&file_system_lock);
    if (file_state != FILE_SYSTEM_OPEN || file_live == UINT_MAX) {
        mutex_exit(&file_system_lock);
        return ERR_PTR(-EBUSY);
    }
    file_live++; /* Includes construction until every fallible step ends. */
    mutex_exit(&file_system_lock);
    file = kmem_zalloc(sizeof(*file), KM_NOSLEEP);
    if (file == NULL)
        goto fail_count;
    spare = linux_task_alloc();
    if (spare == NULL)
        goto fail_file;
    file->f_op = linux_file_fops_get(ops);
    if (file->f_op == NULL) {
        error = ENODEV;
        goto fail_spare;
    }
    ihold(inode);
    file->f_inode = inode;
    file->f_mapping = inode->i_mapping;
    file->private_data = private_data;
    file->f_flags = flags;
    switch (flags & O_ACCMODE) {
    case O_RDONLY: file->f_mode = FMODE_READ; break;
    case O_WRONLY: file->f_mode = FMODE_WRITE; break;
    case O_RDWR: file->f_mode = FMODE_READ | FMODE_WRITE; break;
    /* Linux OPEN_FMODE maps the reserved access value three to no access. */
    default: file->f_mode = 0; break;
    }
    if (ops->llseek != NULL) file->f_mode |= FMODE_LSEEK;
    if ((file->f_mode & FMODE_READ) != 0 &&
        (ops->read != NULL || ops->read_iter != NULL))
        file->f_mode |= FMODE_CAN_READ;
    if ((file->f_mode & FMODE_WRITE) != 0 &&
        (ops->write != NULL || ops->write_iter != NULL))
        file->f_mode |= FMODE_CAN_WRITE;
    file->f_cred = kauth_cred_hold(curlwp->l_cred);
    file->netbsd_release_spare = spare;
    file->netbsd_release_work.file = file;
    file->netbsd_release_work.retire = false;
    file->netbsd_retire_work.file = file;
    file->netbsd_retire_work.retire = true;
    spin_lock_init(&file->f_lock);
    linux_mutex_init(&file->f_pos_lock);
    file_ref_init(&file->f_ref, 1);
    /* Allocate readiness ownership only. Driver poll callbacks cannot run
     * until its constructor has finished initializing private wait heads. */
    error = linux_file_poll_init(file);
    if (error != 0) {
        linux_mutex_destroy(&file->f_pos_lock);
        spin_lock_destroy(&file->f_lock);
        kauth_cred_free(file->f_cred);
        iput(inode);
        linux_file_fops_put(ops);
        goto fail_spare;
    }
    return file;
fail_spare:
    put_task_struct(spare);
fail_file:
    kmem_free(file, sizeof(*file));
fail_count:
    mutex_enter(&file_system_lock);
    file_live--;
    cv_broadcast(&file_system_cv);
    mutex_exit(&file_system_lock);
    return ERR_PTR(-error);
}

void
fput(struct linux_file *file)
{
    if (file == NULL)
        return;
    if (!file_ref_put(&file->f_ref))
        return;
    /* No allocation and no sleeping callback on this last-reference path. */
    mutex_enter(&file_system_lock);
    if (file_state != FILE_SYSTEM_OPEN)
        panic("fput: finalizer queue closed with live file");
    file_pending++;
    mutex_exit(&file_system_lock);
    workqueue_enqueue(file_release_queue, &file->netbsd_release_work.native, NULL);
}

void
__fput_sync(struct linux_file *file)
{
    if (file != NULL && file_ref_put(&file->f_ref))
        linux_file_destroy(file, false);
}
void fput_close(struct linux_file *file) { fput(file); }
void fput_close_sync(struct linux_file *file) { __fput_sync(file); }

void
flush_delayed_fput(void)
{
    ASSERT_SLEEPABLE();
    mutex_enter(&file_system_lock);
    while (file_pending != 0)
        cv_wait(&file_system_cv, &file_system_lock);
    mutex_exit(&file_system_lock);
}

struct linux_file *
get_file_rcu(struct linux_file **pointer)
{
    struct linux_file *file;
    for (;;) {
        file = rcu_dereference_raw(*pointer);
        if (file == NULL)
            return NULL;
        if (!file_ref_get(&file->f_ref))
            continue;
        if (file == rcu_dereference_raw(*pointer))
            return file;
        fput(file);
    }
}

struct linux_file *
get_file_active(struct linux_file **pointer)
{
    struct linux_file *file;
    rcu_read_lock();
    file = rcu_dereference_raw(*pointer);
    if (file != NULL && file_ref_get(&file->f_ref)) {
        if (file != rcu_dereference_raw(*pointer)) {
            fput(file);
            file = NULL;
        }
    } else {
        file = NULL;
    }
    rcu_read_unlock();
    return file;
}

struct linux_file *
linux_file_native_view(struct file *native)
{
    struct linux_file *file = native->f_data;
    if (file == NULL || !file_ref_get(&file->f_ref))
        return NULL;
    return file;
}

void
linux_file_sync_flags(struct linux_file *file, const struct file *native)
{
    unsigned int flags = atomic_load_relaxed(&file->f_flags);
    unsigned int updated, old;
    for (;;) {
        updated = (flags & ~O_NONBLOCK) |
            ((atomic_load_relaxed(&native->f_flag) & FNONBLOCK) ? O_NONBLOCK : 0);
        old = atomic_cas_uint(&file->f_flags, flags, updated);
        if (old == flags)
            return;
        flags = old;
    }
}

loff_t
noop_llseek(struct linux_file *file, loff_t offset, int whence)
{
    (void)offset;
    (void)whence;
    return file->f_pos;
}
loff_t
no_llseek(struct linux_file *file, loff_t offset, int whence)
{
    (void)file; (void)offset; (void)whence;
    return -ESPIPE;
}
