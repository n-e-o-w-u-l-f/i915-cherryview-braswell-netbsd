# HP-I915 / 0045: eDP short-HPD vs. delayed VDD-off — pinned interleaving audit

**Status:** SOURCE-ONLY INTERLEAVING ANALYSIS; 0045 IS A NON-INTEGRATED PATCH CANDIDATE  
**Date:** 2026-10-19  
**Platform:** Valleyview/Cherryview i915, NetBSD 11/amd64 HP TPN-W121  
**Previous source HEAD:** `f240e94a06e045b64a827a5d93a5f23d13a3bf96`  
**Pinned NetBSD:** `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`  
**Pinned Linux:** `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`

## Exact source ownership

| Component | Frozen source and lines | Contract established from source |
|---|---|---|
| Deferred hotplug | NetBSD `display/intel_hotplug.c:313–350`, blob `722edbed2be6b1c4b2d06269572a977e6ca7adef` | `i915_digport_work_func()` drops `irq_lock` before calling `dig_port->hpd_pulse()`; the callback is process/workqueue context |
| eDP short pulse | NetBSD `display/intel_dp.c:5274–5316, 6609–6661`, blob `1dd8858b2d331906190258c8602af55966ff986c` | Short pulse may issue `intel_dp_get_dpcd()` and process service IRQ/PSR; it does **not** continuously hold `pps_mutex` |
| AUX acquisition | NetBSD `display/intel_dp.c:1345–1383, 1517–1528` | `intel_dp_aux_xfer()` gets AUX power domain and PPS mutex; calls `edp_panel_vdd_on()` under lock before the transaction and eventually `edp_panel_vdd_off(...,false)`, releases mutex and puts domain |
| VDD-on | NetBSD `display/intel_dp.c:2704–2753` | Cancels delayed VDD-off, sets `want_panel_vdd=true` under `pps_mutex`; if VDD off, forces VDD, observes panel timing and waits as needed |
| VDD-off | NetBSD `display/intel_dp.c:2818–2867` | Delayed `edp_panel_vdd_work()` takes PPS mutex, tests `!want_panel_vdd` and only then calls `edp_panel_vdd_off_sync()`; asynchronous schedule uses 5× panel power-cycle delay |
| System suspend | NetBSD `i915_drv.c:1765–1847`, `display/intel_hotplug.c:690–705` | i915 disables runtime interrupts and drains HPD work before late system power-domain suspend |
| Upstream Linux | Linux `display/intel_dp.c:6814–6836`, `display/intel_pps.c:69–90,1342–1352`, PPS blob `d4c98b150fa2b7c9736cf5071e67ac55d73f17cb` | Linux also obtains PPS lock **for a panel-status snapshot**, releases it, then continues short-HPD handling; does **not** hold PPS lock across DPCD/AUX. Its PPS power-domain owner is `POWER_DOMAIN_DISPLAY_CORE` and cannot be copied mechanically to older NetBSD AUX ownership |

## Two principal orderings after 0045's status snapshot

Assume eDP was found powered/VDD-on under `pps_mutex`, that the guard
released that mutex, and an existing delayed VDD-off worker is eligible.

1. **VDD-off worker acquires PPS first**: it sees `!want_panel_vdd`, switches
   VDD off via `edp_panel_vdd_off_sync` and releases PPS. Subsequent AUX
   transfer obtains its own AUX-domain wakeref/PPS lock, calls
   `edp_panel_vdd_on`, restores required VDD and observes panel-cycle delay
   rules before DPCD I/O. Thus a VDD-off/VDD-on **transition can occur**.
   Source locking prevents simultaneous PPS register mutation by these
   participants, but *does not* prove that re-powering is electrically benign
   on the HP panel. Long eDP pulses are filtered; short eDP events while VDD is
   off are filtered by candidate 0045 when observed in that state.
2. **AUX transfer acquires PPS first**: it requests VDD and sets
   `want_panel_vdd=true` while holding PPS. A concurrent VDD-off worker
   waits for PPS and rechecks `want_panel_vdd` under that lock, so it cannot
   switch VDD off **while the transfer holds PPS and wants VDD**.
   On transfer completion, the AUX code can clear `want_panel_vdd` and queue
   a later VDD-off; this is ordinary deferred release, not proof of an unsafe
   concurrent register write.

The above orderings arise from pinned code sequencing. They are an **abstract
lock-order argument**, not an executed interleaving exploration, a C memory
model proof or a tested NetBSD scheduler guarantee.

## System suspend and separately remaining race boundaries

Candidate [0045](../candidates/0045-netbsd11-i915-edp-short-hpd-no-resume-pps-guard.patch)
checks `runtime_pm.irqs_enabled` and
`power_domains.display_core_suspended` before acquiring conditional AUX power
and again under PPS mutex. This is necessary because the pinned NetBSD
`include/linux/pm_runtime.h` `pm_runtime_get_if_in_use()` **always returns 1**;
it cannot serve as a Linux-style physical active-RPM test. The conditional
display-domain read still checks enabled power wells; these checks have
different semantics from a true Linux runtime-PM lease.

There is **no persistent VDD reservation** between the status snapshot and
the next AUX transfer. Therefore an extra VDD power cycle remains possible,
and short pulses could be conservatively skipped while the panel is off.
Taking PPS mutex across all `intel_dp_short_pulse()` is **not a safe repair**:
downstream AUX takes the same PPS mutex. A new long-lived VDD lease would
require a separately verified owner API and teardown path, not an improvised
mutex hold. Actual HP ACPI/VBT port/wiring, CHV invalid PPS-pipe paths, system
resume ordering, IRQ race, and eDP electrical timing remain OPEN.

## What changed in this step

- Candidate 0045 has an explicit source comment documenting snapshot
  semantics, possible delayed-VDD interleaving and recursive-lock risk.
- Pinned NetBSD old-line hunk 6602 contains 30 original lines and now
  74 candidate lines. Exact line-context check and text inverse/source
  restoration were **STATIC SOURCE PASS**; **git apply --check, compile,
  hardware and expanded 16-mutation executable regression are NOT_RUN**.
- No change to Linux reference, NetBSD kernel tree, HP target or bootloader.
  [Previous 0045 RPM review](HP_I915_CHV_0045_NETBSD_PM_SHIM_RACE_REVIEW_20261019.md)
  remains valid; this source audit narrows the VDD-off race mechanism without
  claiming the physical HP release gate is closed.

## Minimum next tests and 0045 acceptance

Use the already authored
[`test_chv_edp_short_hpd_0045_source.py`](../tests/test_chv_edp_short_hpd_0045_source.py)
on a genuinely authorized isolated executor (not via an equivalent reroute of
the prior provider-denied operation), require all three source PASS markers,
exit 0 and byte-exact rollback. On a separately authorized native NetBSD
kernel test, instrument **both** VDD-worker-first and AUX-first schedules with
pps_lock/pps_unlock tracing, `want_panel_vdd`, PPS pipe, actual DP AUX
outcome/latency, IRQ and suspend state; include eDP long and short, external
DP unaffected, invalid CHV PPS pipe and multiple deferred work cycles.
Before any physical boot test verify independent early logging/standard
kernel rollback and combined i915+RTL release gates.

The broader 323-unit i915 + DRM/TTM + RTL8723BE project and 300 Linux→NetBSD
semantic acceptance rows remain OPEN; a source-only 0045 result is not a
native-KMS, boot, WPA2 or hardware acceptance.
