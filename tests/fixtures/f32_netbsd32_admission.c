/* Explicit FD and later-syscall environment; no Compat32 implementation. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK_FAILED %s\n",#x); abort(); } } while (0)
typedef unsigned long u_long;
#define SCARG(p, n) ((p)->n)
#define IOCGROUP(c) (((c) >> 8) & 0xffUL)
#define FREAD 0x00000001
#define FWRITE 0x00000002
#define FIOCLEX (0x20000000UL | ((u_long)'f' << 8) | 1)
#define FIONCLEX (0x20000000UL | ((u_long)'f' << 8) | 2)
#define LEGACY_SENTINEL 73
struct file;
struct fileops { int (*fo_ioctl_user)(struct file *, u_long, void *, void *); };
struct file { int f_flag; const struct fileops *f_ops; };
struct args { unsigned fd; u_long com; void *data; };
static struct file current_file;
static unsigned get_calls, put_calls, later_calls, free_calls, cloexec_calls;
static unsigned seen_fd;
static bool valid_fd, cloexec_value;
static u_long later_command;
static void *later_pointer;
static int never_dispatch(struct file *f, u_long c, void *d, void *u)
{ (void)f; (void)c; (void)d; (void)u; CHECK(false); return 0; }
static const struct fileops modern_ops = { never_dispatch }, legacy_ops = { NULL };
static struct file *fd_getfile(unsigned fd)
{ get_calls++; seen_fd = fd; return valid_fd ? &current_file : NULL; }
static void fd_putfile(unsigned fd)
{ CHECK(fd == seen_fd); put_calls++; }
static void fd_set_exclose(void *l, unsigned fd, bool enable)
{ (void)l; CHECK(fd == seen_fd); cloexec_calls++; cloexec_value = enable; }
static void kmem_free(void *memory, size_t size)
{ (void)size; free_calls++; free(memory); }

/* Only original initialization/FD/FIOCLEX/guard and original out are inserted.
 * The omitted native marshalling/conversion body is a counted continuation.
 * Its bytes are independently required to remain identical to pinned source. */
