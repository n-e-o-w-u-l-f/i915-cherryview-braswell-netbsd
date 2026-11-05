/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Native anonymous-file owner. The shared inode and per-file name have the
 * lifetime of Linux anon_inode_getfile, backed by the native inode provider.
 * No dentry, superblock or mount object with an invented Linux layout is used.
 */
#include <sys/param.h>
#include <sys/errno.h>
#include <sys/fcntl.h>
#include <sys/kmem.h>
#include <sys/stat.h>
#include <sys/systm.h>
#include <linux/err.h>
#include <linux/anon_inodes_netbsd.h>
#include <linux/file_api_netbsd.h>
#include <linux/file_netbsd.h>

static struct linux_inode *linux_anonymous_inode;

int
linux_anon_inode_init(void)
{
    struct linux_inode *inode;
    ASSERT_SLEEPABLE();
    if (linux_anonymous_inode != NULL)
        return EBUSY;
    inode = linux_inode_alloc_system(0, 1, S_IFREG | S_IRUSR | S_IWUSR);
    if (IS_ERR(inode))
        return (int)-PTR_ERR(inode);
    linux_anonymous_inode = inode;
    return 0;
}

void
linux_anon_inode_fini(void)
{
    struct linux_inode *inode = linux_anonymous_inode;
    if (inode != NULL && atomic_load_acquire(&inode->netbsd_refs) != 1)
        panic("linux_anon_inode_fini: external shared-inode owner remains");
    linux_anonymous_inode = NULL;
    /* File admission is closed and all file shells have retired first. */
    iput(inode);
}

bool
linux_anon_inode_busy(void)
{
    return linux_anonymous_inode != NULL &&
        atomic_load_acquire(&linux_anonymous_inode->netbsd_refs) != 1;
}

struct linux_file *
linux_file_alloc_named(struct linux_inode *inode,
    const struct file_operations *ops, void *private_data, unsigned int flags,
    const char *name)
{
    struct linux_file *file;
    char *copy;
    size_t size;

    ASSERT_SLEEPABLE();
    if (name == NULL || inode == NULL || IS_ERR(inode) ||
        S_ISDIR(inode->i_mode))
        return ERR_PTR(-EINVAL);
    size = strlen(name);
    if (size == SIZE_MAX)
        return ERR_PTR(-EOVERFLOW);
    size++;
    copy = kmem_alloc(size, KM_NOSLEEP);
    if (copy == NULL)
        return ERR_PTR(-ENOMEM);
    memcpy(copy, name, size);
    file = linux_file_alloc(inode, ops, private_data, flags);
    if (IS_ERR(file)) {
        kmem_free(copy, size);
        return file;
    }
    file->netbsd_name = copy;
    file->netbsd_name_size = size;
    /* Like file_init_path for pseudo-files: open was not called, but the
     * created file owns its release callback from this point onward. */
    file->f_mode |= FMODE_OPENED;
    file->netbsd_opened = true;
    return file;
}

struct linux_file *
anon_inode_getfile(const char *name, const struct file_operations *ops,
    void *private_data, int flags)
{
    struct linux_file *file;
    struct linux_inode *inode;
    int error = linux_file_reservation_enter();

    if (error != 0)
        return ERR_PTR(-error);
    inode = linux_anonymous_inode;
    if (inode == NULL) {
        linux_file_reservation_leave();
        return ERR_PTR(-ENODEV);
    }
    file = linux_file_alloc_named(inode, ops, private_data,
        (unsigned int)flags & (O_ACCMODE | O_NONBLOCK), name);
    if (!IS_ERR(file))
        file->netbsd_anonymous = true;
    linux_file_reservation_leave();
    return file;
}

struct linux_file *
anon_inode_getfile_fmode(const char *name, const struct file_operations *ops,
    void *private_data, int flags, fmode_t mode)
{
    struct linux_file *file = anon_inode_getfile(name, ops, private_data, flags);
    if (!IS_ERR(file))
        file->f_mode |= mode;
    return file;
}

int
anon_inode_getfd(const char *name, const struct file_operations *ops,
    void *private_data, int flags)
{
    struct linux_file *file;
    int fd = get_unused_fd_flags((unsigned int)flags & O_CLOEXEC);
    if (fd < 0)
        return fd;
    file = anon_inode_getfile(name, ops, private_data, flags);
    if (IS_ERR(file)) {
        put_unused_fd((unsigned int)fd);
        return (int)PTR_ERR(file);
    }
    fd_install((unsigned int)fd, file);
    return fd;
}

