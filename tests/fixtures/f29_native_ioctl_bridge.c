/* SPDX-License-Identifier: MIT */
/* Explicit delegated DRM/file/allocator/uaccess model, not a kernel ABI test. */
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Sparse's pointer annotation has no C runtime behavior in this model. */
#define __user
#define CHECK(expr) do { if (!(expr)) { \
	fprintf(stderr, "CHECK_FAILED %s\n", #expr); abort(); \
} } while (0)
#define unlikely(value) (value)
#define max(a, b) ((a) > (b) ? (a) : (b))
#define GFP_KERNEL 0
#define DRM_IOCTL_BASE 'd'
#define DRM_COMMAND_BASE 0x40
#define DRM_COMMAND_END 0xa0
#define IOC_IN 0x40000000U
#define IOC_OUT 0x80000000U
#define _IOC_SIZE(cmd) (((cmd) >> 16) & 0x3fffU)
#define DRM_IOCTL_NR(cmd) ((cmd) & 0xffU)
#define DRM_IOCTL_TYPE(cmd) (((cmd) >> 8) & 0xffU)
#define ENCODE(nr, size, dir) \
	((unsigned int)(nr) | ((unsigned int)DRM_IOCTL_BASE << 8) | \
	((unsigned int)(size) << 16) | (unsigned int)(dir))
#define DRM_ROOT_ONLY 1U
#define DRM_AUTH 2U
#define DRM_MASTER 4U
#define DRM_RENDER_ALLOW 8U
#define CAP_SYS_ADMIN 0
#define drm_dbg_core(dev, ...) ((void)(dev))
typedef uint32_t u32;
struct drm_file;
struct drm_device;
typedef int drm_ioctl_t(struct drm_device *, void *, struct drm_file *);
struct drm_ioctl_desc {
	unsigned int cmd;
	drm_ioctl_t *func;
	u32 flags;
	const char *name;
};
struct drm_driver {
	unsigned int num_ioctls;
	struct drm_ioctl_desc *ioctls;
};
struct drm_device {
	struct drm_driver *driver;
	bool unplugged;
};
struct drm_minor { struct drm_device *dev; };
struct drm_file { struct drm_minor *minor; bool authenticated; };
struct file;
struct fileops { int (*fo_ioctl_user)(struct file *, unsigned long, void *, void *); };
struct file { struct drm_file *private_data; const struct fileops *f_ops; };

static unsigned int callback_calls, copyin_calls, copyout_calls, pid_updates;
static unsigned int alloc_calls, free_calls, last_alloc_size;
static unsigned int callback_zero_start, callback_zero_end, callback_fill_size;
static unsigned int callback_prefix_size;
static unsigned char callback_prefix[512];
static int callback_result;
static bool alloc_fail, copyin_fail, copyout_fail;
static bool admin, render, master;
static struct drm_ioctl_desc drm_ioctls[16], driver_ioctls[1];
#define DRM_CORE_IOCTL_COUNT (sizeof(drm_ioctls) / sizeof(drm_ioctls[0]))
static struct drm_driver driver = { 1, driver_ioctls };
static struct drm_device device = { &driver, false };
static struct drm_minor minor = { &device };
static struct drm_file priv = { &minor, false };
static struct file filp = { .private_data = &priv };

static unsigned int
array_index_nospec(unsigned int index, unsigned int limit)
{
	CHECK(index < limit);
	return index;
}

static bool capable(int cap) { (void)cap; return admin; }
static bool drm_is_render_client(struct drm_file *file)
{ (void)file; return render; }
static bool drm_is_current_master(struct drm_file *file)
{ (void)file; return master; }
static bool drm_dev_is_unplugged(struct drm_device *dev)
{ return dev->unplugged; }
static void drm_file_update_pid(struct drm_file *file)
{ (void)file; pid_updates++; }

static void *
kmalloc(unsigned int size, int flags)
{
	(void)flags;
	alloc_calls++;
	if (alloc_fail)
		return NULL;
	void *memory = malloc(size);
	CHECK(memory != NULL);
	memset(memory, 0xa5, size);
	last_alloc_size = size;
	return memory;
}

static void
kfree(void *memory)
{
	if (memory != NULL) {
		free_calls++;
		free(memory);
	}
}

