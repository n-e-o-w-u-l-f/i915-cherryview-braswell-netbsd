/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _NB_LINUX_ANON_INODES_NETBSD_H_
#define _NB_LINUX_ANON_INODES_NETBSD_H_
#include <linux/fs_netbsd.h>
struct linux_file *anon_inode_getfile(const char *,
    const struct file_operations *, void *, int);
struct linux_file *anon_inode_getfile_fmode(const char *,
    const struct file_operations *, void *, int, fmode_t);
int anon_inode_getfd(const char *, const struct file_operations *, void *, int);
#endif

