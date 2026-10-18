# HP Cherryview/NetBSD: execution gates 1–4, 2026-10-18

Status: PARTIAL — source-only VBlank flush implementation; native integration and
physical i915/RTWN kernel acceptance remain OPEN. This is NOT a release approval.

## Frozen source/hardware baseline

- HP TPN-W121 / NetBSD 11 amd64, Intel CHV 8086:22b1 (rev 0x35).
- Linux DRM/i915 reference: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.
- NetBSD source: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- i915 owner branch: `work/hp-native-drm-stage-replay-20261015`, at this
  checkpoint post-fence-test `767d44d0a7cbce949bcf71aa91aee0f7d60bf9d9`.
- RTL consumer branch: `wip/hp-rtl-runtime-48-merge-20261010`, observed
  `cdf5562b14deece2580ebbac142c4bd152e05f24`.
- Never infer hardware boot, current build process or SSH authorization from
  GitHub source availability. F77/genfb is the *last documented* safe boot, not
  freshly verified physical state.

## 1. VBlank scheduling/flush — PARTIAL

The exact reviewed source is
`compat/native-runtime/drm-vblank/src/drm_vblank_work.c`.
The new `nb_vblank_flush_ready_locked` queues a stack-local no-op fence at
the end of the CRTC ready FIFO while holding `dev->event_lock`; it wakes
the worker and waits for *both* list unlink and callback completion
(`!fence.running`). Since the worker clears `running` under the same lock
and wakes the waiting queue, the stack allocation stays live until the
worker stops referencing it. Per-work flush first waits for its held
VBlank IRQ-reference/pending stage to hand off; flush-all first waits for
all pending-VBlank work to clear. The fence prevents waiting for newly queued
*ready* work behind it.

The source-only test
`tests/test_i915_netbsd_vblank_flush_fence_source.py` checks ten exact
structure/order predicates and a two-scenario FIFO model with four negative
mutations. A separate JavaScript oracle read the actual published C source
and verified 10/10 predicates, 4/4 negative mutation refusals, and the
ready-queue self-rearm FIFO model; the **Python test was NOT RUN**, nor was
a native NetBSD compiler invoked.

Remaining functional issues (DO NOT promote this code to a hardware kernel):
- Frozen Linux's worker calls `sched_set_fifo`; NetBSD pinned
  `kthread_create(PRI_NONE, KTHREAD_MPSAFE|KTHREAD_MUSTJOIN)` selects
  SCHED_RR and PRI_KTHREAD. FIFO and RR scheduling are NOT proven
  real-time deadline equivalents; no invented priority mutation.
- Per-work pending-stage wait is not generation-tagged: concurrent
  self-rearm/reschedule while waiting may prolong it. A real C-thread
  randomized concurrency test, generation-aware barrier and explicit
  cancellation, teardown, late wakeup and worker-stop race tests remain open.
- No `-Werror` NetBSD target recompile after the prior lifetime fix,
  no native threaded IRQ test, no native `ld -r`.

See `docs/NETBSD_VBLANK_WORK_SCHEDULING_PARITY_20261018.md`.

## 2. Native HP VBlank compile and link — BLOCKED / NOT RUN

The previous HP native worker object was compiled **before** lifetime and
fence edits, so it does not validate this work.

Required legitimate HP-only execution order:
1. Reverify execution authorization, uname/kernel/boot ID, HP architecture,
   running jobs and clean pinned source/worktree without altering boot.
2. Independently verify a stable recovery route and staging paths. The prior
   HP source/command request was rejected by a provider safety gate; do NOT
   evade it with a different account, host, wrapper, SSH/pivot or tool.
3. On an independently authorized HP NetBSD executor, stage exact pinned
   DRM sources and include dirs, including real `dist/drm/drm_internal.h`
   and `sys/external/bsd/drm2/include/drm_trace.h`; do NOT generate stubs.
