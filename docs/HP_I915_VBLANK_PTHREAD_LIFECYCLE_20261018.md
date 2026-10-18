# HP i915 VBlank worker — source-extracted pthread lifecycle validation

**Date:** 2026-10-18. **Result:** PASS as a host-thread mock, **NOT** a NetBSD native object/kernel or real IRQ/KMS acceptance.

## Exact source identity

- Producer: `n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd` work branch `work/hp-native-drm-stage-replay-20261015`; test HEAD `50e2a0bbdc04dedaf6a30f9db1b3a67e5fd593fd`.
- Unmodified tested source: `compat/native-runtime/drm-vblank/src/drm_vblank_work.c`, required source SHA256 `fe31c46d491a4b93589d6c8308895266de22ee66913864ddde8b1234c29b12be`. The source worker implementation itself was **not changed** during this step.
- Persistent regression: `tests/test_i915_netbsd_vblank_pthread_lifecycle.py`, imports 14 functions via exact source-bound C definitions rather than reimplementing them.
- Real compiler execution: Legion host `cc -std=gnu11 -Wall -Wextra -Werror -fsanitize=undefined -fno-omit-frame-pointer -pthread`. The native functions run with pthread mutex/condition variable stand-ins for NetBSD spinlock and IRQ wait primitives. Thread scheduling, IRQ disable behavior and NetBSD's actual `kthread_create` semantics are **mocked**.

## Seven positive C thread-lifecycle cases

1. Future-VBlank work acquires an IRQ reference; a simulated IRQ transfers pending to ready, releases the reference and flush waits for the callback.
2. `flush_all` waits until a callback already running on the worker has completed, using the native FIFO completion fence.
3. `cancel_sync` waits until a running callback is complete; the work is not falsely reported as removed from pending.
4. Pending, not-yet-ready work cancellation drops exactly one IRQ reference and unlinks the node.
5. Failed IRQ-reference acquisition returns its error without queueing work or leaking a reference.
6. **True threaded FIFO snapshot:** with first callback blocked, flush-all queues its fence; the callback then requeues itself behind that fence. The flush returns **before** the second callback completes and does not wait indefinitely for later work. The second callback is released and drained independently.
7. Worker teardown cancels outstanding pending work, releases its IRQ references, joins the worker and rejects new submissions; final get/put counts balance.

Two deliberately unsafe **compiled source mutants** are rejected: removing `nb_vblank_ready`'s `pending_ref = false` causes a bounded flush deadlock (expected SIGALRM, 2s), and removing `drm_vblank_cancel_pending_works()` from shutdown triggers the reference-leak assertion (SIGABRT). All cases passed in one run and **8 consecutive full independent reruns** on Legion. The first test harness failed compilation because of its own `puts` counter naming collision and missing prototypes; corrected without touching the driver. An initial negative control produced SIGALRM rather than SIGABRT because the targeted bug genuinely deadlocks; now detected as the precise expected negative signature.

Markers: `I915_NETBSD_VBLANK_EXTRACTED_C11_PTHREAD_7_LIFECYCLE_CASES_PASS`, `I915_NETBSD_VBLANK_PTHREAD_2_UNSAFE_SOURCE_MUTATIONS_REFUSED`, and `VBLANK_SOURCE_EXTRACTED_PTHREAD_8_REPEATED_RUNS_PASS`.

## Remaining source, ABI and physical gates

The host fixture is **not** a NetBSD amd64 `-Werror` native `drm_vblank_work.o`, `ld -r`, an actual i915 IRQ/VBlank deadline, kernel thread priority/SCHED_FIFO equivalence, scheduler wakeup race proof or complete 323 modern Linux i915 + DRM/TTM source/ABI integration. Earlier pinned Linux-vs-NetBSD pending/ready fence source comparisons remain source-only. Full i915 semantic matrix stays **300 UNREVIEWED + 23 CHV-specific reference-inapplicable**. The standard recovery kernel remains historical last-known-safe; no HP operation occurred.

Next: complete native VBlank scheduling/cancellation/teardown contracts and physical-independent error/dump logging prerequisites as part of 323 source closure; then and only then native compile/link on the authorized HP, independent recovery-safe installation, **user-installed-kernel test**, and physical KMS validation afterward.
