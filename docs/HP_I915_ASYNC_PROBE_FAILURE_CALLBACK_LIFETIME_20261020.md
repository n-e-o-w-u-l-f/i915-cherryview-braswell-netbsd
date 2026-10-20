# HP-I915: Native i915 asynchronous callback/probe failure lifecycle audit

Date: 2026-10-20 Europe/Berlin. Status: **SOURCE-PROVEN DETACH ASSERTION INVARIANT MISMATCH; NO C PATCH; NO NATIVE/HP VALIDATION**.

## Immutable provenance
- Own i915 branch at start: `work/hp-native-drm-stage-replay-20261015` @ `3402da187a04ebbe760cb8591cc67eeaf5415211`.
- NetBSD/src pin: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- [i915_pci_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c) blob `9798385b02f247c08db9b16624d5ddc9d11a8ca5`.
- [intelfb.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/intelfb.c) blob `482f05fb6879cae8bebaf9aa6e3bd054dc6118b4`.
- [i915_pci.h](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci.h) blob `8230e116a68ef7fa2a592bebe8d0dd9fc78cf86e`.
- [subr_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_autoconf.c): `config_mountroot` and `config_pending_{incr,decr}` (frozen source).
- Separate modern runtime integration remains pending: `compat/native-runtime/task/` and `compat/native-runtime/worker/` are staged candidates, **not** evidence of an integrated native i915 callback runtime.

## Concrete source mismatch

The pinned `i915drmkms_attach` creates `sc_task_wq`, initializes `sc_tasks`, and registers `i915drmkms_attach_real` through `config_mountroot`. At real attach, it assigns `sc->sc_task_thread = curlwp` before `-i915_driver_probe(...)`.

On nonzero probe error the current error arm logs and returns **without clearing `sc_task_thread`, emptying the SIMPLEQ or handling ownership of pending callbacks**. The normal path below this return drains synchronous tasks and performs `atomic_store_relaxed(&sc->sc_task_thread, NULL)`. However, `i915drmkms_detach` has unconditional `KASSERT(sc->sc_task_thread == NULL)` and `KASSERT(SIMPLEQ_EMPTY(&sc->sc_tasks))` before its workqueue and PCI cleanup. Thus a probe failure followed by detach is **source-inconsistent even when the queue is empty**. A real assertion/panic on HP has **not** been observed; the runtime detach call sequence is not asserted to occur.

Further, `intelfb_attach` stores a task inside its device softc, calls `i915drmkms_task_schedule`, and increments `config_pending` on that device. Its `intelfb_attach_task` is the only reviewed place that decrements this counter; `intelfb_detach` does not cancel a queued attach task or balance it itself. If a partially successful probe created an intelfb child before later error, the failed parent probe can strand that task/counter; exact path reachability and teardown ownership require a real callgraph and fault test. A queued task cannot just be dropped, and blindly invoking it on a torn-down display may dereference invalid state.

Also distinguish `config_mountroot` deferred callback lifetime (may run immediately if root mounted) from workqueue scheduling; device detach before deferred execution and asynchronous callbacks from other LWPs require separate synchronization and source-owner review.

## Reproducible source-pattern verification performed

GitHub connector read the exact three pinned blobs and checked eight independent predicates: (1) task-thread assignment precedes probe, (2) early error arm exists, (3) no thread clear in that arm, (4) no SIMPLEQ drain in that arm, (5–6) detach asserts null thread and empty queue, (7) intelfb schedules an attach task, and (8) intelfb counter increment/decrement is coupled to that callback. **Eight source-pattern checks PASS.** This is not a compiler, symbolic-execution, race, native fault-injection, or physical-hardware PASS.

## Minimum safe repair contract (not implemented)

1. Define explicit attachment/probe/teardown state with acceptance of new tasks only while their device, callback and workqueue owners are alive. Inspect source-derived Linux i915 probe error unwind and native child attach sequencing; do not assume the failed probe never emitted intelfb tasks.
2. On each probe-error edge, resolve all synchronous queued tasks with **owner-defined cancellation or safe completion**; balance every `config_pending` increment exactly once and prevent callback after child lifetime ends. Avoid blindly running `intelfb_attach_task` after DRM probe failure.
3. Reset `sc_task_thread` with correct publication and lifetime synchronization only after queue ownership has been settled. Prevent concurrent `i915drmkms_task_schedule` enqueue to a destroyed/NULL workqueue. Coordinate `config_detach_children`, PMF and workqueue destruction.
4. Verify `config_mountroot` deferred callback cancellation/dependence on detach before proposing actual C changes; do not assume a normal probe success unwind covers failed or re-entrant attach.
5. Build a narrow negative test matrix: probe failure before/after first intelfb task; zero/one/multiple queued callbacks; concurrent workqueue enqueue; early detach; PMF registration failure; pending mountroot callback; recovery to stock kernel. Native diagnostic build/LOCKDEBUG/SMP and actual fault-injected cleanup are required before declaring bug fixed.

## Boundaries and next action

**NEXT:** Confirm frozen i915 probe late-error reachability of intelfb attachment, identify the exact child/counter cancellation owner, and implement a **separate, narrowly scoped** test oracle for thread/queue/counter unwind. Only after that design an independent reviewable fix and test on an authorized NetBSD kernel worktree. No speculative production C edit is justified by the source-pattern test alone.

Prior `0047+0048` composite creation was provider-blocked and remains **NOT_CREATED**; do not recreate or reroute. Prior `0045` 16 negative mutations remain **NOT_RUN**. All standalone patches remain **UNINTEGRATED**. The parent 300 semantic units, combined modern DRM/TTM+i915+RTL kernel link, G01–G09 diagnostics, independently verified stock-kernel rollback, HP boot, KMS and WPA2 are **OPEN/NOT_VERIFIED**. No active driver source, HP kernel, bootloader or physical system was changed in this audit.

Governance event: `Agent-Governance/state/events/hp-i915-async-probe-fail-callback-audit-20261020.jsonl`.
