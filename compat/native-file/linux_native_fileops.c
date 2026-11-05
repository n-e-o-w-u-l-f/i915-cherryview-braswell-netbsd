/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#include <sys/param.h>
#include <sys/errno.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/poll.h>
#include <sys/proc.h>
#include <sys/stat.h>
#include <sys/systm.h>
#include <sys/uio.h>
#include <uvm/uvm_extern.h>
#include <linux/file_netbsd.h>
#include <linux/mm_netbsd.h>
#include <linux/shmem_fs_netbsd.h>
#include <linux/task_netbsd.h>

static int
linux_native_error(long result)
{
    if (result == -ERESTARTSYS)
        return ERESTART;
    return result < 0 ? (int)-result : 0;
}

static int
linux_native_io(struct file *native, off_t *offset, struct uio *uio,
    int flags, bool writing)
{
    struct linux_file *file = native->f_data;
    struct task_struct *task = NULL;
    struct iovec *iov;
    loff_t position;
    size_t original = uio->uio_resid, length;
    ssize_t result;
    int error;

    error = linux_task_entry_enter(&task);
    if (error != 0)
        return error;
    linux_file_sync_flags(file, native);
    if (shmem_file(file)) {
        error = linux_shmem_native_io(file, offset, uio, flags, writing);
        goto out;
    }
    if (uio->uio_resid == 0) {
        error = 0;
        goto out;
    }
    if (uio->uio_iovcnt <= 0 || original > SSIZE_MAX) {
        error = EINVAL;
        goto out;
    }
    /* These Linux callbacks consume a user address. Native kernel-space
     * uio buffers are not relabelled as user addresses; providers that own
     * kernel-space I/O (e.g. shmem above) consume the real uio directly. */
    if (uio->uio_vmspace != curproc->p_vmspace) {
        error = EFAULT;
        goto out;
    }
    if (writing ? file->f_op->write == NULL : file->f_op->read == NULL) {
        error = EINVAL;
        goto out;
    }
    mutex_lock(&file->f_pos_lock);
    position = (flags & FOF_UPDATE_OFFSET) ? file->f_pos : *offset;
    error = 0;
    while (uio->uio_resid != 0 && uio->uio_iovcnt > 0) {
        iov = uio->uio_iov;
        if (iov->iov_len == 0) {
            uio->uio_iov++;
            uio->uio_iovcnt--;
            continue;
        }
        length = MIN(iov->iov_len, uio->uio_resid);
        if (writing)
            result = (*file->f_op->write)(file, iov->iov_base, length, &position);
        else
            result = (*file->f_op->read)(file, iov->iov_base, length, &position);
        if (result < 0) {
            error = original == uio->uio_resid ? linux_native_error(result) : 0;
            break;
        }
        if ((size_t)result > length)
            panic("Linux file I/O callback exceeded its supplied buffer");
        iov->iov_base = (char *)iov->iov_base + result;
        iov->iov_len -= (size_t)result;
        uio->uio_resid -= (size_t)result;
        uio->uio_offset = position;
        if ((size_t)result < length)
            break;
    }
    if (flags & FOF_UPDATE_OFFSET)
        file->f_pos = position;
    *offset = position;
    mutex_unlock(&file->f_pos_lock);
out:
    linux_task_entry_leave(&task);
    return error;
}

static int
linux_native_read(struct file *native, off_t *offset, struct uio *uio,
    kauth_cred_t cred, int flags)
{
    (void)cred;
    return linux_native_io(native, offset, uio, flags, false);
}
static int
linux_native_write(struct file *native, off_t *offset, struct uio *uio,
    kauth_cred_t cred, int flags)
{
    (void)cred;
    return linux_native_io(native, offset, uio, flags, true);
}

static int
linux_native_ioctl(struct file *native, u_long command, void *data)
{
    struct linux_file *file = native->f_data;
    struct task_struct *task = NULL;
    int error;
    linux_file_sync_flags(file, native);
    switch (command) {
    case FIONBIO:
        /* sys_ioctl already changed the real native FNONBLOCK flag. */
        return 0;
    case FIOASYNC:
        if (file->f_op->fasync == NULL)
            return ENOTTY;
        error = linux_task_entry_enter(&task);
        if (error != 0)
            return error;
        error = linux_native_error((*file->f_op->fasync)(-1, file, *(int *)data));
        linux_task_entry_leave(&task);
        return error;
    default:
        return ENOTTY;
    }
}

