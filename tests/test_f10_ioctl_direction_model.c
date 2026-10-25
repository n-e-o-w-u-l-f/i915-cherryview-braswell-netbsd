/* SPDX-License-Identifier: MIT */
/* Source-derived NetBSD ioctl preparation under STUB semantics.
 * This IS NOT a NetBSD kernel build or a production direction fix.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "CHECK_FAILED %s\n", #x); abort(); } } while (0)
#define IOC_IN  0x80000000UL
#define IOC_OUT 0x40000000UL
#define IOC_VOID 0x20000000UL
#define IOCPARM_LEN(c) (((c) >> 16) & 0x1fffUL)
#define UIO_WRITE 1
#define EFAULT 14
#define __predict_false(x) (x)
#define zero_size(n) (n)
#define SCARG(p, n) ((p)->n)
struct args { unsigned int fd; unsigned char *data; };
static unsigned copied, traced;
static bool simulate_unreadable;
static int copyin(const void *src, void *dst, size_t count)
{
    copied++;
    if (simulate_unreadable) return EFAULT;
    memcpy(dst, src, count);
    return 0;
}
static void ktrgenio(unsigned fd, int mode, void *u, size_t size, int err)
{
    (void)u;
    CHECK(fd == 7 && mode == UIO_WRITE && size == 16 && err == 0);
    traced++;
}
static int marshal(unsigned long com, unsigned char *user, bool corrected,
                   unsigned char *snapshot)
{
    unsigned char stkbuf[64];
    memset(stkbuf, 0xcc, sizeof(stkbuf));
    struct args args = {7, user};
    struct args *uap = &args;
    void *data = stkbuf;
    size_t size = IOCPARM_LEN(com);
    size_t alloc_size = size;
    int error = 0;
    copied = traced = 0;
    CHECK(size == 16);
    if (corrected) {
        /* Target direction contract only; NOT a production kernel patch. */
        if (com & IOC_OUT) {
            error = copyin(SCARG(uap, data), data, size);
            if (error) goto out;
        } else if (com & IOC_IN) {
            memset(data, 0, size);
        }
    } else {
#include "fixtures/f10_netbsd_sys_ioctl_prep_03d918f6.inc"
    }
out:
    memcpy(snapshot, stkbuf, 16);
    return error;
}
static unsigned long linux_cmd(unsigned long direction)
{
    return direction | (16UL << 16) | ((unsigned long)'d' << 8) | 0x0dUL;
}
int main(void)
{
    unsigned char user[16], actual[16], corrected[16];
    memset(user, 0x42, sizeof(user));
    simulate_unreadable = false;
    /* Linux _IOW: user -> kernel, but NetBSD IOC_OUT zeros the data. */
    CHECK(marshal(linux_cmd(IOC_OUT), user, false, actual) == 0);
    CHECK(actual[0] == 0 && actual[15] == 0 && copied == 0);
    CHECK(marshal(linux_cmd(IOC_OUT), user, true, corrected) == 0);
    CHECK(corrected[0] == 0x42 && corrected[15] == 0x42 && copied == 1);
    /* Linux _IOR: kernel -> user, but NetBSD IOC_IN calls copyin. */
    simulate_unreadable = true;
    CHECK(marshal(linux_cmd(IOC_IN), user, false, actual) == EFAULT);
    CHECK(copied == 1);
    CHECK(marshal(linux_cmd(IOC_IN), user, true, corrected) == 0);
    CHECK(corrected[0] == 0 && corrected[15] == 0 && copied == 0);
    /* Linux _IOWR: bidirectional, so the original and target both copy in. */
    simulate_unreadable = false;
    CHECK(marshal(linux_cmd(IOC_IN | IOC_OUT), user, false, actual) == 0);
    CHECK(actual[0] == 0x42 && actual[15] == 0x42 && copied == 1);
    CHECK(marshal(linux_cmd(IOC_IN | IOC_OUT), user, true, corrected) == 0);
    CHECK(corrected[0] == 0x42 && corrected[15] == 0x42 && copied == 1);
    puts("F10_NETBSD_LINUX_IOCTL_DIRECTION_MISMATCH_CONFIRMED 3_DIRECTIONS");
    return 0;
}
