/* SPDX-License-Identifier: MIT */
/*
 * F02 FILE-owner lifetime accounting model, NOT a NetBSD kernel provider.
 * Models independent native file references, Linux file strong refs, pre-open
 * reservations, delayed final release, and LWP-key quiescence accounting.
 * Does NOT model actual locks, LWP identity, DRM callbacks, VM/UVM, or ABI.
 */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "CHECK_FAILED %s:%d %s\n", __FILE__, __LINE__, #expr); \
    abort(); \
} } while (0)

struct world {
    unsigned module_pins;
    unsigned task_spares;
    unsigned file_owners;
    unsigned user_lwp_tasks;
    unsigned release_calls;
};
struct owner {
    struct world *world;
    unsigned native_refs;
    unsigned linux_refs;
    bool native_attached;
    bool module_pin;
    bool task_spare;
    bool work_reserved;
    bool driver_open;
    bool deferred;
    bool released;
};

static bool
quiesce_ready(const struct world *w)
{
    return w->module_pins == 0 && w->task_spares == 0 &&
        w->file_owners == 0 && w->user_lwp_tasks == 0;
}

static void
finish_release(struct owner *o, bool sleepable)
{
    CHECK(sleepable); /* actual NetBSD last task put must be sleepable */
    CHECK(o->driver_open && o->linux_refs == 0 && !o->released);
    CHECK(o->module_pin && o->task_spare && o->work_reserved);
    CHECK(o->world->module_pins > 0);
    CHECK(o->world->task_spares > 0);
    CHECK(o->world->file_owners > 0);
    o->world->release_calls++;
    o->world->file_owners--;
    o->world->task_spares--;
    o->world->module_pins--;
    o->driver_open = false;
    o->released = true;
    o->module_pin = o->task_spare = o->work_reserved = false;
    o->deferred = false;
}

static void
abort_prepublication(struct owner *o)
{
    CHECK(!o->native_attached && o->native_refs == 0);
    if (o->driver_open) {
        CHECK(o->linux_refs == 1);
        o->linux_refs = 0;
        finish_release(o, true); /* while caller is in its entered task */
        return;
    }
    if (o->linux_refs) {
        CHECK(o->linux_refs == 1);
        o->world->file_owners--;
        o->linux_refs = 0;
    }
    if (o->task_spare) {
        CHECK(o->world->task_spares > 0);
        o->world->task_spares--;
        o->task_spare = false;
    }
    if (o->module_pin) {
        CHECK(o->world->module_pins > 0);
        o->world->module_pins--;
        o->module_pin = false;
    }
    o->work_reserved = false;
    o->released = true;
}

/* fail_stage=1..6 injects failure before native fd publication. */
static bool
open_owner(struct owner *o, struct world *w, unsigned fail_stage)
{
    CHECK(fail_stage <= 6);
    memset(o, 0, sizeof(*o));
    o->world = w;
    if (fail_stage == 1)
        return false; /* task/module admission rejected before allocation */
    w->module_pins++;
    o->module_pin = true;
    if (fail_stage == 2)
        goto fail;
    w->task_spares++;
    o->task_spare = true;
    if (fail_stage == 3)
        goto fail;
    o->work_reserved = true; /* preallocated pending finalization slot */
    if (fail_stage == 4)
        goto fail;
    w->file_owners++;
    o->linux_refs = 1; /* native file will own this reference at publish */
    if (fail_stage == 5)
        goto fail;
    o->driver_open = true;
    if (fail_stage == 6)
        goto fail;
    o->native_refs = 1;
    o->native_attached = true;
#ifdef MUTATE_SKIP_SPARE
    o->task_spare = false; /* broken release reservation transfer */
    w->task_spares--;
#endif
    return true;
fail:
    abort_prepublication(o);
    return false;
}

static bool
linux_view_get(struct owner *o) /* caller already pins the native file */
{
    if (!o->native_attached || o->native_refs == 0)
        return false;
    CHECK(o->linux_refs > 0 && !o->released);
    o->linux_refs++;
    return true;
}

static void
linux_ref_put(struct owner *o, bool sleepable)
{
    CHECK(o->linux_refs > 0 && !o->released);
    o->linux_refs--;
    if (o->linux_refs)
        return;
#ifdef MUTATE_DROP_MODULE_PIN
    /* Broken: module may unload while ->release still has to run. */
    o->module_pin = false;
    o->world->module_pins--;
#endif
    if (sleepable) {
        finish_release(o, true);
        return;
    }
#ifdef MUTATE_UNSLEEPABLE_SYNC
    finish_release(o, false); /* broken: calls last task put in atomic ctx */
#else
    CHECK(o->work_reserved && !o->deferred);
    o->deferred = true; /* queue a previously reserved ticket, not alloc */
#endif
}

