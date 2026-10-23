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
struct file { struct drm_file *private_data; };

static unsigned int callback_calls, copyin_calls, copyout_calls, pid_updates;
static unsigned int alloc_calls, free_calls, last_alloc_size;
static unsigned int callback_zero_start, callback_zero_end, callback_fill_size;
static unsigned int callback_prefix_size;
static unsigned char callback_prefix[512];
static int callback_result;
static bool alloc_fail, copyin_fail, copyout_fail;
static bool admin, render, master;
static struct drm_ioctl_desc drm_ioctls[4], driver_ioctls[1];
#define DRM_CORE_IOCTL_COUNT (sizeof(drm_ioctls) / sizeof(drm_ioctls[0]))
static struct drm_driver driver = { 1, driver_ioctls };
static struct drm_device device = { &driver, false };
static struct drm_minor minor = { &device };
static struct drm_file priv = { &minor, false };
static struct file filp = { &priv };

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
	if (callback_zero_end > 128)
		CHECK(last_alloc_size >= callback_zero_end);
	CHECK(memcmp(data, callback_prefix, callback_prefix_size) == 0);
	for (unsigned int i = callback_zero_start; i < callback_zero_end; i++)
		CHECK(p[i] == 0);
	for (unsigned int i = 0; i < callback_fill_size; i++)
		p[i] = (unsigned char)(0x40 + i % 32);
	return callback_result;
}

/* ACTUAL_FUNCTIONS */

static unsigned char storage[544];
static unsigned char *const data = storage + 16;

static void
reset(unsigned int canonical_size, unsigned int canonical_direction,
    u32 permission)
{
	callback_calls = copyin_calls = copyout_calls = pid_updates = 0;
	alloc_calls = free_calls = last_alloc_size = 0;
	callback_zero_start = callback_zero_end = callback_fill_size = 0;
	callback_prefix_size = 0;
	callback_result = 0;
	alloc_fail = copyin_fail = copyout_fail = false;
	admin = render = master = false;
	device.unplugged = false;
	priv.authenticated = false;
	memset(drm_ioctls, 0, sizeof(drm_ioctls));
	drm_ioctls[1] = (struct drm_ioctl_desc){
		ENCODE(1, canonical_size, canonical_direction), callback,
		permission, "model_core" };
	driver_ioctls[0] = (struct drm_ioctl_desc){
		ENCODE(DRM_COMMAND_BASE, canonical_size, canonical_direction),
		callback, permission, "model_driver" };
	memset(storage, 0x7b, sizeof(storage));
}

static void
guards(unsigned int caller_size)
{
	for (unsigned int i = 0; i < 16; i++)
		CHECK(storage[i] == 0x7b);
	for (unsigned int i = 16 + caller_size; i < sizeof(storage); i++)
		CHECK(storage[i] == 0x7b);
}

static void
prepare_prefix(unsigned int size)
{
	for (unsigned int i = 0; i < size; i++)
		data[i] = (unsigned char)(0x10 + i % 16);
	callback_prefix_size = size;
	memcpy(callback_prefix, data, size);
}

static void
small_caller_large_driver(void)
{
	unsigned int out_size = 99;
	reset(256, IOC_IN | IOC_OUT, 0);
	prepare_prefix(4);
	callback_zero_start = 4;
	callback_zero_end = callback_fill_size = 256;
	long ret = drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_IN | IOC_OUT),
	    data, &out_size);
	CHECK(ret == 0);
	CHECK(out_size == 4);
	CHECK(alloc_calls == 1 && free_calls == 1);
	CHECK(callback_calls == 1 && pid_updates == 1);
	CHECK(copyin_calls == 0 && copyout_calls == 0);
	CHECK(data[0] == 0x40 && data[3] == 0x43);
	guards(4);
}

static void
large_caller_small_driver(void)
{
	unsigned int out_size;
	reset(4, IOC_IN | IOC_OUT, 0);
	prepare_prefix(256);
	callback_fill_size = 4;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 256, IOC_IN | IOC_OUT),
	    data, &out_size) == 0);
	CHECK(out_size == 256);
	CHECK(data[4] == callback_prefix[4] && data[255] == callback_prefix[255]);
	CHECK(alloc_calls == 1 && free_calls == 1);
	guards(256);
}

