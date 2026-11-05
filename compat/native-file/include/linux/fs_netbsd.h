/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Source-level OS adapter for Linux fd179f8a DRM/i915 file consumers.
 * Linux-owned struct file/inode/address_space tags are translated to the
 * explicit linux_* tags below. Native sys/file.h remains unmodified here.
 * Backing objects, credentials, references and mapping registries are real
 * native owners; no Linux on-disk/VFS binary layout is asserted.
 */
#ifndef _NB_LINUX_FS_H_
#define _NB_LINUX_FS_H_
#include <sys/types.h>
#include <sys/kauth.h>
#include <sys/workqueue.h>
#include <linux/types.h>
#include <linux/mm_abi_types_netbsd.h>
#include <linux/gfp.h>
#include <linux/atomic.h>
#include <linux/mutex.h>
#include <linux/rwsem.h>
#include <linux/spinlock.h>
#include <linux/rcupdate.h>
#include <linux/file_ref_netbsd.h>
#include <linux/kiocb_netbsd.h>

struct file;
struct uvm_object;
struct linux_file;
struct linux_inode;
struct linux_mapping_registry;
struct task_struct;
struct module;
struct vm_area_struct;
struct vm_area_desc;
struct poll_table_struct;
struct seq_file;
struct kiocb;
struct iov_iter;
struct io_comp_batch;
struct dir_context;
struct file_lock;
struct file_lease;
struct pipe_inode_info;
struct io_uring_cmd;
struct address_space_operations;
struct linux_file_poll;
struct linux_file_work {
	struct work native;
	struct linux_file *file;
	bool retire;
};

typedef unsigned int fmode_t;
typedef unsigned int fop_flags_t;
typedef unsigned int __poll_t;
typedef void *fl_owner_t;

#define FMODE_READ (1U << 0)
#define FMODE_WRITE (1U << 1)
#define FMODE_LSEEK (1U << 2)
#define FMODE_PATH (1U << 14)
#define FMODE_ATOMIC_POS (1U << 15)
#define FMODE_CAN_READ (1U << 17)
#define FMODE_CAN_WRITE (1U << 18)
#define FMODE_OPENED (1U << 19)
#define FOP_UNSIGNED_OFFSET (1U << 5)

struct linux_address_space {
	struct linux_inode *host;
	struct uvm_object *netbsd_uobj;
	struct linux_mapping_registry *netbsd_mappings;
	struct rw_semaphore invalidate_lock;
	struct rw_semaphore i_mmap_rwsem;
	spinlock_t i_private_lock;
	atomic_t i_mmap_writable;
	gfp_t gfp_mask;
	unsigned long flags;
	const struct address_space_operations *a_ops;
};

struct linux_inode {
	mode_t i_mode;
	dev_t i_rdev;
	uint64_t i_ino;
	loff_t i_size;
	void *i_private;
	struct linux_address_space *i_mapping;
	struct linux_address_space i_data;
	volatile unsigned int netbsd_refs;
	voff_t netbsd_backing_size;
	kmutex_t netbsd_size_lock;
	bool netbsd_shmem;
	bool netbsd_noreserve;
	bool netbsd_admitted;
	uint64_t netbsd_commit_pages;
};

/* Callback signatures are from the actual frozen Linux file_operations. */
struct file_operations {
	struct module *owner;
	fop_flags_t fop_flags;
	loff_t (*llseek)(struct linux_file *, loff_t, int);
	ssize_t (*read)(struct linux_file *, char *, size_t, loff_t *);
	ssize_t (*write)(struct linux_file *, const char *, size_t, loff_t *);
	ssize_t (*read_iter)(struct kiocb *, struct iov_iter *);
	ssize_t (*write_iter)(struct kiocb *, struct iov_iter *);
	int (*iopoll)(struct kiocb *, struct io_comp_batch *, unsigned int);
	int (*iterate_shared)(struct linux_file *, struct dir_context *);
	__poll_t (*poll)(struct linux_file *, struct poll_table_struct *);
	long (*unlocked_ioctl)(struct linux_file *, unsigned int, unsigned long);
	long (*compat_ioctl)(struct linux_file *, unsigned int, unsigned long);
	int (*mmap)(struct linux_file *, struct vm_area_struct *);
	int (*open)(struct linux_inode *, struct linux_file *);
	int (*flush)(struct linux_file *, fl_owner_t);
	int (*release)(struct linux_inode *, struct linux_file *);
	int (*fsync)(struct linux_file *, loff_t, loff_t, int);
	int (*fasync)(int, struct linux_file *, int);
	int (*lock)(struct linux_file *, int, struct file_lock *);
	unsigned long (*get_unmapped_area)(struct linux_file *, unsigned long,
	    unsigned long, unsigned long, unsigned long);
	int (*check_flags)(int);
	int (*flock)(struct linux_file *, int, struct file_lock *);
	ssize_t (*splice_write)(struct pipe_inode_info *, struct linux_file *,
	    loff_t *, size_t, unsigned int);
	ssize_t (*splice_read)(struct linux_file *, loff_t *,
	    struct pipe_inode_info *, size_t, unsigned int);
	void (*splice_eof)(struct linux_file *);
	int (*setlease)(struct linux_file *, int, struct file_lease **, void **);
	long (*fallocate)(struct linux_file *, int, loff_t, loff_t);
	void (*show_fdinfo)(struct seq_file *, struct linux_file *);
	ssize_t (*copy_file_range)(struct linux_file *, loff_t,
	    struct linux_file *, loff_t, size_t, unsigned int);
	loff_t (*remap_file_range)(struct linux_file *, loff_t,
	    struct linux_file *, loff_t, loff_t, unsigned int);
	int (*fadvise)(struct linux_file *, loff_t, loff_t, int);
	int (*uring_cmd)(struct io_uring_cmd *, unsigned int);
	int (*uring_cmd_iopoll)(struct io_uring_cmd *, struct io_comp_batch *, unsigned int);
	int (*mmap_prepare)(struct vm_area_desc *);
};

