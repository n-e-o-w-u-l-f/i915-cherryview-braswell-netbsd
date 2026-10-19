# CHV/VLV eDP short-HPD 0045: non-resuming AUX/PPS guard — candidate review

Date: 2026-10-19
Project: HP-I915 — NetBSD 11/amd64 on HP TPN-W121
Status: SOURCE CANDIDATE ONLY / NOT INTEGRATED / NATIVE AND HARDWARE NOT_RUN
Owner source before patch: i915 `a7c4c330031c4856fe6ab7a57151292f3441fb8a`
Pinned NetBSD source `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
- `display/intel_dp.c` blob `1dd8858b2d331906190258c8602af55966ff986c`
- `display/intel_display_power.c` blob `b11bfb6dfc8d67877770c0820c23d6541188cd10`
- `intel_runtime_pm.c` blob `89c002e87103516506cfc770403ba141072b443c`
- `display/intel_hotplug.c` blob `722edbed2be6b1c4b2d06269572a977e6ca7adef`
Pinned Linux: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Why the patch is restricted to eDP short HPD

NetBSD `intel_dp_hpd_pulse()` already ignores **long** eDP HPD (`intel_dp.c:6609–6624`). For short eDP HPD, it can call `intel_dp_short_pulse()` and issue AUX reads. The pinned Linux successor also ignores short eDP HPD while RPM is suspended or panel power/VDD is absent (`intel_dp.c:6814–6836`). On VLV/CHV a successfully initialized eDP connector is **B/C only** (`NetBSD intel_dp.c:7535–7539`), and regular eDP detection bypasses the general external HPD live-status check. Candidate 0044 remains external B/C/D only; 0045 does not change those paths.

## Proven source locking and power reference ordering

- `intel_display_power_get()` uses `intel_runtime_pm_get()`, **which may resume**; therefore an unconditional `pps_lock()` is not a valid short-HPD test for an already-off eDP panel (`intel_display_power.c:1904–1943`, `intel_dp.c:724–751`).
- `intel_display_power_get_if_enabled()` first calls `intel_runtime_pm_get_if_in_use()`, returns **zero** when unavailable, holds `power_domains->lock` to take a reference only when that domain is enabled, and symmetrically drops the RPM ref otherwise (`intel_display_power.c:1945–1981`). The runtime PM helper uses `pm_runtime_get_if_in_use()` when CONFIG_PM applies (`intel_runtime_pm.c:424–445`). This is a bounded non-resuming **acquisition path**, not a guarantee against all OS-specific suspend races.
- `pps_lock()` acquires AUX-domain power first, then `pps_mutex`; `pps_unlock()` releases mutex before the power ref (`intel_dp.c:724–751`). The proposed helper mirrors that order using `get_if_enabled` and never calls `edp_panel_vdd_on`.
- `edp_have_panel_power()` and `edp_have_panel_vdd()` assert that `pps_mutex` is held, and both return false for CHV/VLV `pps_pipe == INVALID_PIPE` (`intel_dp.c:1140–1164`). Reading them outside their lock is **not allowed**.
- The existing AUX transaction `intel_dp_aux_xfer()` acquires AUX-domain and PPS refs, then conditionally turns on eDP VDD and later schedules its off path; `edp_panel_vdd_work()` separately holds `pps_mutex` and may shut down VDD (`intel_dp.c:1345–1383, 1518–1528, 2704–2850`). The new helper obtains and releases its references within the status check, without holding the PPS mutex across downstream DPCD/AUX.
- `i915_digport_work_func()` releases `irq_lock` before the HPD pulse callback (`intel_hotplug.c:313–350`), so this source site is a workqueue rather than an IRQ-spinlocked section. Confirm full suspend/unload lock order on the target before release.

## Candidate file and source-level checks

[`candidates/0045-netbsd11-i915-edp-short-hpd-no-resume-pps-guard.patch`](../candidates/0045-netbsd11-i915-edp-short-hpd-no-resume-pps-guard.patch):
1. Adds `intel_dp_edp_hpd_panel_powered()` using `get_if_enabled(AUX domain)`, `pps_mutex`, `edp_have_panel_power() || edp_have_panel_vdd()`, unlocking then `intel_display_power_put()`.
2. Leaves long eDP suppression intact; suppresses **short** eDP HPD when the check returns false. Leaves external DP and HPD A/B/C/D routing untouched.
3. Uses separate long/short diagnostic text. An initial generated hunk retained a misleading `long` log on the new short path; corrected before acceptance at `b4b7fd382adf63ea21b21689a2c2367a9c829d8c`, final candidate blob `cd5691f0942b0d51a523ccef83f84fed16284f50`.
4. Source-only 30-original-line / 58-new-line hunk at original 6602 matched the frozen NetBSD C *exactly*; text insertion and inverse reproduced original bytes. A first whole-translation-unit ordering search was incorrectly scoped and gave a false FAIL; restricted helper-only source order check PASS. **Neither check executes `git apply` or compiles C.**

## Open acceptance and possible effects

This is **not accepted driver behavior**. Between releasing the PPS status lock and starting `intel_dp_short_pulse()`, delayed VDD-off, HP suspend/resume and other workers can race: the check is a power-state **snapshot**, not an atomic reservation for the whole AUX transaction. It may suppress genuine DPCD short-pulse processing while the panel is temporarily off; verify correct eDP link/event policy on actual hardware. Under CONFIG_PM-disabled/NetBSD compatibility behavior, inspect runtime-PM semantics before interpreting `get_if_enabled()` as a universal suspend guard.

Required future negative/positive tests on an **independently authorized** runner:
- eDP long (skip unchanged), eDP short with inactive RPM and disabled AUX domain (skip without waking), eDP short with PPS/VDD off (skip), eDP short with panel on or force-VDD (proceed), external DP short/long (unchanged).
- CHV `pps_pipe == INVALID_PIPE` (no unsafe PP register read), delayed VDD-off interleaving, suspend/workqueue interaction, A/other pin preservation.
- Mutation cases: replace `get_if_enabled` with unconditional `get`, drop `pps_mutex`, invert acquire/release, omit CHV PPS-power checks, widen guard to external DP, remove eDP long skip.
- Verify exact `git apply --check`/apply/reverse to pinned source, diff and compiler warnings, combine with patches 0013/0014/0043/0044, and enforce proper integration/recovery gates.
- Native NetBSD i915+DRM+TTM kernel build, boot, real panel KMS, combined RTL8723BE and physical HPD remain **NOT_RUN**. Previously provider-denied equivalent test routes must not be retried by substituting tools/accounts.

## Release gate

0045 remains a separately staged **review candidate**. No operative source-tree modification or target installation. Governance PRE/POST: `n-e-o-w-u-l-f/Agent-Governance/state/events/hp-i915-chv-pps-aux-lock-order-20261019.jsonl`. Live owner: `Agent-Governance/handoffs/HP-I915-CURRENT.md`. NEXT: review `CONFIG_PM` compatibility and the delayed work race; run original accepted tests only with legitimate execution permission; source-review further 300 open Linux→NetBSD semantic units.