static int
copy_from_user(void *to, const void *from, unsigned int size)
{
	copyin_calls++;
	if (copyin_fail || (size != 0 && from == NULL))
		return 1;
	if (size != 0)
		memcpy(to, from, size);
	return 0;
}

static int
copy_to_user(void *to, const void *from, unsigned int size)
{
	copyout_calls++;
	if (copyout_fail || (size != 0 && to == NULL))
		return 1;
	if (size != 0)
		memcpy(to, from, size);
	return 0;
}

static int
callback(struct drm_device *dev, void *data, struct drm_file *file)
{
	unsigned char *p = data;
	(void)dev;
	(void)file;
	callback_calls++;
	CHECK(data != NULL);
	if (callback_zero_end > 128)
		CHECK(last_alloc_size >= callback_zero_end);
	CHECK(memcmp(data, callback_prefix, callback_prefix_size) == 0);
	for (unsigned int i = callback_zero_start; i < callback_zero_end; i++)
		CHECK(p[i] == 0);
	for (unsigned int i = 0; i < callback_fill_size; i++)
		p[i] = (unsigned char)(0x40 + i % 32);
	return callback_result;
}


/* Actual DRM functions use Linux directions. Native excerpts below are separately
 * preprocessed with NetBSD directions. All FD/uaccess/allocator state is modeled. */
/* ACTUAL_DRM_FUNCTIONS */

typedef unsigned long u_long;
#define SCARG(p, n) ((p)->n)
#define IOCPARM_SHIFT 16
#define IOCPARM_LEN(c) (((c) >> 16) & 0x1fffUL)
#define IOCGROUP(c) (((c) >> 8) & 0xffUL)
#define IOCPARM_MAX 4096UL
#define IOC_VOID 0x20000000UL
#define KM_SLEEP 0
#define UIO_WRITE 1
#define zero_size(n) (n)
#ifndef __predict_false
#define __predict_false(x) (x)
#endif
static unsigned native_copyins, native_copyouts, native_allocs, native_out_size;
static void *native_seen_data;
static bool native_copyin_fail;
static unsigned long requested_command;
static void *kmem_alloc(size_t bytes, int flags)
{ (void)flags; native_allocs++; void *p = malloc(bytes); CHECK(p != NULL); return p; }
static int copyin(const void *from, void *to, size_t bytes)
{
    native_copyins++;
    if (native_copyin_fail) return EFAULT;
    CHECK(from != NULL && to != NULL); memcpy(to, from, bytes); return 0;
}
static int copyout(const void *from, void *to, size_t bytes)
{
    native_copyouts++;
    CHECK(from != NULL && to != NULL); memcpy(to, from, bytes); return 0;
}
static void ktrgenio(unsigned fd, int mode, void *user, size_t size, int error)
{ (void)fd; (void)mode; (void)user; (void)size; (void)error; }
static int bridge_callback(struct file *file, u_long command, void *data, void *user)
{
    native_seen_data = data;
    CHECK(command == requested_command);
    if (IOCGROUP(command) != 'd') return 0;
    if (_IOC_SIZE(command) == 0) CHECK(data == NULL);
    unsigned out_size = 99;
    long result = drm_ioctl_kernel_data(file, (unsigned)command, data, &out_size);
    native_out_size = out_size;
    if (out_size) {
        int error = copyout(data, user, out_size);
        if (error) result = -error;
    }
    return result < 0 ? (int)-result : (int)result;
}
static const struct fileops drm_ops = { bridge_callback }, legacy_ops = { NULL };
#undef IOC_IN
#undef IOC_OUT
#define IOC_IN 0x80000000UL
#define IOC_OUT 0x40000000UL
static int native_boundary(u_long command, const struct fileops *ops, void *user)
{
    struct file file = filp;
    file.f_ops = ops;
    struct file *fp = &file;
    struct args { unsigned fd; void *data; } args = {7, user}, *uap = &args;
    u_long stkbuf[128 / sizeof(u_long)];
    u_long com = command, prep_com;
    void *data, *memp = NULL;
    size_t size, alloc_size;
    bool linux_drm_ioctl;
    int error = 0;
    requested_command = command;
/* ACTUAL_NATIVE_EARLY */
/* ACTUAL_NATIVE_SIZE */
/* ACTUAL_NATIVE_MARSHAL */
    if (fp->f_ops->fo_ioctl_user != NULL)
        error = (*fp->f_ops->fo_ioctl_user)(fp, com, data, user);
    else
        native_seen_data = data;
out:
    if (memp) free(memp);
    return error;
}
#undef IOC_IN
#undef IOC_OUT
#define IOC_IN 0x40000000U
#define IOC_OUT 0x80000000U
static unsigned char storage[288];
static unsigned char *const user_bytes = storage + 16;
static void reset(unsigned canonical, unsigned direction)
{
    callback_calls = copyin_calls = copyout_calls = pid_updates = 0;
    alloc_calls = free_calls = last_alloc_size = 0;
    callback_zero_start = callback_zero_end = callback_fill_size = callback_prefix_size = 0;
    callback_result = 0;
    alloc_fail = copyin_fail = copyout_fail = false;
    admin = render = master = false; device.unplugged = false; priv.authenticated = false;
    native_copyins = native_copyouts = native_allocs = native_out_size = 0;
    native_seen_data = (void *)(uintptr_t)2; native_copyin_fail = false;
    memset(drm_ioctls, 0, sizeof(drm_ioctls));
    /* GET_CAP metadata: nr 0x0c and canonical 16-byte R/W argument.
     * The explicit stub models EINVAL for unsupported capability zero. */
    drm_ioctls[0x0c] = (struct drm_ioctl_desc){
        ENCODE(0x0c, canonical, direction), callback, 0, "get_cap_metadata" };
    driver_ioctls[0] = (struct drm_ioctl_desc){
        ENCODE(DRM_COMMAND_BASE, canonical, direction), callback, 0, "large_driver" };
    memset(storage, 0x7b, sizeof(storage));
}
static void guards(unsigned changed)
{
    for (unsigned i = 0; i < 16; i++) CHECK(storage[i] == 0x7b);
    for (unsigned i = 16 + changed; i < sizeof(storage); i++) CHECK(storage[i] == 0x7b);
}