static int
linux_native_ioctl_user(struct file *native, u_long command, void *data,
    void *user_data)
{
    struct linux_file *file = native->f_data;
    struct task_struct *task = NULL;
    int error;
    (void)data;
    if (file->f_op->unlocked_ioctl == NULL)
        return ENOTTY;
    error = linux_task_entry_enter(&task);
    if (error != 0)
        return error;
    linux_file_sync_flags(file, native);
    /* Linux unlocked_ioctl owns its user copy on success and error. Native
     * sys_ioctl's optional hook skips its generic second copyout. */
    error = linux_native_error((*file->f_op->unlocked_ioctl)(file,
        (unsigned int)command, (unsigned long)user_data));
    linux_task_entry_leave(&task);
    return error;
}

static int
linux_native_close(struct file *native)
{
    struct linux_file *file = native->f_data;
    native->f_data = NULL;
    linux_file_fd_detach(file);
    fput(file);
    return 0;
}

static int
linux_native_poll(struct file *native, int events)
{
    struct task_struct *task = NULL;
    int result;
    if (linux_task_entry_enter(&task) != 0)
        return POLLERR;
    result = linux_file_native_poll(native, events);
    linux_task_entry_leave(&task);
    return result;
}

static int
linux_native_kqfilter(struct file *native, struct knote *knote)
{
    struct task_struct *task = NULL;
    int error = linux_task_entry_enter(&task);
    if (error != 0)
        return error;
    error = linux_file_native_kqfilter(native, knote);
    linux_task_entry_leave(&task);
    return error;
}

static int
linux_native_stat(struct file *native, struct stat *stat)
{
    struct linux_file *file = native->f_data;
    struct linux_inode *inode = file->f_inode;
    memset(stat, 0, sizeof(*stat));
    stat->st_ino = inode->i_ino;
    stat->st_rdev = inode->i_rdev;
    stat->st_uid = kauth_cred_geteuid(file->f_cred);
    stat->st_gid = kauth_cred_getegid(file->f_cred);
    stat->st_mode = inode->i_mode;
    if (file->netbsd_anonymous)
        stat->st_mode &= ~S_IFMT; /* Actual anon_inode_getattr policy. */
    stat->st_nlink = 1;
    stat->st_size = i_size_read(inode);
    stat->st_blksize = PAGE_SIZE;
    return 0;
}

static int
linux_native_seek(struct file *native, off_t offset, int whence,
    off_t *result, int flags)
{
    struct linux_file *file = native->f_data;
    struct task_struct *task = NULL;
    loff_t previous, next;
    int error;
    (void)flags;
    if (file->f_op->llseek == NULL || (file->f_mode & FMODE_LSEEK) == 0)
        return ESPIPE;
    error = linux_task_entry_enter(&task);
    if (error != 0)
        return error;
    mutex_lock(&file->f_pos_lock);
    previous = file->f_pos;
    next = (*file->f_op->llseek)(file, offset, whence);
    error = linux_native_error(next < 0 ? next : 0);
    if (result == NULL || error != 0)
        file->f_pos = previous;
    else
        *result = next;
    mutex_unlock(&file->f_pos_lock);
    linux_task_entry_leave(&task);
    return error;
}

static int
linux_native_mmap_prepare(struct file *native, off_t *offset, size_t length,
    int prot, int *flags, int *advice, struct uvm_object **object,
    int *maxprot, struct uvm_mmap_request **request)
{
    struct linux_file *file = native->f_data;
    struct task_struct *task = NULL;
    int error = linux_task_entry_enter(&task);
    if (error != 0)
        return error;
    linux_file_sync_flags(file, native);
    /* The request owns this preparation independently of the real UAO
     * pager class. The factory returns native positive errno values. */
    error = linux_uvm_mmap_prepare(file, offset, length, prot, flags,
        advice, object, maxprot, request);
    linux_task_entry_leave(&task);
    return error;
}

const struct fileops linux_file_native_ops = {
    .fo_name = "linux-file",
    .fo_read = linux_native_read,
    .fo_write = linux_native_write,
    .fo_ioctl = linux_native_ioctl,
    .fo_ioctl_user = linux_native_ioctl_user,
    .fo_linux_file = linux_file_native_view,
    .fo_fcntl = fnullop_fcntl,
    .fo_poll = linux_native_poll,
    .fo_stat = linux_native_stat,
    .fo_close = linux_native_close,
    .fo_kqfilter = linux_native_kqfilter,
    .fo_restart = fnullop_restart,
    .fo_mmap_prepare = linux_native_mmap_prepare,
    .fo_seek = linux_native_seek,
};