struct linux_file {
	spinlock_t f_lock;
	fmode_t f_mode;
	const struct file_operations *f_op;
	struct linux_address_space *f_mapping;
	void *private_data;
	struct linux_inode *f_inode;
	unsigned int f_flags;
	loff_t f_pos;
	struct mutex f_pos_lock;
	/* A retained native credential, not a fabricated Linux cred object. */
	kauth_cred_t f_cred;
	file_ref_t f_ref;
	bool netbsd_opened;
	size_t (*netbsd_event_size)(struct linux_file *);
	struct task_struct *netbsd_release_spare;
	struct linux_file_work netbsd_release_work;
	struct linux_file_work netbsd_retire_work;
	struct rcu_head netbsd_rcu;
	struct linux_file_poll *netbsd_poll;
	char *netbsd_name;
	size_t netbsd_name_size;
	bool netbsd_anonymous;
};

struct linux_inode *linux_inode_alloc(dev_t, uint64_t, mode_t);
struct linux_inode *linux_inode_alloc_size(dev_t, uint64_t, mode_t, loff_t);
void ihold(struct linux_inode *);
void iput(struct linux_inode *);
loff_t i_size_read(const struct linux_inode *);
int linux_inode_resize(struct linux_inode *, loff_t);
/* Caller holds netbsd_size_lock; grows real backing without publishing size. */
int linux_inode_ensure_capacity_locked(struct linux_inode *, loff_t);
void i_size_write(struct linux_inode *, loff_t);
void linux_shmem_commit_init(void);
void linux_shmem_commit_fini(void);
int linux_shmem_commit_set(struct linux_inode *, loff_t);

struct linux_file *linux_file_alloc(struct linux_inode *,
    const struct file_operations *, void *, unsigned int);
void fput(struct linux_file *);
void __fput_sync(struct linux_file *);
void flush_delayed_fput(void);
struct linux_file *get_file_active(struct linux_file **);
struct linux_file *get_file_rcu(struct linux_file **);

static inline struct linux_file *get_file(struct linux_file *file)
{
	file_ref_inc(&file->f_ref);
	return file;
}
#define file_count(file) file_ref_read(&(file)->f_ref)
static inline struct linux_inode *file_inode(const struct linux_file *file)
{
	return file->f_inode;
}
static inline unsigned int iminor(const struct linux_inode *inode)
{ return minor(inode->i_rdev); }
static inline unsigned int imajor(const struct linux_inode *inode)
{ return major(inode->i_rdev); }
static inline gfp_t mapping_gfp_mask(const struct linux_address_space *mapping)
{
	return atomic_load_relaxed(&mapping->gfp_mask);
}
void mapping_set_gfp_mask(struct linux_address_space *, gfp_t);
static inline gfp_t mapping_gfp_constraint(const struct linux_address_space *mapping,
    gfp_t mask)
{ return mapping_gfp_mask(mapping) & mask; }
static inline void filemap_invalidate_lock(struct linux_address_space *mapping)
{ down_write(&mapping->invalidate_lock); }
static inline void filemap_invalidate_unlock(struct linux_address_space *mapping)
{ up_write(&mapping->invalidate_lock); }
static inline void filemap_invalidate_lock_shared(struct linux_address_space *mapping)
{ down_read(&mapping->invalidate_lock); }
static inline void filemap_invalidate_unlock_shared(struct linux_address_space *mapping)
{ up_read(&mapping->invalidate_lock); }
static inline int filemap_invalidate_trylock_shared(struct linux_address_space *mapping)
{ return down_read_trylock(&mapping->invalidate_lock); }
int mapping_map_writable(struct linux_address_space *);
void mapping_unmap_writable(struct linux_address_space *);
int mapping_deny_writable(struct linux_address_space *);
void mapping_allow_writable(struct linux_address_space *);
int mapping_mapped(const struct linux_address_space *);
static inline int mapping_writably_mapped(const struct linux_address_space *mapping)
{
	return atomic_read(&mapping->i_mmap_writable) > 0;
}
loff_t noop_llseek(struct linux_file *, loff_t, int);
loff_t no_llseek(struct linux_file *, loff_t, int);
#endif
