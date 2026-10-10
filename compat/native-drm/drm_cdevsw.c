/*	$NetBSD: drm_cdevsw.c,v 1.31 2024/04/21 03:02:39 riastradh Exp $	*/

/*-
 * Copyright (c) 2013 The NetBSD Foundation, Inc.
 * All rights reserved.
 *
 * This code is derived from software contributed to The NetBSD Foundation
 * by Taylor R. Campbell.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE NETBSD FOUNDATION, INC. AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
 * TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE FOUNDATION OR CONTRIBUTORS
 * BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD: drm_cdevsw.c,v 1.31 2024/04/21 03:02:39 riastradh Exp $");
#include <sys/param.h>
#include <sys/types.h>
#include <sys/conf.h>
#include <sys/device.h>
#include <sys/file.h>
#include <sys/filedesc.h>
#include <sys/ioccom.h>
#include <sys/kauth.h>
#include <sys/kmem.h>
#include <sys/mman.h>
#include <sys/poll.h>
#include <sys/proc.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <uvm/uvm_extern.h>
#include <linux/err.h>
#include <linux/file.h>
#include <linux/file_netbsd.h>
#include <linux/mm_netbsd.h>
#include <linux/poll.h>
#include <linux/pci.h>
#include <linux/slab.h>
#include <linux/task_netbsd.h>
#include <drm/drm_device.h>
#include <drm/drm_drv.h>
#include <drm/drm_file.h>
#include <drm/drm_file_netbsd.h>
#include <drm/drm_ioctl.h>
#include <drm/drm_print.h>

static dev_type_open(drm_native_open);
static int drm_native_close(struct file *);
static int drm_native_read(struct file *, off_t *, struct uio *, kauth_cred_t, int);
static int drm_native_ioctl(struct file *, unsigned long, void *);
static int drm_native_ioctl_user(struct file *, unsigned long, void *, void *);
static int drm_native_poll(struct file *, int);
static int drm_native_kqfilter(struct file *, struct knote *);
static int drm_native_stat(struct file *, struct stat *);
static int drm_native_mmap(struct file *, off_t *, size_t, int, int *, int *,
    struct uvm_object **, int *);
static size_t drm_native_event_size(struct linux_file *);

const struct cdevsw drm_cdevsw = {
	.d_open = drm_native_open,
	.d_close = noclose,
	.d_read = noread,
	.d_write = nowrite,
	.d_ioctl = noioctl,
	.d_stop = nostop,
	.d_tty = notty,
	.d_poll = nopoll,
	.d_mmap = nommap,
	.d_kqfilter = nokqfilter,
	.d_discard = nodiscard,
	.d_flag = D_NEGOFFSAFE | D_MPSAFE,
};

const struct fileops drm_fileops = {
	.fo_name = "drm",
	.fo_read = drm_native_read,
	.fo_write = fbadop_write,
	.fo_ioctl = drm_native_ioctl,
	.fo_ioctl_user = drm_native_ioctl_user,
	.fo_linux_file = linux_file_native_view,
	.fo_fcntl = fnullop_fcntl,
	.fo_poll = drm_native_poll,
	.fo_stat = drm_native_stat,
	.fo_close = drm_native_close,
	.fo_kqfilter = drm_native_kqfilter,
	.fo_restart = fnullop_restart,
	.fo_mmap = drm_native_mmap,
};

static int
drm_native_error(long error)
{
	if (error == -ERESTARTSYS)
		return ERESTART;
	return error < 0 ? (int)-error : (int)error;
}

dev_t
linux_drm_minor_devno(const struct drm_minor *minor)
{
	return makedev(cdevsw_lookup_major(&drm_cdevsw), minor->index);
}

void
linux_drm_print_pci(struct drm_printer *printer, struct device *device)
{
    unsigned int domain, bus, slot, function;
    if (linux_pci_address(device, &domain, &bus, &slot, &function))
        drm_printf(printer, "drm-pdev:\t%04x:%02x:%02x.%d\n",
            domain, bus, slot, function);
}

static unsigned int
drm_native_open_flags(int flags)
{
	unsigned int linux_flags = flags & (O_NONBLOCK | O_EXCL | O_CLOEXEC);
	if ((flags & (FREAD | FWRITE)) == (FREAD | FWRITE))
		linux_flags |= O_RDWR;
	else if (flags & FWRITE)
		linux_flags |= O_WRONLY;
	return linux_flags;
}

static int
drm_native_open(dev_t devno, int flags, int fmt, struct lwp *lwp)
{
	struct task_struct *task = NULL;
	struct drm_minor *dminor;
	struct linux_inode *inode;
	struct linux_file *file;
	struct file *native;
	const struct file_operations *ops;
	int fd, error;

	(void)fmt;
	(void)lwp;
	error = drm_guarantee_initialized();
	if (error != 0)
		return error;
	error = linux_task_entry_enter(&task);
	if (error != 0)
		return error;
	dminor = drm_minor_acquire(&drm_minors_xa, minor(devno));
	if (IS_ERR(dminor)) {
		error = drm_native_error(PTR_ERR(dminor));
		goto out_task;
	}
	ops = dminor->dev->driver->fops;
	if (ops == NULL || ops->open == NULL || ops->release == NULL) {
		error = EOPNOTSUPP;
		goto out_minor;
	}
	error = fd_allocfile(&native, &fd);
	if (error != 0)
		goto out_minor;
	inode = linux_inode_alloc(devno, 0, S_IFCHR);
	if (IS_ERR(inode)) {
		error = drm_native_error(PTR_ERR(inode));
		goto out_fd;
	}
	file = linux_file_alloc(inode, ops, NULL, drm_native_open_flags(flags));
	iput(inode);
	if (IS_ERR(file)) {
		error = drm_native_error(PTR_ERR(file));
		goto out_fd;
	}
	/* The lookup reference pins the code/device until open acquires its own
	 * minor reference. Failure has no driver-release side effect.
	 */
	error = drm_native_error(ops->open(file->f_inode, file));
	if (error != 0)
		goto out_file;
	file->netbsd_opened = true;
	file->netbsd_event_size = drm_native_event_size;
	error = linux_file_poll_init(file);
	if (error != 0)
		goto out_file;
	error = fd_clone(native, fd, flags, &drm_fileops, file);
	KASSERT(error == EMOVEFD);
	drm_minor_release(dminor);
	linux_task_entry_leave(&task);
	return error;

