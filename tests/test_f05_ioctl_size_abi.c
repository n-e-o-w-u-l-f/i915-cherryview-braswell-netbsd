/* SPDX-License-Identifier: MIT */
/* Host-only encoding/size contract derived from pinned Linux/NetBSD headers.
 * This is not a kernel-header compilation or a DRM dispatch implementation. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "CHECK_FAILED %s\n", #x); abort(); \
} } while (0)
#define LINUX_IOC_SIZEBITS 14U
#define LINUX_SIZE_MASK ((1U << LINUX_IOC_SIZEBITS) - 1U)
#define NETBSD_IOCPARM_MASK 0x1fffU
#define IOCTL_SIZE_SHIFT 16U
#define NETBSD_IOCPARM_MAX 4096U /* NBPG modeled as 4 KiB here */
#define IOC_IN 0x80000000U
#define IOC_OUT 0x40000000U
#define IOC_VOID 0x20000000U
#define DRM_GET_CAP_NR 0x0cU
#define DRM_IOCTL_TYPE 0x64U
#ifdef MUTATE_LINUX_SIZE_MASK_13
#define LINUX_SIZE(x) (((x) >> IOCTL_SIZE_SHIFT) & NETBSD_IOCPARM_MASK)
#else
#define LINUX_SIZE(x) (((x) >> IOCTL_SIZE_SHIFT) & LINUX_SIZE_MASK)
#endif
#define NETBSD_SIZE(x) (((x) >> IOCTL_SIZE_SHIFT) & NETBSD_IOCPARM_MASK)
static uint32_t drm_user_cmd(unsigned encoded_size)
{
    CHECK(encoded_size <= LINUX_SIZE_MASK);
    return IOC_IN | IOC_OUT | (encoded_size << IOCTL_SIZE_SHIFT) |
        (DRM_IOCTL_TYPE << 8) | DRM_GET_CAP_NR;
}
static unsigned linux_ksize(unsigned in_size, unsigned out_size,
    unsigned drv_size)
{
    unsigned size = in_size > out_size ? in_size : out_size;
#ifndef MUTATE_SKIP_DRIVER_SIZE
    if (size < drv_size)
        size = drv_size;
#else
    (void)drv_size;
#endif
    return size;
}
struct drm_get_cap_pinned {
    uint64_t capability;
    uint64_t value;
};
_Static_assert(sizeof(struct drm_get_cap_pinned) == 16,
    "Pinned Linux DRM_GET_CAP descriptor is two __u64 members");
static bool accepted_by_netbsd(unsigned size)
{
#ifdef MUTATE_PAGE_EDGE
    return size < NETBSD_IOCPARM_MAX;
#else
    return size <= NETBSD_IOCPARM_MAX;
#endif
}
static bool safe_kernel_data_capacity(unsigned allocated, unsigned required)
{
#ifdef MUTATE_TRUST_USER_SIZE
    (void)required;
    return allocated <= NETBSD_IOCPARM_MAX;
#else
    return allocated >= required;
#endif
}
static void verify_sizes(void)
{
    const uint32_t small = drm_user_cmd(8);
    const uint32_t normal = drm_user_cmd(16);
    const uint32_t edge = drm_user_cmd(4096);
    const uint32_t too_big = drm_user_cmd(4097);
    const uint32_t high = drm_user_cmd(8192);
    const uint32_t highest = drm_user_cmd(16383);
    CHECK(LINUX_SIZE(small) == 8 && NETBSD_SIZE(small) == 8);
    CHECK(LINUX_SIZE(normal) == 16 && NETBSD_SIZE(normal) == 16);
    CHECK(LINUX_SIZE(edge) == 4096 && NETBSD_SIZE(edge) == 4096);
    CHECK(accepted_by_netbsd(NETBSD_SIZE(edge)));
    CHECK(!accepted_by_netbsd(NETBSD_SIZE(too_big)));
    CHECK(LINUX_SIZE(high) == 8192 && NETBSD_SIZE(high) == 0);
    CHECK((high & IOC_VOID) != 0); /* Linux size bit 13 overlaps NetBSD VOID. */
    CHECK(LINUX_SIZE(highest) == 16383 && NETBSD_SIZE(highest) == 8191);
    CHECK(!accepted_by_netbsd(NETBSD_SIZE(highest)));
    /* Linux DRM supports shorter user structs with driver-defined ksize. */
    CHECK(linux_ksize(8, 8, sizeof(struct drm_get_cap_pinned)) == 16);
    CHECK(!safe_kernel_data_capacity(NETBSD_SIZE(small), 16));
    CHECK(safe_kernel_data_capacity(16, 16));
    CHECK(!safe_kernel_data_capacity(NETBSD_SIZE(high), 8192));
    puts("F05_IOCTL_SIZE_ABI_MODEL_PASS 13_CONTRACTS");
}
int main(void) { verify_sizes(); return 0; }