static void
native_fd_dup(struct owner *o)
{
    CHECK(o->native_attached && o->native_refs > 0);
    o->native_refs++; /* dup shares the same native struct file */
}

static void
native_fd_close(struct owner *o, bool sleepable)
{
    CHECK(o->native_refs > 0 && o->native_attached);
    o->native_refs--;
    if (o->native_refs)
        return;
    /* This is the single NetBSD fo_close of the native file. */
    o->native_attached = false;
#ifdef MUTATE_EARLY_RELEASE
    /* Broken: assumes final native close is final Linux strong reference. */
    o->linux_refs = 1;
#endif
    linux_ref_put(o, sleepable);
}

static void
drain_deferred(struct owner *o)
{
    CHECK(o->deferred && o->linux_refs == 0 && !o->released);
    finish_release(o, true); /* simulated reserved sleepable worker */
}

static void
assert_world_empty(const struct world *w, unsigned releases)
{
    CHECK(quiesce_ready(w));
    CHECK(w->release_calls == releases);
}

static void
test_rollback(void)
{
    for (unsigned i = 1; i <= 6; ++i) {
        struct world w = {0};
        struct owner o;
        CHECK(!open_owner(&o, &w, i));
        CHECK(!o.native_attached && o.native_refs == 0);
        assert_world_empty(&w, i == 6 ? 1U : 0U);
    }
}

static void
test_linux_outlives_native(void)
{
    struct world w = {0};
    struct owner o;
    CHECK(open_owner(&o, &w, 0));
    CHECK(linux_view_get(&o));
    CHECK(o.linux_refs == 2);
    native_fd_close(&o, true);
    CHECK(!o.native_attached && o.linux_refs == 1);
    CHECK(!o.released && w.module_pins == 1 && w.release_calls == 0);
    CHECK(!linux_view_get(&o)); /* cannot borrow stale native file */
    linux_ref_put(&o, true);
    CHECK(o.released && !o.deferred);
    assert_world_empty(&w, 1);
}

static void
test_native_dup(void)
{
    struct world w = {0};
    struct owner o;
    CHECK(open_owner(&o, &w, 0));
    native_fd_dup(&o);
    native_fd_close(&o, true);
    CHECK(o.native_attached && o.native_refs == 1 && w.release_calls == 0);
    native_fd_close(&o, true);
    CHECK(o.released && w.release_calls == 1);
    assert_world_empty(&w, 1);
}

static void
test_atomic_last_put(void)
{
    struct world w = {0};
    struct owner o;
    CHECK(open_owner(&o, &w, 0));
    CHECK(linux_view_get(&o));
    native_fd_close(&o, true);
    linux_ref_put(&o, false); /* possible non-sleepable last Linux ref */
    CHECK(o.deferred && !o.released && w.module_pins == 1);
    CHECK(!quiesce_ready(&w));
    drain_deferred(&o);
    CHECK(o.released && !o.deferred);
    assert_world_empty(&w, 1);
}

static void
test_atomic_native_close(void)
{
    struct world w = {0};
    struct owner o;
    CHECK(open_owner(&o, &w, 0));
    native_fd_close(&o, false);
    CHECK(o.deferred && !o.released);
    drain_deferred(&o);
    assert_world_empty(&w, 1);
}

static void
test_lwp_independent_quiesce(void)
{
    struct world w = {0};
    struct owner o;
    w.user_lwp_tasks = 1; /* task key still held by live caller LWP */
    CHECK(open_owner(&o, &w, 0));
    native_fd_close(&o, true);
    CHECK(w.release_calls == 1 && !quiesce_ready(&w));
    w.user_lwp_tasks = 0; /* native LWP-exit callback releases final owner */
    assert_world_empty(&w, 1);
}

int
main(void)
{
    test_rollback();
    test_linux_outlives_native();
    test_native_dup();
    test_atomic_last_put();
    test_atomic_native_close();
    test_lwp_independent_quiesce();
    puts("F02_FILE_OWNER_MODEL_PASS 6_SCENARIOS");
    return 0;
}