out_file:
	fput(file);
out_fd:
	fd_abort(curproc, native, fd);
out_minor:
	drm_minor_release(dminor);
out_task:
	linux_task_entry_leave(&task);
	return error;
}

static int
drm_native_close(struct file *native)
{
	struct linux_file *file = native->f_data;

	linux_file_fd_detach(file);
	native->f_data = NULL;
	fput(file);
	return 0;
}

static void
drm_native_put_back(struct drm_file *priv, struct drm_pending_event *event)
{
	struct drm_device *dev = priv->minor->dev;
	unsigned long flags;

	spin_lock_irqsave(&dev->event_lock, flags);
	KASSERT(priv->event_space >= event->event->length);
	priv->event_space -= event->event->length;
	list_add(&event->link, &priv->event_list);
	spin_unlock_irqrestore(&dev->event_lock, flags);
	wake_up_interruptible_poll(&priv->event_wait, EPOLLIN | EPOLLRDNORM);
}

static int
drm_native_read_events(struct linux_file *file, struct uio *uio)
{
	struct drm_file *priv = file->private_data;
	struct drm_device *dev = priv->minor->dev;
	struct iovec *saved_iov;
	size_t original_resid = uio->uio_resid;
	size_t allocation_size = (size_t)uio->uio_iovcnt * sizeof(*saved_iov);
	int error;

	if (uio->uio_resid == 0)
		return 0;
	if (uio->uio_iovcnt <= 0 || (size_t)uio->uio_iovcnt >
	    SIZE_MAX / sizeof(*saved_iov))
		return EINVAL;
	saved_iov = kmem_alloc(allocation_size, KM_SLEEP);
	error = mutex_lock_interruptible(&priv->event_read_lock);
	if (error != 0)
		goto out;
	for (;;) {
		struct drm_pending_event *event = NULL;
		struct uio saved_uio;
		unsigned long flags;
		size_t length;

		spin_lock_irqsave(&dev->event_lock, flags);
		if (!list_empty(&priv->event_list)) {
			event = list_first_entry(&priv->event_list,
			    struct drm_pending_event, link);
			priv->event_space += event->event->length;
			list_del(&event->link);
		}
		spin_unlock_irqrestore(&dev->event_lock, flags);
		if (event == NULL) {
			if (original_resid != uio->uio_resid)
				break;
			if (file->f_flags & O_NONBLOCK) {
				error = -EAGAIN;
				break;
			}
			mutex_unlock(&priv->event_read_lock);
			error = wait_event_interruptible(priv->event_wait,
			    !list_empty(&priv->event_list));
			if (error == 0)
				error = mutex_lock_interruptible(&priv->event_read_lock);
			if (error != 0)
				goto out;
			continue;
		}
		length = event->event->length;
		if (length > uio->uio_resid) {
			drm_native_put_back(priv, event);
			break;
		}
		saved_uio = *uio;
		memcpy(saved_iov, uio->uio_iov,
		    (size_t)uio->uio_iovcnt * sizeof(*saved_iov));
		error = -uiomove(event->event, length, uio);
		if (error != 0) {
			memcpy(saved_uio.uio_iov, saved_iov,
			    (size_t)saved_uio.uio_iovcnt * sizeof(*saved_iov));
			*uio = saved_uio;
			if (original_resid != uio->uio_resid)
				error = 0;
			drm_native_put_back(priv, event);
			break;
		}
		kfree(event);
	}
	mutex_unlock(&priv->event_read_lock);
out:
	kmem_free(saved_iov, allocation_size);
	return drm_native_error(error);
}