static void
output_only_zeroes_entire_caller(void)
{
	unsigned int out_size;
	reset(4, IOC_OUT, 0);
	callback_zero_end = 256;
	callback_fill_size = 4;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 256, IOC_OUT), data,
	    &out_size) == 0);
	CHECK(out_size == 256);
	for (unsigned int i = 4; i < 256; i++)
		CHECK(data[i] == 0);
	guards(256);
}

static void
direction_intersection_suppresses_output(void)
{
	unsigned int out_size;
	reset(4, IOC_IN, 0);
	prepare_prefix(4);
	callback_fill_size = 4;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_IN | IOC_OUT),
	    data, &out_size) == 0);
	CHECK(out_size == 0);
	CHECK(memcmp(data, callback_prefix, 4) == 0);
	guards(4);
}

static void
zero_size_accepts_null_buffer(void)
{
	unsigned int out_size;
	reset(0, 0, 0);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 0, 0), NULL,
	    &out_size) == 0);
	CHECK(out_size == 0 && callback_calls == 1);
	CHECK(alloc_calls == 0 && free_calls == 0);
}

static void
permission_error_retains_output(void)
{
	unsigned int out_size;
	reset(4, IOC_OUT, DRM_AUTH);
	long ret = drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size);
	CHECK(ret == -EACCES);
	CHECK(out_size == 4 && callback_calls == 0 && pid_updates == 1);
	CHECK(data[0] == 0 && data[3] == 0);
	CHECK(copyout_calls == 0);
	guards(4);
}

static void
driver_error_retains_output(void)
{
	unsigned int out_size;
	reset(4, IOC_OUT, 0);
	callback_fill_size = 4;
	callback_result = -EIO;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == -EIO);
	CHECK(out_size == 4 && data[3] == 0x43 && callback_calls == 1);
	guards(4);
}

static void
unplugged_has_no_output_or_dispatch(void)
{
	unsigned int out_size = 99;
	reset(4, IOC_OUT, 0);
	device.unplugged = true;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == -ENODEV);
	CHECK(out_size == 0 && callback_calls == 0 && pid_updates == 0);
	guards(0);
}

static void
invalid_type_has_no_output(void)
{
	unsigned int out_size = 99;
	reset(4, IOC_OUT, 0);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT) ^ (1U << 8),
	    data, &out_size) == -ENOTTY);
	CHECK(out_size == 0 && callback_calls == 0);
	guards(0);
}

static void
invalid_driver_index_has_no_dispatch(void)
{
	unsigned int out_size = 99;
	reset(4, IOC_OUT, 0);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(DRM_COMMAND_BASE + 1, 4,
	    IOC_OUT), data, &out_size) == -EINVAL);
	CHECK(out_size == 0 && callback_calls == 0);
	guards(0);
}

static void
invalid_core_index_has_no_dispatch(void)
{
	unsigned int out_size = 99;
	reset(4, IOC_OUT, 0);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(7, 4, IOC_OUT), data,
	    &out_size) == -EINVAL);
	CHECK(out_size == 0 && callback_calls == 0);
	guards(0);
}

static void
missing_handler_has_no_output(void)
{
	unsigned int out_size = 99;
	reset(4, IOC_OUT, 0);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(2, 4, IOC_OUT), data,
	    &out_size) == -EINVAL);
	CHECK(out_size == 0 && callback_calls == 0 && alloc_calls == 0);
	guards(0);
}

static void
allocation_failure_unwinds_without_output(void)
{
	unsigned int out_size = 99;
	reset(256, IOC_OUT, 0);
	alloc_fail = true;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == -ENOMEM);
	CHECK(out_size == 0 && callback_calls == 0);
	CHECK(alloc_calls == 1 && free_calls == 0);
	guards(0);
}

static void
required_native_parameters(void)
{
	unsigned int out_size = 99;
	reset(4, IOC_OUT, 0);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    NULL) == -EINVAL);
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), NULL,
	    &out_size) == -EINVAL);
	CHECK(out_size == 0 && callback_calls == 0 && alloc_calls == 0);
}

