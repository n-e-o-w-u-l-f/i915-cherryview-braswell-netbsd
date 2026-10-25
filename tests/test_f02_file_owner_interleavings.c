/* SPDX-License-Identifier: MIT */
/* Bounded sequential interleavings of the F02 reference model.
 * Deliberately NOT a concurrent/atomic/NetBSD kernel ABI test. */
#define main f02_model_original_main
#include "test_f02_file_owner_model.c"
#undef main

static unsigned long examined;

static unsigned
popcount(unsigned v)
{
    unsigned c = 0;
    for (; v; v >>= 1)
        c += v & 1U;
    return c;
}

/* Every close/put ordering that starts with native-owned+borrowed Linux
 * references and releases them exactly once, under both context choices. */
static void
simulate(unsigned native_count, unsigned borrowed_count,
    unsigned order_mask, unsigned context_mask, bool lwp_owner)
{
    struct world w = {0};
    struct owner o;
    const unsigned steps = native_count + borrowed_count;
    unsigned remaining_native = native_count;
    unsigned remaining_borrowed = borrowed_count;

    if (lwp_owner)
        w.user_lwp_tasks = 1;
    CHECK(open_owner(&o, &w, 0));
    for (unsigned i = 1; i < native_count; ++i)
        native_fd_dup(&o);
    for (unsigned i = 0; i < borrowed_count; ++i)
        CHECK(linux_view_get(&o));
    CHECK(o.native_refs == native_count);
    CHECK(o.linux_refs == borrowed_count + 1);
    CHECK(w.module_pins == 1 && w.task_spares == 1);
    CHECK(!quiesce_ready(&w));

    for (unsigned i = 0; i < steps; ++i) {
        const bool linux_event = (order_mask & (1U << i)) != 0;
        const bool sleepable = (context_mask & (1U << i)) == 0;
        if (linux_event) {
            CHECK(remaining_borrowed > 0);
            linux_ref_put(&o, sleepable);
            --remaining_borrowed;
        } else {
            CHECK(remaining_native > 0);
            native_fd_close(&o, sleepable);
            --remaining_native;
        }
        const unsigned expected_linux =
            (remaining_native ? 1U : 0U) + remaining_borrowed;
        CHECK(o.native_refs == remaining_native);
        CHECK(o.native_attached == (remaining_native > 0));
        CHECK(o.linux_refs == expected_linux);
        CHECK(w.release_calls <= 1);
        if (expected_linux != 0) {
            CHECK(!o.released && !o.deferred);
            CHECK(o.module_pin && o.task_spare && o.work_reserved);
            CHECK(w.module_pins == 1 && w.task_spares == 1);
            CHECK(w.file_owners == 1 && w.release_calls == 0);
        } else if (sleepable) {
            CHECK(o.released && !o.deferred);
            CHECK(w.release_calls == 1 && w.module_pins == 0);
        } else {
            CHECK(o.deferred && !o.released);
            CHECK(w.module_pins == 1 && w.task_spares == 1);
            CHECK(w.file_owners == 1 && w.release_calls == 0);
            CHECK(!quiesce_ready(&w));
        }
    }
    CHECK(remaining_native == 0 && remaining_borrowed == 0);
    CHECK(!o.native_attached && o.linux_refs == 0);
    CHECK(!linux_view_get(&o));
    if (o.deferred) {
        CHECK(w.module_pins == 1 && w.release_calls == 0);
        drain_deferred(&o);
    }
    CHECK(o.released && !o.deferred && w.release_calls == 1);
    CHECK(!o.module_pin && !o.task_spare && !o.work_reserved);
    CHECK(quiesce_ready(&w) == !lwp_owner);
    if (lwp_owner) {
        w.user_lwp_tasks = 0;
        CHECK(quiesce_ready(&w));
    }
    assert_world_empty(&w, 1);
    ++examined;
}

static void
exhaustive(void)
{
    for (unsigned native = 1; native <= 3; ++native) {
        for (unsigned borrowed = 0; borrowed <= 3; ++borrowed) {
            const unsigned steps = native + borrowed;
            for (unsigned order = 0; order < (1U << steps); ++order) {
                if (popcount(order) != borrowed)
                    continue;
                for (unsigned context = 0; context < (1U << steps); ++context) {
                    simulate(native, borrowed, order, context, false);
                    simulate(native, borrowed, order, context, true);
                }
            }
        }
    }
    CHECK(examined > 1000);
    printf("F02_INTERLEAVINGS_PASS %lu_PATHS\n", examined);
}

static void
invalid(const char *arg)
{
    struct world w = {0};
    struct owner o;
    CHECK(open_owner(&o, &w, 0));
    if (strcmp(arg, "double_native_close") == 0) {
        native_fd_close(&o, true);
        native_fd_close(&o, true); /* must assert */
    } else if (strcmp(arg, "borrow_after_close") == 0) {
        native_fd_close(&o, true);
        CHECK(linux_view_get(&o)); /* must fail */
    } else if (strcmp(arg, "premature_worker_drain") == 0) {
        drain_deferred(&o); /* must assert */
    } else if (strcmp(arg, "double_linux_put") == 0) {
        native_fd_close(&o, true);
        linux_ref_put(&o, true); /* must assert */
    } else {
        fprintf(stderr, "UNKNOWN_TEST %s\n", arg);
        exit(2);
    }
    CHECK(0); /* negative inputs must never return */
}

int
main(int argc, char **argv)
{
    if (argc == 1)
        exhaustive();
    else if (argc == 2)
        invalid(argv[1]);
    else
        return 2;
    return 0;
}
