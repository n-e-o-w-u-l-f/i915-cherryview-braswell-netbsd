/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/fcntl.h>
#include <sys/file.h>
#include <sys/filedesc.h>
#include <sys/kmem.h>
#include <sys/lwp.h>
#include <sys/mutex.h>
#include <sys/proc.h>
#include <sys/queue.h>
#include <sys/systm.h>
#include <linux/err.h>
#include <linux/file_api_netbsd.h>
#include <linux/file_netbsd.h>

struct linux_fd_reservation {
    LIST_ENTRY(linux_fd_reservation) link;
    filedesc_t *table;
    file_t *native;
    unsigned int fd;
};
/* linux/list.h has a different LIST_HEAD macro; this is a native list. */
static struct { struct linux_fd_reservation *lh_first; } reservations;
static kmutex_t reservation_lock;
static volatile unsigned int reservation_count;

void
linux_fd_system_init(void)
{
    LIST_INIT(&reservations);
    reservation_count = 0;
    mutex_init(&reservation_lock, MUTEX_DEFAULT, IPL_HIGH);
}

void
linux_fd_system_fini(void)
{
    if (!LIST_EMPTY(&reservations) || reservation_count != 0)
        panic("linux_fd_system_fini: outstanding reserved descriptor");
    mutex_destroy(&reservation_lock);
}

int linux_fd_system_busy(void) { return atomic_load_acquire(&reservation_count) != 0; }

int
get_unused_fd_flags(unsigned int flags)
{
    struct linux_fd_reservation *reservation;
    int fd, error;
    ASSERT_SLEEPABLE();
    if (flags & ~O_CLOEXEC)
        return -EINVAL;
    error = linux_file_reservation_enter();
    if (error != 0)
        return -error;
    reservation = kmem_zalloc(sizeof(*reservation), KM_NOSLEEP);
    if (reservation == NULL) {
        linux_file_reservation_leave();
        return -ENOMEM;
    }
    /* All native file/FD allocation is here, never in void fd_install. */
    error = fd_allocfile(&reservation->native, &fd);
    if (error != 0) {
        kmem_free(reservation, sizeof(*reservation));
        linux_file_reservation_leave();
        return -error;
    }
    fd_set_exclose(curlwp, fd, (flags & O_CLOEXEC) != 0);
    reservation->table = curlwp->l_fd;
    reservation->fd = (unsigned int)fd;
    mutex_enter(&reservation_lock);
    LIST_INSERT_HEAD(&reservations, reservation, link);
    atomic_inc_uint(&reservation_count);
    mutex_exit(&reservation_lock);
    return fd;
}

static struct linux_fd_reservation *
linux_fd_take_reservation(unsigned int fd)
{
    struct linux_fd_reservation *reservation;
    mutex_enter(&reservation_lock);
    LIST_FOREACH(reservation, &reservations, link) {
        if (reservation->table == curlwp->l_fd && reservation->fd == fd) {
            LIST_REMOVE(reservation, link);
            atomic_dec_uint(&reservation_count);
            mutex_exit(&reservation_lock);
            return reservation;
        }
    }
    mutex_exit(&reservation_lock);
    panic("Linux FD handoff: no reservation in the current descriptor table");
}

void
put_unused_fd(unsigned int fd)
{
    struct linux_fd_reservation *reservation = linux_fd_take_reservation(fd);
    ASSERT_SLEEPABLE();
    fd_abort(curproc, reservation->native, fd);
    kmem_free(reservation, sizeof(*reservation));
    linux_file_reservation_leave();
}

void
fd_install(unsigned int fd, struct linux_file *file)
{
    struct linux_fd_reservation *reservation;
    file_t *native;
    ASSERT_SLEEPABLE();
    if (file == NULL || IS_ERR(file) || file_count(file) == 0)
        panic("fd_install: invalid consumed Linux file reference");
    reservation = linux_fd_take_reservation(fd);
    native = reservation->native;
    native->f_flag = ((file->f_mode & FMODE_READ) ? FREAD : 0) |
        ((file->f_mode & FMODE_WRITE) ? FWRITE : 0) |
        ((file->f_flags & O_NONBLOCK) ? FNONBLOCK : 0);
    native->f_type = DTYPE_MISC;
    native->f_ops = &linux_file_native_ops;
    native->f_data = file;
    linux_file_fd_attach(file);
    /* The existing Linux reference is transferred into f_data, not copied.
     * Native dup shares this same file_t and calls fo_close only at its last
     * native reference. Native fork follows its normal file_t ownership. */
    fd_affix(curproc, native, fd);
    kmem_free(reservation, sizeof(*reservation));
    linux_file_reservation_leave();
}

struct linux_file *
fget_raw(unsigned int fd)
{
    return fd_get_linux_file(fd); /* Callback returned one OWNED reference. */
}

struct linux_file *
fget(unsigned int fd)
{
    struct linux_file *file = fget_raw(fd);
    if (file != NULL && (file->f_mode & FMODE_PATH) != 0) {
        fput(file);
        file = NULL;
    }
    return file;
}

struct fd
fdget(unsigned int fd)
{
    struct linux_file *file = fget(fd);
    return file != NULL ? CLONED_FD(file) : EMPTY_FD;
}

struct fd
fdget_raw(unsigned int fd)
{
    struct linux_file *file = fget_raw(fd);
    return file != NULL ? CLONED_FD(file) : EMPTY_FD;
}

struct fd
fdget_pos(unsigned int fd)
{
    struct fd result = fdget(fd);
    struct linux_file *file = fd_file(result);
    if (file != NULL && (file->f_mode & FMODE_ATOMIC_POS) != 0) {
        mutex_lock(&file->f_pos_lock);
        result.word |= FDPUT_POS_UNLOCK;
    }
    return result;
}

void
__f_unlock_pos(struct linux_file *file)
{
    mutex_unlock(&file->f_pos_lock);
}