static void
driver_table_dispatch(void)
{
	unsigned int out_size;
	reset(4, IOC_OUT, DRM_AUTH);
	priv.authenticated = true;
	callback_fill_size = 4;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(DRM_COMMAND_BASE, 4,
	    IOC_OUT), data, &out_size) == 0);
	CHECK(out_size == 4 && callback_calls == 1 && data[3] == 0x43);
	guards(4);
}

static void
root_master_render_permissions(void)
{
	unsigned int out_size;
	reset(4, IOC_OUT, DRM_ROOT_ONLY | DRM_MASTER | DRM_RENDER_ALLOW);
	render = true;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == -EACCES);
	CHECK(callback_calls == 0);
	admin = true;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == -EACCES);
	CHECK(callback_calls == 0);
	master = true;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == 0);
	CHECK(callback_calls == 1);
	reset(4, IOC_OUT, 0);
	render = true;
	CHECK(drm_ioctl_kernel_data(&filp, ENCODE(1, 4, IOC_OUT), data,
	    &out_size) == -EACCES);
	CHECK(callback_calls == 0);
}

static void
user_wrapper_keeps_uaccess(void)
{
	reset(4, IOC_IN | IOC_OUT, 0);
	prepare_prefix(4);
	callback_fill_size = 4;
	CHECK(drm_ioctl(&filp, ENCODE(1, 4, IOC_IN | IOC_OUT),
	    (unsigned long)(uintptr_t)data) == 0);
	CHECK(copyin_calls == 1 && copyout_calls == 1 && callback_calls == 1);
	CHECK(data[0] == 0x40 && data[3] == 0x43);
	guards(4);
}

static void
user_copyin_fault_unwinds(void)
{
	reset(256, IOC_IN | IOC_OUT, 0);
	copyin_fail = true;
	CHECK(drm_ioctl(&filp, ENCODE(1, 4, IOC_IN | IOC_OUT),
	    (unsigned long)(uintptr_t)data) == -EFAULT);
	CHECK(copyin_calls == 1 && copyout_calls == 0 && callback_calls == 0);
	CHECK(alloc_calls == 1 && free_calls == 1);
	guards(0);
}

static void
user_copyout_fault_overrides_dispatch_error(void)
{
	reset(4, IOC_OUT, 0);
	callback_fill_size = 4;
	callback_result = -EIO;
	copyout_fail = true;
	CHECK(drm_ioctl(&filp, ENCODE(1, 4, IOC_OUT),
	    (unsigned long)(uintptr_t)data) == -EFAULT);
	CHECK(callback_calls == 1 && copyout_calls == 1);
	guards(0);
}

int
main(void)
{
	const struct { const char *name; void (*run)(void); } tests[] = {
#define CASE(test) { #test, test }
		CASE(small_caller_large_driver),
		CASE(large_caller_small_driver),
		CASE(output_only_zeroes_entire_caller),
		CASE(direction_intersection_suppresses_output),
		CASE(zero_size_accepts_null_buffer),
		CASE(permission_error_retains_output),
		CASE(driver_error_retains_output),
		CASE(unplugged_has_no_output_or_dispatch),
		CASE(invalid_type_has_no_output),
		CASE(invalid_driver_index_has_no_dispatch),
		CASE(invalid_core_index_has_no_dispatch),
		CASE(missing_handler_has_no_output),
		CASE(allocation_failure_unwinds_without_output),
		CASE(required_native_parameters),
		CASE(driver_table_dispatch),
		CASE(root_master_render_permissions),
		CASE(user_wrapper_keeps_uaccess),
		CASE(user_copyin_fault_unwinds),
		CASE(user_copyout_fault_overrides_dispatch_error),
#undef CASE
	};
	setvbuf(stdout, NULL, _IONBF, 0);
	for (unsigned int i = 0; i < sizeof(tests) / sizeof(tests[0]); i++) {
		printf("RUN %s\n", tests[i].name);
		tests[i].run();
		printf("PASS %s\n", tests[i].name);
	}
	puts("DRM_IOCTL_KERNEL_DATA_MODEL_PASS 19");
	return 0;
}