4. Apply the exact current core hooks patch to an isolated pinned tree and
   build the **latest** native provider plus `drm_vblank.c` with real
   NetBSD kernel `-Werror` compiler arguments; capture exit, object SHA-256,
   actual ABI and unresolved symbols; link `ld -r`.
5. Only native success may close this *two-object* sub-gate; it is not
   a complete kernel link.

The platform permission and native build prerequisites were not
established in this source-only work; no HP commands were dispatched.

## 3. Complete 323 i915 units + RTWN combined integration — BLOCKED

Authoritative `docs/I915-STRUCTURAL-COVERAGE.tsv` has 323 source rows:
136 EXACT_ACTIVE_DIST; 13 ACTIVE_OVERRIDE_OR_MOVED; 7 PRESENT_NOT_BUILT;
167 UNRESOLVED_NO_BASENAME. Semantic state is **300 UNREVIEWED** plus
23 `REFERENCE_INAPPLICABLE_CHV_UC_PXP`. File-name matching is not
porting or build parity. Earlier source audits also found 65 direct
shared DRM/Linux headers without same-path matches and 140 C files that
use one or more such headers (lexical audit, not proof of missing APIs).

The RTL input currently selects 50 NetBSD-native C units in
`config/files.rtwn8723be_native`, with separate WLAN/runtime acceptance
not verified. A combined 304-unique-object candidate *name* matrix exists
(254 potential i915/DRM/TTM names + 50 RTL), but that is neither the 323
Linux-source semantic closure nor a linked NetBSD kernel.

The `governance/HP_I915DRMKMS_KERNEL_RELEASE.json` release artifact is
**ABSENT** from the observed i915 work branch. The RTL owner gate
`tools/check_i915_kernel_release.py` requires legitimate HP-I915 approval
and six real PASS criteria. Do not invent or inject it. The user's current
authorization to continue preparatory work is not proof those PASS checks
occurred. The downstream RTL owner runs the eventual shared kernel build
only when full i915 coverage, source/ABI/recovery and authentic permission
are established. Do not use older RTL-only scripts: they intentionally
select `no i915drmkms*` and therefore do NOT build the combined kernel.

Remaining: provider mapping for 300 rows; selected NetBSD native
DRM/TTM/GEM/GTT/ACPI/irq/PM and RTL net80211/DMA/fw/PHY dependency closure;
unique symbol ownership; complete generated kernel-config object list;
ABI, failure unwinds and no-dummy-callback proof. Native combined full
kernel `dependall`/ELF link is NOT RUN.

## 4. Physical i915 KMS test — HARD BLOCK / NOT RUN

The isolated F83 and F84 KMS kernels turned the HP's internal panel black
with backlight on. F84's async-fbdev scheduling hypothesis was falsified.
Early PCI/GT/VBT/AUX/DPIO/eDP/fbdev/wsdisplay G01–G09 trace is still absent.
`docs/HP_I915_TRACE_TRANSPORT_20261011.md` establishes no attached
independent serial console and no safe bootloader-to-kernel trace transport
at the last audit; postboot syslog/Tailscale/RDC cannot substitute for the
built-in driver attach interval.

**No testboot, install, boot menu/default, register/firmware or /netbsd
mutation.** Before revisiting: independent early physical serial console,
a captured known-good F77 boot marker, rollback verified from that console,
an isolated candidate with *only* G01–G09 trace and one selectable
non-default boot entry, plus legitimate HP target permission and a prior
native/full integration/release gate. The physical test must use observed
phase traces, not random register twiddling.

## Next safe dependent action

Keep the current source-only VBlank fence as WIP. Add a generation-aware
pending wait and true concurrent kernel-thread/failure-path tests, validate
the genuine NetBSD ABI on an independently authorized HP source executor,
then return to the full 323-unit semantic/DRM/TTM closure. Preserve
the current external execution denial and source/build/release distinctions.

No background job is running by virtue of this document; a future HP
executor must be observed directly before it can be claimed.
