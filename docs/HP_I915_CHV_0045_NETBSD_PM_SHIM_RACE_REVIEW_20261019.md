# HP-I915 0045 follow-up: NetBSD PM shim, explicit suspend gate, deferred-VDD race

**Status:** SOURCE-ONLY CORRECTION / 0045 UNINTEGRATED / NATIVE & HARDWARE NOT_RUN
**Date:** 2026-10-19
**Previous audited i915 commit:** `ce4abae6d844e60506b3efbc1799009e607a5693`
**Pinned NetBSD:** `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`
**Pinned Linux:** `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`

## Confirmed portability defect in 0045 v1 assumptions

The NetBSD Linux-compatibility header
`sys/external/bsd/drm2/include/linux/pm_runtime.h` (Git blob
`01d2e138590ff25d549a135545e3b68c39d9205c`) implements
`pm_runtime_get_if_in_use(struct device *)` as a **stub unconditionally returning 1**.
Its `pm_runtime_get_sync()` also returns 0 without enacting Linux runtime-resume.
Therefore the Linux semantics that `get_if_in_use` proves the device is already
active **do not apply verbatim on NetBSD**, even if `CONFIG_PM` tests call it.
This is an actual source-contract discrepancy, not evidence of an observed HP
failure. Do not treat the Linux `CONFIG_PM` option alone as evidence of a working
NetBSD runtime suspend/resume implementation.

`intel_runtime_pm_get_if_in_use()` from pinned
`intel_runtime_pm.c` (blob `89c002e87103516506cfc770403ba141072b443c`,
lines 424–450) calls this shim under `IS_ENABLED(CONFIG_PM)`, then acquires a
tracked software wakeref.
`intel_display_power_get_if_enabled()` from
`display/intel_display_power.c` (blob
`b11bfb6dfc8d67877770c0820c23d6541188cd10`, lines 1945–1981)
**also** checks `__intel_display_power_is_enabled()`, which reads
`runtime_pm.suspended` and power-well `hw_enabled` (lines 200–237). The
domain check is meaningful, but it is not a substitute for an independently
verified system suspend state, especially with always-on domains.

## System suspend/hotplug ordering

- NetBSD `i915_drv.c` lines 1765–1845: `i915_drm_suspend()` disables i915
  interrupts using `intel_runtime_pm_disable_interrupts()`, then drains HPD
  work with `intel_hpd_cancel_work()`, prior to `i915_drm_suspend_late()`
  / `intel_power_domains_suspend()`.
- `intel_hotplug.c` lines 690–705: `intel_hpd_cancel_work()` clears pending
  masks under IRQ lock and performs `cancel_work_sync(dig_port_work)`, followed
  by cancellation of hotplug and poll work. This helps serialize the HPD worker
  against *system suspend*; it does not prove immunity against every concurrent
  operation, firmware failure or legacy NetBSD taskqueue issue.
- `i915_irq.c` lines 4190–4220: disable sets `runtime_pm.irqs_enabled=false`
  after resetting/synchronizing IRQ; resume enables it. `display_core_suspended`
  is set by `intel_power_domains_suspend()` and cleared on resume; field
  declaration is `display/intel_display_power.h:209`.
- Therefore the source-only 0045 v2 explicitly rejects snapshots when either
  `!runtime_pm.irqs_enabled` or `display_core_suspended`. It checks once
  *before* trying to acquire the existing AUX domain and again *under the PPS
  mutex* before reading the panel-control registers. This does not rely
  exclusively on the NetBSD stub's fabricated in-use answer.

## Deferred panel-VDD and time-of-check/time-of-use limitation

Pinned `intel_dp.c` lines 724–751 and 1140–1164 establish AUX-domain ->
`pps_mutex` ordering, with the panel state helpers requiring the lock.
`intel_dp_aux_xfer()` (1345–1383, 1518–1528) obtains the AUX wakeref and PPS
mutex and can call `edp_panel_vdd_on()`; `edp_panel_vdd_off()` may queue
`panel_vdd_work` (2704–2850), which also enters the PPS mutex before changing
`EDP_FORCE_VDD`.

After 0045's helper releases `pps_mutex`, the delayed VDD worker may legally
turn VDD off *before* the subsequent `intel_dp_short_pulse()` takes its own
AUX/PPS references. The helper observes a **snapshot**, not a lease keeping VDD
on for the complete short-pulse path. Holding `pps_mutex` across
`intel_dp_short_pulse()` would risk self-deadlock when downstream AUX itself
calls `pps_lock()`. Never adopt that as a quick fix. A safe final design must
demonstrate its behavior in these interleavings, including suppression of stale
eDP pulses and avoiding VDD-off→HPD→VDD-on loops. Do not invent a stronger
guarantee from source-only inspection.

## Candidate and regression ownership

- [0045 patch](../candidates/0045-netbsd11-i915-edp-short-hpd-no-resume-pps-guard.patch)
  now includes explicit IRQ/display-suspend checks and the retained
  `get_if_enabled`/PPS-mutex/release order. Pinned source text old 30 lines,
  new 68 lines, static exact-context replacement + inverse **SOURCE PASS**,
  not executed `git apply`.
- [0045 pinned-source test](../tests/test_chv_edp_short_hpd_0045_source.py)
  checks exact Git blob identities, scratch-only `git apply --check`/apply/
  reverse, the NetBSD always-1 PM shim, conditional domain acquisition,
  `intel_hpd_cancel_work`, both new suspend checks, mutex/ref ordering and
  **ten source mutation** negative cases. It is **AUTHORED, NOT_RUN**.
  Script parsing was corrected for `static inline int`; this edit is not
  evidence that the program actually runs successfully.

### Required release sequence

1. Observe current exact candidate/test blob SHA, independently inspect
   permission/scope and run the script on a genuinely authorized isolated
   executor (not a reroute of the previously provider-denied equivalent test).
2. Require all three exact source markers:
   `CHV_EDP_HPD0045_PINNED_SOURCE_GUARD_PASS`,
   `CHV_EDP_HPD0045_TEN_MUTATIONS_REFUSED` and
   `CHV_EDP_HPD0045_BYTE_EXACT_REVERSE_PASS`, actual exit 0.
3. Check compatibility with i915 candidate patches 0013/0014/0043/0044;
   run native NetBSD compiled i915/DRM/TTM+RTL common-kernel tests before any
   install. A Linux compatibility shim's unit behavior alone does not prove
   real NetBSD suspend state correctness.
4. Require read-only current HP VBT/ACPI eDP B/C mapping, independent early
   console/standard-kernel rollback, then gated hardware suspend/resume,
   HPD short/long, KMS and WPA2 acceptance. Nothing has been installed.

## Current conclusion

This checkpoint resolves an **incorrect portability assumption** and strengthens
an **unintegrated** candidate. The deferred-VDD TOCTOU remains **OPEN**, and
the user's full 323-source/300-semantic i915 port and physical NetBSD release
goals remain **NOT VERIFIED**. Governance material event is
`Agent-Governance/state/events/hp-i915-chv-edp-hpd0045-rpm-vdd-race-20261019.jsonl`.
