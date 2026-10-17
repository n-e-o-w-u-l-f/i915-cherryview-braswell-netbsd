# NetBSD 11 VBlank work — frozen-reference scheduler/flush semantic gaps

Status: SOURCE REVIEW / OPEN, **not** a build, native runtime test or kernel-ready fix.
Date: 2026-10-18
Scope: HP-I915 VBlank work in NetBSD 11 amd64; Cherryview 8086:22b1; project work branch only.

## Exact source authorities

- Linux reference: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`, `drivers/gpu/drm/drm_vblank_work.c`.
- NetBSD reference: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, `sys/kern/kern_kthread.c` and `sys/sys/kthread.h`.
- Candidate source: `compat/native-runtime/drm-vblank/src/drm_vblank_work.c`, initially audited at branch HEAD `d8138a0b73b5eb0240b66c7999de6735549723ea`.
- Source-level harnesses: `tests/test_i915_netbsd_vblank_actual_c_state.py` (22 mocked state cases) and `tests/test_i915_netbsd_vblank_core_lifecycle.py` (4 mocked initializer/cleanup failure cases). Neither verifies actual HP scheduling/IRQ latency.

## Finding VBLANK-SCHED-01 — scheduler class differs

Frozen Linux `drm_vblank_worker_init()` creates a kthread worker and calls `sched_set_fifo(worker->task)`: FIFO scheduling is an explicit part of the time-sensitive dispatch design.

The current NetBSD port calls `kthread_create(PRI_NONE, KTHREAD_MPSAFE | KTHREAD_MUSTJOIN, ...)`. In the **pinned** NetBSD `kern_kthread.c`, the no-`KTHREAD_TS` path sets `lc = SCHED_RR`, and `PRI_NONE` selects `PRI_KTHREAD`. This is a valid NetBSD kernel-thread creation path, but **not a demonstrated semantic equivalent of Linux's explicit FIFO policy**. Timing/preemption characteristics and priority inversion must be measured against the HP display deadline. Do not guess a numeric priority or mutate `lwp->l_class` unsafely.

Classification: verified scheduler-policy difference; real-world functional impact **UNKNOWN**, not proven black-screen cause.

## Finding VBLANK-FLUSH-02 — absence of snapshot flush barrier

Frozen Linux `drm_vblank_work_flush()` waits for pending-list handoff, then invokes `kthread_flush_work(&work->base)`. `drm_vblank_work_flush_all()` waits for `pending_work` to drain, then calls `kthread_flush_worker(vblank->worker)`.

The current NetBSD `drm_vblank_work_flush()` waits for `list_empty(&work->node) && !work->running`; `drm_vblank_work_flush_all()` waits for pending and ready lists to be empty **and** `!worker_running`. Those conditions inspect live queues and have no snapshot/barrier token identifying work that existed when flush began.

Consequence: when callbacks self-rearm or new work is enqueued continually, a live-emptiness wait can extend beyond the generation that Linux flush APIs synchronize. This is a **source-level semantic mismatch / potential starvation risk**, not an observed HP hang. Flush from within the same worker would also need an explicit deadlock contract.

## Acceptance to close these rows

1. Define NetBSD scheduler-class/priority mapping from **pinned APIs**, including actual load/latency constraints and safe bounded priority. Compile native with `-Werror` and verify genuine class/priority at runtime; no unvalidated FIFO changes to HP production kernel.
2. Implement a worker-safe per-work/all-work barrier or generation-fence model (or prove a bounded equivalent) preserving: no lost wakeups, exactly-once completion of the *already queued generation*, correct cancel_sync for self-arming work, and teardown join ordering.
3. Extend real-source C harnesses to exercise concurrent reschedule/flush/cancel, IRQ-induced queue transfer, and teardown races, with `-Werror` and failure injection. Mocked tests alone do not establish real NetBSD kthread scheduling.
4. On independently permitted **physical HP** execution, compile latest provider and patched pinned `drm_vblank.c` with genuine `drm_internal.h` and `sys/external/bsd/drm2/include/drm_trace.h`; link `ld -r`; validate native synchronization and IRQ stress before expanding to full 323-unit DRM/TTM/i915 build.
5. No kernel install, bootloader mutation, physical KMS test or full-release label without authorized combined build gate and an early-console/recovery transport. Retain last documented F77/genfb fallback.

## Verification classification

- Exact primary source text: **READ/COMPARED**.
- This note: **SOURCE_REVIEW_ONLY**.
- New automated/native tests in this step: **NOT_RUN**.
- HP build, link, reboot, display, FIFO timing and flush concurrency: **NOT_VERIFIED**.
- Cross-project scope: only HP-I915. PHOBOS Windows networking remains HOME-NETWORK-WLAN.