static int
drm_native_read(struct file *native, off_t *offset, struct uio *uio,
    kauth_cred_t cred, int flags)
{
	struct linux_file *file = native->f_data;
	struct task_struct *task = NULL;
	int error;

	(void)offset;
	(void)cred;
	(void)flags;
	error = linux_task_entry_enter(&task);
	if (error != 0)
		return error;
	linux_file_sync_flags(file, native);
	/* All modern DRM fops use the core whole-event stream. */
	if (file->f_op->read == drm_read)
		error = drm_native_read_events(file, uio);
	else
		error = EOPNOTSUPP;
	linux_task_entry_leave(&task);
	return error;
}

static int
drm_native_ioctl_impl(struct file *native, unsigned long cmd, void *data,
    void *user_data, bool user_request)
{
	struct linux_file *file = native->f_data;
	struct task_struct *task = NULL;
	unsigned int out_size = 0;
	long linux_error;
	int error;

	if (cmd == FIONBIO)
		return 0;
	if (cmd == FIOASYNC)
		return EOPNOTSUPP;
	error = linux_task_entry_enter(&task);
	if (error != 0)
		return error;
	linux_file_sync_flags(file, native);
	if (user_request && (curproc->p_flag & PK_32)) {
		linux_error = file->f_op->compat_ioctl != NULL ?
		    file->f_op->compat_ioctl(file, cmd, (unsigned long)user_data) :
		    -ENOTTY;
	} else if (file->f_op->unlocked_ioctl == drm_ioctl) {
		linux_error = drm_ioctl_kernel_data(file, cmd, data, &out_size);
		/* Modern DRM returns output even on a dispatch/permission error. */
		if (user_request && out_size != 0) {
			error = copyout(data, user_data, out_size);
			if (error != 0)
				linux_error = -error;
		}
	} else if (user_request && file->f_op->unlocked_ioctl != NULL) {
		linux_error = file->f_op->unlocked_ioctl(file, cmd,
		    (unsigned long)user_data);
	} else {
		linux_error = -ENOTTY;
	}
	linux_task_entry_leave(&task);
	return drm_native_error(linux_error);
}

static int
drm_native_ioctl(struct file *native, unsigned long cmd, void *data)
{
	return drm_native_ioctl_impl(native, cmd, data, NULL, false);
}

static int
drm_native_ioctl_user(struct file *native, unsigned long cmd, void *data,
    void *user_data)
{
	return drm_native_ioctl_impl(native, cmd, data, user_data, true);
}

static int
drm_native_poll(struct file *native, int events)
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
drm_native_kqfilter(struct file *native, struct knote *knote)
{
	struct task_struct *task = NULL;
	int error = linux_task_entry_enter(&task);

	if (error != 0)
		return error;
	error = linux_file_native_kqfilter(native, knote);
	linux_task_entry_leave(&task);
	return error;
}

static size_t
drm_native_event_size(struct linux_file *file)
{
	struct drm_file *priv = file->private_data;
	struct drm_device *dev = priv->minor->dev;
	unsigned long flags;
	size_t size = 0;

	spin_lock_irqsave(&dev->event_lock, flags);
	if (!list_empty(&priv->event_list))
		size = list_first_entry(&priv->event_list,
		    struct drm_pending_event, link)->event->length;
	spin_unlock_irqrestore(&dev->event_lock, flags);
	return size;
}

static int
drm_native_stat(struct file *native, struct stat *stat)
{
	struct linux_file *file = native->f_data;
	dev_t devno = file->f_inode->i_rdev;

	memset(stat, 0, sizeof(*stat));
	stat->st_dev = devno;
	stat->st_rdev = devno;
	stat->st_uid = kauth_cred_geteuid(native->f_cred);
	stat->st_gid = kauth_cred_getegid(native->f_cred);
	stat->st_mode = S_IFCHR;
	return 0;
}

static int
drm_native_mmap(struct file *native, off_t *offset, size_t length, int prot,
    int *flags, int *advice, struct uvm_object **object, int *maxprot)
{
	struct linux_file *file = native->f_data;
	struct task_struct *task = NULL;
	voff_t adjusted;
	int error = linux_task_entry_enter(&task);

	if (error != 0)
		return error;
	linux_file_sync_flags(file, native);
	error = linux_uvm_mmap(file, *offset, length, prot, *flags, object, &adjusted);
	if (error == 0) {
		*offset = adjusted;
		*maxprot &= linux_uvm_mmap_maxprot(*object);
		*advice = UVM_ADV_RANDOM;
	}
	linux_task_entry_leave(&task);
	return drm_native_error(error);
}
