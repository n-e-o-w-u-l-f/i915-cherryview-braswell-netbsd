/*
 * HP-I915-0078 portable reference contract; test-only, NOT NetBSD kernel code.
 * Public-source pin: NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6
 * Models ownership, failures and rollback BEFORE native ABI implementation.
 */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct backend {
    int brightness;
    int power;
    unsigned brightness_calls;
    unsigned power_calls;
    bool fail_brightness;
    bool fail_power;
};

struct registry;
struct class_device {
    struct registry *owner;
    struct backend *backend;
    int brightness, max_brightness, power;
};
struct registry {
    struct class_device *live;
    unsigned allocations, releases, registrations, unregistrations;
    bool fail_next_alloc;
};

static int backend_brightness(struct backend *b, int value)
{
    ++b->brightness_calls;
    if (b->fail_brightness) return EIO;
    b->brightness = value;
    return 0;
}
static int backend_power(struct backend *b, int value)
{
    ++b->power_calls;
    if (b->fail_power) return EIO;
    b->power = value;
    return 0;
}
static int class_register(struct registry *r, struct backend *b,
                          int brightness, int max, struct class_device **out)
{
    struct class_device *d;
    *out = NULL;
    if (b == NULL) return ENODEV; /* unsupported != success */
    if (max <= 0 || brightness < 0 || brightness > max) return EINVAL;
    if (r->live != NULL) return EBUSY; /* exactly one hardware owner */
    if (r->fail_next_alloc) {
        r->fail_next_alloc = false;
        return ENOMEM;
    }
    d = calloc(1, sizeof(*d));
    if (d == NULL) return ENOMEM;
    ++r->allocations;
    d->owner = r;
    d->backend = b;
    d->brightness = brightness;
    d->max_brightness = max;
    d->power = 1;
    r->live = d;
    ++r->registrations;
    *out = d;
    return 0;
}
static int class_set_brightness(struct class_device *d, int value)
{
    int error;
    if (d == NULL) return ENODEV;
    if (value < 0 || value > d->max_brightness) return EINVAL;
    error = backend_brightness(d->backend, value);
    if (error == 0) d->brightness = value;
    return error;
}
static int class_set_power(struct class_device *d, int on)
{
    int error;
    if (d == NULL) return ENODEV;
    if (on != 0 && on != 1) return EINVAL;
    error = backend_power(d->backend, on);
    if (error == 0) d->power = on;
    return error;
}
static int class_unregister(struct class_device **handle)
{
    struct class_device *d = *handle;
    struct registry *r;
    if (d == NULL) return 0; /* safe retry; no double free */
    r = d->owner;
    if (r->live != d) return EINVAL;
    r->live = NULL;
    ++r->unregistrations;
    ++r->releases;
    *handle = NULL;
    free(d);
    return 0;
}
static int connector_register(struct registry *r, struct backend *b,
                              struct class_device **handle,
                              bool fail_after_class_register)
{
    int error = class_register(r, b, 128, 255, handle);
    if (error) return error;
    if (fail_after_class_register) {
        error = EFAULT;
        (void)class_unregister(handle); /* same function owns unwind */
        return error;
    }
    return 0;
}

static unsigned checks;
#define CHECK(condition) do { \
    ++checks; \
    if (!(condition)) { \
        fprintf(stderr, "HP_I915_0078_FAIL line=%d check=%s\n", \
                __LINE__, #condition); \
        return 2; \
    } \
} while (0)

int main(void)
{
    struct registry r = {0};
    struct backend b = {.brightness = 128, .power = 1};
    struct backend rival = {.brightness = 128, .power = 1};
    struct class_device *d = NULL, *other = NULL;
    unsigned before_calls;

    CHECK(class_register(&r, NULL, 128, 255, &d) == ENODEV);
    CHECK(d == NULL && r.allocations == 0);
    CHECK(class_register(&r, &b, 128, 0, &d) == EINVAL);
    CHECK(d == NULL);
    r.fail_next_alloc = true;
    CHECK(class_register(&r, &b, 128, 255, &d) == ENOMEM);
    CHECK(d == NULL && r.allocations == 0);

    CHECK(class_register(&r, &b, 128, 255, &d) == 0);
    CHECK(d != NULL && r.live == d && r.allocations == 1);
    CHECK(class_register(&r, &rival, 128, 255, &other) == EBUSY);
    CHECK(other == NULL && r.registrations == 1);
    CHECK(class_set_brightness(d, -1) == EINVAL);
    CHECK(class_set_brightness(d, 256) == EINVAL);
    CHECK(b.brightness_calls == 0);
    CHECK(class_set_brightness(d, 42) == 0);
    CHECK(d->brightness == 42 && b.brightness == 42);
    b.fail_brightness = true;
    CHECK(class_set_brightness(d, 53) == EIO);
    CHECK(d->brightness == 42 && b.brightness == 42);
    b.fail_brightness = false;
    CHECK(class_set_power(d, 0) == 0);
    CHECK(d->power == 0 && d->brightness == 42);
    CHECK(b.power == 0 && b.brightness == 42);
    b.fail_power = true;
    CHECK(class_set_power(d, 1) == EIO);
    CHECK(d->power == 0 && b.power == 0);
    b.fail_power = false;
    CHECK(class_set_power(d, 3) == EINVAL);
    CHECK(class_set_power(d, 1) == 0 && d->power == 1);
    before_calls = b.brightness_calls;
    CHECK(class_set_brightness(d, 42) == 0);
    CHECK(b.brightness_calls == before_calls + 1);
    CHECK(class_unregister(&d) == 0);
    CHECK(d == NULL && r.live == NULL && r.releases == 1);
    CHECK(class_unregister(&d) == 0);
    CHECK(r.unregistrations == 1 && r.releases == 1);

    /* Model the original i915 connector late_register -EFAULT rollback. */
    CHECK(connector_register(&r, &b, &d, true) == EFAULT);
    CHECK(d == NULL && r.live == NULL && r.registrations == 2);
    CHECK(r.unregistrations == 2 && r.releases == 2);
    CHECK(connector_register(&r, &b, &d, false) == 0);
    CHECK(d != NULL && r.live == d && r.registrations == 3);
    CHECK(class_register(&r, &rival, 128, 255, &other) == EBUSY);
    CHECK(other == NULL);
    CHECK(class_unregister(&d) == 0);
    CHECK(r.live == NULL && d == NULL);
    CHECK(r.allocations == 3 && r.releases == 3);
    CHECK(r.registrations == 3 && r.unregistrations == 3);

    printf("HP_I915_0078_MODEL_PASS checks=%u allocations=%u releases=%u "
           "registrations=%u unregistrations=%u live=0 gpu=0\n",
           checks, r.allocations, r.releases, r.registrations,
           r.unregistrations);
    return 0;
}
