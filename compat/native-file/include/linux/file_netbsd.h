/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _NB_LINUX_FILE_NETBSD_H_
#define _NB_LINUX_FILE_NETBSD_H_
#include <sys/file.h>
#include <linux/fs_netbsd.h>
#include <linux/file_api_netbsd.h>
int linux_file_system_init(void);
int linux_file_system_fini(void);
unsigned int linux_file_live_count(void);
struct linux_file *linux_file_native_view(struct file *);
void linux_file_sync_flags(struct linux_file *, const struct file *);
void linux_file_fd_detach(struct linux_file *);
void linux_file_fd_attach(struct linux_file *);
int linux_file_poll_init(struct linux_file *);
void linux_file_poll_fini(struct linux_file *);
int linux_file_native_poll(struct file *, int);
int linux_file_native_kqfilter(struct file *, struct knote *);
const struct file_operations *linux_file_fops_get(const struct file_operations *);
void linux_file_fops_put(const struct file_operations *);
extern const struct fileops linux_file_native_ops;
int linux_fd_system_busy(void);
void linux_fd_system_init(void);
void linux_fd_system_fini(void);
int linux_file_reservation_enter(void);
void linux_file_reservation_leave(void);
int linux_anon_inode_init(void);
bool linux_anon_inode_busy(void);
void linux_anon_inode_fini(void);
/* Only the file system's retained shared-anon owner uses this during init.
 * All externally held inode owners use the admitted public constructor. */
struct linux_inode *linux_inode_alloc_system(dev_t, uint64_t, mode_t);
struct linux_file *linux_file_alloc_named(struct linux_inode *,
    const struct file_operations *, void *, unsigned int, const char *);
#endif
