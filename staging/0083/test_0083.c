#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "0083_linux_backlight_abi.h"
#include <linux/err.h>

static atomic_int fail_alloc, alloc_count, free_count, callbacks, invalid_callback;
static pthread_mutex_t gate_m = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cv = PTHREAD_COND_INITIALIZER;
static atomic_int gate_enabled, gate_entered, gate_continue;

void *test_kmem_zalloc(size_t size, int flags) {
    assert(flags == 1);
    if (atomic_exchange(&fail_alloc, 0)) return NULL;
    void *p = calloc(1, size);
    if (p) ++alloc_count;
    return p;
}
void test_kmem_free(void *p, size_t size) {
    assert(size == sizeof(struct backlight_device));
    ++free_count;
    free(p);
}
static int update(struct backlight_device *bd) {
    ++callbacks;
    if (bd->props.max_brightness != 100 || bl_get_data(bd) != (void *)&callbacks) {
        ++invalid_callback;
    }
    if (atomic_load(&gate_enabled)) {
        pthread_mutex_lock(&gate_m);
        atomic_store(&gate_entered, 1);
        pthread_cond_broadcast(&gate_cv);
        while (!atomic_load(&gate_continue)) pthread_cond_wait(&gate_cv, &gate_m);
        pthread_mutex_unlock(&gate_m);
    }
    return 0;
}
static int current_brightness(struct backlight_device *bd) { return bd->props.brightness; }
static const struct backlight_ops ops = { .update_status=update, .get_brightness=current_brightness };
static struct backlight_properties props = { .brightness=30, .max_brightness=100, .power=0, .type=BACKLIGHT_RAW };
static atomic_int successes;
#define CHECK(e) do { if (!(e)) { fprintf(stderr, "FAILED %s:%d: %s\n", __FILE__, __LINE__, #e); exit(11); } ++successes; } while(0)
static void *callback_thread(void *arg) { CHECK(backlight_disable((struct backlight_device *)arg) == 0); return NULL; }
static void *unregister_thread(void *arg) { backlight_device_unregister((struct backlight_device *)arg); return NULL; }

int main(void) {
    struct backlight_device *d, *r;
    pthread_t t1, t2;
    CHECK(backlight_enable(NULL) == 0);
    CHECK(backlight_disable(NULL) == 0);
    d=backlight_device_register(NULL, NULL, &callbacks, &ops, &props);
    CHECK(IS_ERR(d) && PTR_ERR(d) == -EINVAL);
    d=backlight_device_register("intel_backlight", NULL, &callbacks, NULL, &props);
    CHECK(IS_ERR(d) && PTR_ERR(d) == -EINVAL);
    d=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, NULL);
    CHECK(IS_ERR(d) && PTR_ERR(d) == -EINVAL);
    props.max_brightness=0;
    d=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, &props);
    CHECK(IS_ERR(d) && PTR_ERR(d) == -EINVAL);
    props.max_brightness=100;
    props.brightness=101;
    d=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, &props);
    CHECK(IS_ERR(d) && PTR_ERR(d) == -EINVAL);
    props.brightness=30;
    atomic_store(&fail_alloc, 1);
    d=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, &props);
    CHECK(IS_ERR(d) && PTR_ERR(d) == -ENOMEM);
    d=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, &props);
    CHECK(!IS_ERR(d));
    CHECK(d->props.brightness == 30 && d->props.power == 0);
    CHECK(strcmp(d->name, "intel_backlight") == 0);
    r=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, &props);
    CHECK(IS_ERR(r) && PTR_ERR(r) == -EBUSY);
    CHECK(atomic_load(&alloc_count) == 2 && atomic_load(&free_count) == 1);
    CHECK(backlight_update_status(d) == 0);
    CHECK(backlight_disable(d) == 0 && d->props.power == BACKLIGHT_POWER_OFF);
    CHECK(backlight_enable(d) == 0 && d->props.power == BACKLIGHT_POWER_ON);
    CHECK(atomic_load(&callbacks) == 3 && atomic_load(&invalid_callback) == 0);
    atomic_store(&gate_enabled, 1);
    CHECK(pthread_create(&t1, NULL, callback_thread, d) == 0);
    pthread_mutex_lock(&gate_m);
    while (!atomic_load(&gate_entered)) pthread_cond_wait(&gate_cv, &gate_m);
    pthread_mutex_unlock(&gate_m);
    CHECK(pthread_create(&t2, NULL, unregister_thread, d) == 0);
    /* Avoid scheduling-dependent wait: wait for unregister to stop new calls
     * by checking it under exact test kernel mock registry? No exported state.
     * Instead release active callback, then join both before new registration. */
    pthread_mutex_lock(&gate_m);
    atomic_store(&gate_continue, 1);
    pthread_cond_broadcast(&gate_cv);
    pthread_mutex_unlock(&gate_m);
    CHECK(pthread_join(t1, NULL) == 0);
    CHECK(pthread_join(t2, NULL) == 0);
    CHECK(atomic_load(&alloc_count) == atomic_load(&free_count));
    atomic_store(&gate_enabled, 0);
    r=backlight_device_register("intel_backlight", NULL, &callbacks, &ops, &props);
    CHECK(!IS_ERR(r));
    CHECK(backlight_enable(r) == 0);
    backlight_device_unregister(r);
    CHECK(atomic_load(&alloc_count) == atomic_load(&free_count));
    printf("HP_I915_0083_STAGED_ABI_PASS checks=%d alloc=%d free=%d callbacks=%d\n",
        atomic_load(&successes), atomic_load(&alloc_count),
        atomic_load(&free_count), atomic_load(&callbacks));
    return 0;
}