static void forged_get_cap_zero_size(void)
{
    const unsigned dirs[] = {0, IOC_IN, IOC_OUT, IOC_IN | IOC_OUT};
    for (unsigned i = 0; i < 4; i++) {
        reset(16, IOC_IN | IOC_OUT);
        callback_zero_end = callback_fill_size = 16; callback_result = -EINVAL;
        int error = native_boundary(ENCODE(0x0c, 0, dirs[i]), &drm_ops, (void *)(uintptr_t)1);
        CHECK(error == EINVAL);
        CHECK(native_seen_data == NULL && native_out_size == 0);
        CHECK(callback_calls == 1 && native_copyins == 0 && native_copyouts == 0);
        CHECK(copyin_calls == 0 && copyout_calls == 0 && native_allocs == 0);
        CHECK(alloc_calls == 0 && free_calls == 0); guards(0);
    }
}
static void zero_size_large_canonical(void)
{
    const int results[] = {0, -EIO};
    for (unsigned i = 0; i < 2; i++) {
        reset(256, IOC_IN | IOC_OUT);
        callback_zero_end = callback_fill_size = 256; callback_result = results[i];
        int error = native_boundary(ENCODE(DRM_COMMAND_BASE, 0, IOC_IN | IOC_OUT),
            &drm_ops, (void *)(uintptr_t)1);
        CHECK(error == -results[i]);
        CHECK(native_seen_data == NULL && native_out_size == 0);
        CHECK(callback_calls == 1 && alloc_calls == 1 && free_calls == 1);
        CHECK(last_alloc_size == 256);
        CHECK(native_copyins == 0 && native_copyouts == 0 && native_allocs == 0);
        CHECK(copyin_calls == 0 && copyout_calls == 0); guards(0);
    }
}
static void normal(unsigned direction)
{
    reset(16, IOC_IN | IOC_OUT);
    unsigned input = (direction & IOC_IN) ? 16 : 0;
    if (input) {
        for (unsigned i = 0; i < input; i++) user_bytes[i] = (unsigned char)(0x10 + i);
        memcpy(callback_prefix, user_bytes, input);
    }
    callback_prefix_size = input; callback_zero_start = input;
    callback_zero_end = callback_fill_size = 16;
    int error = native_boundary(ENCODE(0x0c, 16, direction), &drm_ops, user_bytes);
    CHECK(error == 0);
    CHECK(native_copyins == (input ? 1U : 0U));
    CHECK(callback_calls == 1 && copyin_calls == 0 && copyout_calls == 0);
    CHECK(native_copyouts == ((direction & IOC_OUT) ? 1U : 0U));
    CHECK(native_out_size == ((direction & IOC_OUT) ? 16U : 0U));
    if (direction & IOC_OUT) CHECK(user_bytes[0] == 0x40 && user_bytes[15] == 0x4f);
    else CHECK(memcmp(user_bytes, callback_prefix, 16) == 0);
    guards(16);
}
static void linux_read_write_16(void) { normal(IOC_IN | IOC_OUT); }
static void linux_write_only_16(void) { normal(IOC_IN); }
static void linux_read_only_16(void) { normal(IOC_OUT); }
static void legacy_zero_size_preserves_user_address(void)
{
    reset(16, IOC_IN | IOC_OUT);
    CHECK(native_boundary(ENCODE(0x0c, 0, 0), &legacy_ops, user_bytes) == 0);
    CHECK(native_seen_data == user_bytes);
    CHECK(callback_calls == 0 && native_copyins == 0 && native_copyouts == 0); guards(0);
}
static void non_drm_hook_zero_size_preserves_user_address(void)
{
    reset(16, IOC_IN | IOC_OUT);
    CHECK(native_boundary(((u_long)'x' << 8) | 0x0c, &drm_ops, user_bytes) == 0);
    CHECK(native_seen_data == user_bytes);
    CHECK(callback_calls == 0 && native_copyins == 0 && native_copyouts == 0); guards(0);
}
static void copyin_fault_before_callback(void)
{
    reset(16, IOC_IN | IOC_OUT); native_copyin_fail = true;
    CHECK(native_boundary(ENCODE(0x0c, 16, IOC_IN), &drm_ops, (void *)(uintptr_t)1) == EFAULT);
    CHECK(native_copyins == 1 && callback_calls == 0 && native_copyouts == 0);
}
static void highbit_rejected_before_uaccess(void)
{
    reset(16, IOC_IN | IOC_OUT);
    int error = native_boundary(ENCODE(0x0c, 8192, IOC_IN | IOC_OUT), &drm_ops, (void *)(uintptr_t)1);
    CHECK(error == ENOTTY);
    CHECK(native_copyins == 0 && callback_calls == 0 && native_copyouts == 0);
}
static void oversized_native_argument_rejected(void)
{
    reset(16, IOC_IN | IOC_OUT);
    int error = native_boundary(ENCODE(0x0c, 4097, IOC_IN | IOC_OUT), &drm_ops, (void *)(uintptr_t)1);
    CHECK(error == ENOTTY);
    CHECK(native_copyins == 0 && callback_calls == 0 && native_copyouts == 0);
}
static void null_user_zero_size_get_cap(void)
{
    reset(16, IOC_IN | IOC_OUT);
    callback_zero_end = callback_fill_size = 16; callback_result = -EINVAL;
    CHECK(native_boundary(ENCODE(0x0c, 0, 0), &drm_ops, NULL) == EINVAL);
    CHECK(native_seen_data == NULL && native_out_size == 0);
    CHECK(callback_calls == 1 && native_copyins == 0 && native_copyouts == 0);
}
#define RUN(n) do { puts("RUN " #n); n(); puts("PASS " #n); } while (0)
int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    RUN(forged_get_cap_zero_size); RUN(zero_size_large_canonical);
    RUN(linux_read_write_16); RUN(linux_write_only_16); RUN(linux_read_only_16);
    RUN(legacy_zero_size_preserves_user_address);
    RUN(non_drm_hook_zero_size_preserves_user_address);
    RUN(copyin_fault_before_callback); RUN(highbit_rejected_before_uaccess);
    RUN(oversized_native_argument_rejected); RUN(null_user_zero_size_get_cap);
    puts("F29_NATIVE_IOCTL_SOURCE_PASS 11"); return 0;
}
