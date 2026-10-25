/* SPDX-License-Identifier: MIT */
/* Standalone F03 callback/ref transfer oracle; NOT a NetBSD kernel ABI test. */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "CHECK_FAILED %s\n", #x); abort(); } } while (0)
#define OUT 1
struct linux_file { unsigned refs, releases; };
struct native_file;
struct fileops {
    int (*fo_ioctl)(struct native_file *, int, int *);
    int (*fo_ioctl_user)(struct native_file *, int, int *, int *);
    struct linux_file *(*fo_linux_file)(struct native_file *);
};
struct native_file { const struct fileops *f_ops; struct linux_file *linux; bool active; unsigned pins; };
static unsigned old_calls, user_calls, fd_gets, fd_puts, copies;
static int copy_failure;
static int old_ioctl(struct native_file *f, int cmd, int *out)
{ (void)f; (void)cmd; ++old_calls; *out = 13; return -7; }
static int old_success(struct native_file *f, int cmd, int *out)
{ (void)f; (void)cmd; ++old_calls; *out = 14; return 0; }
static int user_ioctl(struct native_file *f, int cmd, int *out, int *address)
{ (void)f; (void)cmd; CHECK(address != NULL); ++user_calls; *out = 37; return -9; }
static int copyout_value(int value, int *user)
{ ++copies; if (copy_failure) return 14; *user = value; return 0; }
static int dispatch(struct native_file *f, bool output, unsigned size, int *user)
{
    int data = 0, err;
#ifdef F03_MUTATE_IGNORE_USER_CALLBACK
    err = f->f_ops->fo_ioctl(f, 1, &data);
#else
    if (f->f_ops->fo_ioctl_user)
        err = f->f_ops->fo_ioctl_user(f, 1, &data, user);
    else
        err = f->f_ops->fo_ioctl(f, 1, &data);
#endif
#ifdef F03_MUTATE_LEGACY_ERROR_COPYOUT
    if (output && size) {
#elif defined(F03_MUTATE_NO_ERROR_COPYOUT)
    if (err == 0 && output && size) {
#else
    if ((err == 0 || f->f_ops->fo_ioctl_user != NULL) && output && size) {
#endif
        const int copyerror = copyout_value(data, user);
        if (copyerror) err = copyerror;
    }
    return err;
}
static struct linux_file *linux_view(struct native_file *f)
{
    CHECK(f->active && f->pins != 0);
#ifdef F03_MUTATE_DROP_STRONG_REF
    return f->linux;
#else
    CHECK(f->linux->refs != 0);
    ++f->linux->refs;
    return f->linux;
#endif
}
static struct native_file *fd_get(struct native_file *f)
{ ++fd_gets; if (!f->active) return NULL; ++f->pins; return f; }
static void fd_put(struct native_file *f)
{ CHECK(f->pins > 0); ++fd_puts; --f->pins; }
static struct linux_file *get_linux_file(struct native_file *f)
{
    struct native_file *pin = fd_get(f);
    struct linux_file *lf = NULL;
    if (!pin) return NULL;
#ifdef F03_MUTATE_EARLY_FD_PUT
    fd_put(f);
#endif
    if (pin->f_ops && pin->f_ops->fo_linux_file)
        lf = pin->f_ops->fo_linux_file(pin);
#ifndef F03_MUTATE_EARLY_FD_PUT
    fd_put(f);
#endif
    return lf;
}
static void fput_linux(struct linux_file *lf)
{ CHECK(lf->refs > 0); if (--lf->refs == 0) ++lf->releases; }
static void check_ioctls(void)
{
    const struct fileops legacy = {old_ioctl, NULL, NULL};
    const struct fileops legacy_ok = {old_success, NULL, NULL};
    const struct fileops optin = {old_ioctl, user_ioctl, NULL};
    struct native_file f = {.f_ops=&legacy, .active=true};
    int user = 111;
    CHECK(dispatch(&f, true, sizeof(user), &user) == -7);
    CHECK(user == 111 && copies == 0 && old_calls == 1);
    f.f_ops = &legacy_ok;
    CHECK(dispatch(&f, true, sizeof(user), &user) == 0);
    CHECK(user == 14 && copies == 1 && old_calls == 2);
    f.f_ops = &optin;
    CHECK(dispatch(&f, true, sizeof(user), &user) == -9);
    CHECK(user == 37 && copies == 2 && user_calls == 1);
    copy_failure = 1;
    user = 123;
    CHECK(dispatch(&f, true, sizeof(user), &user) == 14);
    CHECK(user == 123 && copies == 3);
    copy_failure = 0;
    CHECK(dispatch(&f, false, sizeof(user), &user) == -9);
    CHECK(dispatch(&f, true, 0, &user) == -9);
    CHECK(copies == 3 && user_calls == 4);
}
static void check_file_bridge(void)
{
    const struct fileops drm = {old_ioctl, NULL, linux_view};
    const struct fileops legacy = {old_ioctl, NULL, NULL};
    struct linux_file linux = {.refs=1};
    struct native_file f = {.f_ops=&drm, .linux=&linux, .active=true};
    struct linux_file *borrow = get_linux_file(&f);
    CHECK(borrow == &linux && borrow->refs == 2);
    CHECK(f.pins == 0 && fd_gets == 1 && fd_puts == 1);
    f.active = false; /* final native close drops its own reference */
    fput_linux(&linux);
    CHECK(linux.refs == 1 && linux.releases == 0);
    fput_linux(borrow);
    CHECK(linux.refs == 0 && linux.releases == 1);
    CHECK(get_linux_file(&f) == NULL && fd_gets == 2 && fd_puts == 1);
    f.active = true;
    f.f_ops = &legacy;
    CHECK(get_linux_file(&f) == NULL && fd_gets == 3 && fd_puts == 2);
    CHECK(f.pins == 0);
}
int main(void)
{ check_ioctls(); check_file_bridge(); puts("F03_FILEOPS_BRIDGE_MODEL_PASS 10_CONTRACTS"); return 0; }