static int entry(struct args *uap)
{
    struct file *fp;
    u_long com;
    int error = 0;
    size_t size, alloc_size32, size32;
    void *memp = NULL, *memp32 = NULL;
    unsigned fd;
    void *l = NULL;
/* ACTUAL_EARLY */
    /* This is an explicit stub boundary, not a reimplementation of ioctl. */
    (void)size32;
    later_calls++;
    later_command = com;
    later_pointer = uap->data;
    error = LEGACY_SENTINEL;
/* ACTUAL_OUT */
}
static void reset(const struct fileops *ops, int flags, bool exists)
{
    get_calls = put_calls = later_calls = free_calls = cloexec_calls = 0;
    seen_fd = 99; cloexec_value = false;
    later_command = 0; later_pointer = NULL;
    current_file.f_ops = ops; current_file.f_flag = flags; valid_fd = exists;
}
static u_long command(unsigned group, unsigned size, unsigned direction)
{ return ((u_long)group << 8) | 0x0c | ((u_long)size << 16) | direction; }
static int invoke(u_long com, void *user)
{ struct args args = {7, com, user}; return entry(&args); }
static void modern_drm_all_commands(void)
{
    const unsigned directions[] = {0, 0x40000000U, 0x80000000U, 0xc0000000U};
    const unsigned sizes[] = {0, 16, 4097, 8192, 16383};
    for (unsigned d = 0; d < 4; d++) for (unsigned s = 0; s < 5; s++) {
        reset(&modern_ops, FREAD | FWRITE, true);
        int result = invoke(command('d', sizes[s], directions[d]), (void *)(uintptr_t)1);
        CHECK(result == ENOTTY);
        CHECK(get_calls == 1 && put_calls == 1);
        CHECK(later_calls == 0 && free_calls == 0 && cloexec_calls == 0);
    }
}
static void null_user_rejected(void)
{
    reset(&modern_ops, FREAD, true);
    CHECK(invoke(command('d', 0, 0), NULL) == ENOTTY);
    CHECK(get_calls == 1 && put_calls == 1 && later_calls == 0);
}
static void legacy_drm_preserved(void)
{
    const unsigned directions[] = {0, 0x40000000U, 0x80000000U, 0xc0000000U};
    const unsigned sizes[] = {0, 16, 4097, 8192, 16383};
    for (unsigned d = 0; d < 4; d++) for (unsigned s = 0; s < 5; s++) {
        reset(&legacy_ops, FREAD, true);
        u_long com = command('d', sizes[s], directions[d]);
        int result = invoke(com, (void *)(uintptr_t)1);
        CHECK(result == LEGACY_SENTINEL);
        CHECK(later_command == com && later_pointer == (void *)(uintptr_t)1);
        CHECK(get_calls == 1 && put_calls == 1 && later_calls == 1);
        CHECK(free_calls == 0 && cloexec_calls == 0);
    }
}
static void non_drm_hook_preserved(void)
{
    const unsigned directions[] = {0, 0x40000000U, 0x80000000U, 0xc0000000U};
    const unsigned sizes[] = {0, 16, 4097, 8192, 16383};
    for (unsigned d = 0; d < 4; d++) for (unsigned s = 0; s < 5; s++) {
        reset(&modern_ops, FWRITE, true);
        u_long com = command('x', sizes[s], directions[d]);
        int result = invoke(com, (void *)(uintptr_t)1);
        CHECK(result == LEGACY_SENTINEL);
        CHECK(later_command == com && later_pointer == (void *)(uintptr_t)1);
        CHECK(get_calls == 1 && put_calls == 1 && later_calls == 1);
    }
}
static void invalid_fd_rejected(void)
{
    reset(&modern_ops, FREAD, false);
    CHECK(invoke(command('d', 16, 0xc0000000U), (void *)(uintptr_t)1) == EBADF);
    CHECK(get_calls == 1 && put_calls == 0 && later_calls == 0);
}
static void missing_access_precedes_gate(void)
{
    reset(&modern_ops, 0, true);
    CHECK(invoke(command('d', 16, 0xc0000000U), (void *)(uintptr_t)1) == EBADF);
    CHECK(get_calls == 1 && put_calls == 1 && later_calls == 0);
}
static void read_write_access_reaches_gate(void)
{
    const int flags[] = {FREAD, FWRITE, FREAD | FWRITE};
    for (unsigned i = 0; i < 3; i++) {
        reset(&modern_ops, flags[i], true);
        CHECK(invoke(command('d', 16, 0xc0000000U), NULL) == ENOTTY);
        CHECK(get_calls == 1 && put_calls == 1 && later_calls == 0);
    }
}
static void fioclex_preserved(void)
{
    reset(&modern_ops, FREAD, true);
    CHECK(invoke(FIOCLEX, (void *)(uintptr_t)1) == 0);
    CHECK(cloexec_calls == 1 && cloexec_value);
    CHECK(get_calls == 1 && put_calls == 1 && later_calls == 0);
}
static void fionclex_preserved(void)
{
    reset(&modern_ops, FREAD, true);
    CHECK(invoke(FIONCLEX, (void *)(uintptr_t)1) == 0);
    CHECK(cloexec_calls == 1 && !cloexec_value);
    CHECK(get_calls == 1 && put_calls == 1 && later_calls == 0);
}
#define RUN(name) do { puts("RUN " #name); name(); puts("PASS " #name); } while (0)
int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    RUN(modern_drm_all_commands); RUN(null_user_rejected);
    RUN(legacy_drm_preserved); RUN(non_drm_hook_preserved);
    RUN(invalid_fd_rejected); RUN(missing_access_precedes_gate);
    RUN(read_write_access_reaches_gate); RUN(fioclex_preserved); RUN(fionclex_preserved);
    puts("F32_SOURCE_ADMISSION_PASS 9");
    return 0;
}
