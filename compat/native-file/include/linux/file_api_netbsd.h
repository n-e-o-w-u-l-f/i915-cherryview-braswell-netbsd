/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _NB_LINUX_FILE_H_
#define _NB_LINUX_FILE_H_
#include <linux/fs_netbsd.h>
#define FDPUT_FPUT 1UL
#define FDPUT_POS_UNLOCK 2UL
struct fd { unsigned long word; };
#define EMPTY_FD ((struct fd){0})
#define fd_file(fd) ((struct linux_file *)((fd).word & ~(FDPUT_FPUT | FDPUT_POS_UNLOCK)))
static inline bool fd_empty(struct fd fd) { return fd.word == 0; }
static inline struct fd BORROWED_FD(struct linux_file *file) { return (struct fd){(unsigned long)file}; }
static inline struct fd CLONED_FD(struct linux_file *file) { return (struct fd){(unsigned long)file | FDPUT_FPUT}; }
static inline void fdput(struct fd fd) { if (fd.word & FDPUT_FPUT) fput(fd_file(fd)); }
struct linux_file *fget(unsigned int);
struct linux_file *fget_raw(unsigned int);
struct fd fdget(unsigned int);
struct fd fdget_raw(unsigned int);
struct fd fdget_pos(unsigned int);
void __f_unlock_pos(struct linux_file *);
static inline void fdput_pos(struct fd fd) {
    if (fd.word & FDPUT_POS_UNLOCK) __f_unlock_pos(fd_file(fd));
    fdput(fd);
}
int get_unused_fd_flags(unsigned int);
void put_unused_fd(unsigned int);
void fd_install(unsigned int, struct linux_file *);
void fput_close(struct linux_file *);
void fput_close_sync(struct linux_file *);
#endif
