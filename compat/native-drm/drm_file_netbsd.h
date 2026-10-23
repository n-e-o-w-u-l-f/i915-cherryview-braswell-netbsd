/* SPDX-License-Identifier: MIT */
/* NetBSD boundary for the pinned modern DRM ioctl dispatcher. */
#ifndef _DRM_FILE_NETBSD_H_
#define _DRM_FILE_NETBSD_H_

struct linux_file;

/*
 * data has _IOC_SIZE(cmd) bytes, already marshalled by the native ioctl
 * boundary.  The dispatcher owns a separate buffer large enough for both
 * that caller ABI and the driver's canonical ABI, and zero-extends input.
 * On return, out_size describes valid output in data even if the permission
 * check or driver callback failed.  A user boundary must perform that copyout
 * itself and suppress the native generic success-only copyout.
 *
 * This declaration accompanies drm_ioctl_kernel_data.patch.  Linux-owned
 * struct file tokens must be translated to struct linux_file in the same
 * source integration as the complete file provider; no global macro alias
 * may rewrite native sys/file.h.
 */
long drm_ioctl_kernel_data(struct linux_file *, unsigned int, void *,
    unsigned int *);

#endif /* _DRM_FILE_NETBSD_H_ */
