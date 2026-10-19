# Cherryview / Valleyview HPD A, eDP, AUX and PPS: pinned Linux → NetBSD semantic audit

Date: 2026-10-19. Status: **SOURCE-ONLY AUDIT — no C patch, no executable test, no HP hardware evidence.**
Scope: HP-I915 project only, NetBSD 11 amd64 HP TPN-W121; i915 work branch `work/hp-native-drm-stage-replay-20261015`.
Observed prior i915 HEAD: `2ddb3d6d87ab1f6778a8eeb3f97307609c3daff7`.
NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
Linux: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Exact frozen source identity

| Source | Git blob SHA | Anchors |
|---|---|---|
| NetBSD `sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c` | `1dd8858b2d331906190258c8602af55966ff986c` | lines 1140–1164, 1345–1383, 5375–5378, 5445–5465, 5511–5529, 5590–5629, 5675–5696, 6609–6661, 6665–6677, 7513–7557 |
| NetBSD `sys/external/bsd/drm2/dist/drm/i915/display/intel_hotplug.c` | `722edbed2be6b1c4b2d06269572a977e6ca7adef` | 94–105 default pin mapping; 313–350 workqueue pulse callback |
| NetBSD `sys/external/bsd/drm2/dist/drm/i915/i915_irq.c` | `73f8deec8404481c4e457bb72631456b3b11ff69` | 115–122, 1454–1507 G4X VLV/CHV interrupt family |
| Linux `drivers/gpu/drm/i915/display/intel_dp.c` | `3152122e6aefe926e9ab128248dc2941da9958a6` | 6011–6065 locking and display-core power; 6304–6337 eDP-first detect; 6814–6836 short/long eDP HPD guards |

All assertions below are limited to these pinned source revisions. Newer OS APIs, HP wiring and resulting C compiler behavior remain unverified.

## 1. eDP and HPD-A mapping: do not route A to G4X

- NetBSD `intel_hpd_pin_default()` maps PORT_A→HPD_PORT_A, B→B, C→C, D→D (`intel_hotplug.c:94–105`). The mapping alone does not prove an actual HP panel is wired to any one pin.
- NetBSD `intel_dp_is_port_edp()` returns true for Gen 5–8 PORT_A before consulting VBT (`intel_dp.c:6665–6677`), **but** `intel_dp_init_connector()` rejects eDP on VLV/CHV unless `port == PORT_B || port == PORT_C` (`intel_dp.c:7513–7539`). This means *successfully initialized* VLV/CHV eDP connectors are B/C only. Any attempted eDP A connector initialization on VLV/CHV is an unresolved platform/topology question, not proof of a physically missing display.
- NetBSD `intel_dp_detect()` branches eDP to `edp_detect()` ahead of `intel_digital_port_connected()`; `edp_detect()` returns connected (`intel_dp.c:5375–5378, 5675–5696`). Pinned Linux detection also has eDP-first routing (`intel_dp.c:6304–6337`). Consequently the candidate 0044 *external* HPD live-status read is **not** the regular eDP detection path.
- `g4x_digital_port_connected()` supports B/C/D only and reads `PORT_HOTPLUG_STAT` (`intel_dp.c:5445–5465`); `i9xx_hpd_irq_ack()` and its handler use the G4X interrupt family for VLV/CHV (`i915_irq.c:1454–1507`). Keep candidate 0044 external B/C/D-only. HPD A under Gen7/Gen8 fallback and other connector types still requires separate platform evidence.

## 2. eDP short-pulse / panel power semantic gap (candidate, not accepted patch)

- NetBSD `intel_dp_hpd_pulse()` ignores **long** eDP pulses. For **short** eDP pulses it may continue to MST/short-pulse work and eventually AUX (`intel_dp.c:6609–6661`).
- Pinned Linux `intel_dp_hpd_pulse()` suppresses eDP pulses when `long_hpd || intel_display_rpm_suspended(display) || !intel_pps_have_panel_power_or_vdd(intel_dp)` (`intel_dp.c:6814–6836`). This includes some short pulses that the NetBSD code does not initially screen out. Potential repeated VDD toggling/extra DPCD traffic is a **hypothesis** needing instrumentation, not a measured HP defect.
- NetBSD already has `edp_have_panel_power()` and `edp_have_panel_vdd()` with `lockdep_assert_held(&dev_priv->pps_mutex)` and CHV/VLV `pps_pipe == INVALID_PIPE` guard (`intel_dp.c:1140–1164`). The existing `pps_lock()` **first obtains the AUX power domain and then** takes `pps_mutex` (`intel_dp.c:724–755`); `intel_dp_aux_xfer()` obtains AUX domain + `pps_lock`, calls `edp_panel_vdd_on()`, then unwinds the same resources (`intel_dp.c:1345–1383, 1518–1528`).
- NetBSD `intel_hotplug.c:313–350` dispatches `hpd_pulse` from a digport **work function after dropping `irq_lock`**, rather than calling this callback while the shown spinlock is held. Nevertheless, this does **not** prove that taking `pps_mutex` or an AUX wakeref in a new early guard is deadlock-free under all suspend/workqueue transitions. Calling unlocked `edp_have_panel_power()` violates its documented lock precondition.
- Linux's optional `dig_port->lock/unlock` and callback-based `dig_port->connected` do not match NetBSD's inline Gen7/Gen8 dispatch (`NetBSD intel_dp.c:5590–5629`, Linux `intel_dp.c:6011–6065`). Do **not** transplant lock or callback APIs verbatim or imply that later Type-C locks apply directly to old CHV ports.

## 3. Required source/host proof before a C candidate or integration

1. Inventory `intel_dp_hpd_pulse` callers, deferred work ordering, `pps_mutex`, `rpm` and power-domain reference ownership. Identify a **non-invasive, correctly synchronized** way to observe panel power/VDD without first powering it on. Verify no recursion through `edp_panel_vdd_on` and no suspend lock inversion.
2. Check actual HP ACPI/VBT eDP port B/C, PPS pipe and HPD/AUX pin assignment using read-only host evidence when authorized. Preserve a safe independent early console and standard-kernel recovery.
3. Draft isolated short-pulse guard only after (1)-(2); require deterministic source/compile negative cases including (eDP long), (eDP short + PPS on), (eDP short + PPS/VDD off), (eDP short + RPM suspended), (external DP short and long), (CHV PPS pipe INVALID_PIPE), and suspended/drm-IRQ-disabled cases. Explicitly distinguish no-IRQ hang from duplicate panel power cycles.
4. Run real `git apply --check`/apply/reverse + seven-mutant 0044 source script only when genuinely authorized: prior provider-denied equivalent Legion execution **not retried** in this audit. Native NetBSD compile, combined 323-unit DRM/TTM+i915+RTL kernel, hardware HPD/KMS and WPA2 remain NOT_RUN.
5. Keep separate correctness gates for `0013` IRQ wait, `0014` precharge, `0043` AUX buffer and `0044` B/C/D source selection. Disjoint patch hunks are not a full-build or runtime proof.

## Outcome and continuity

- **CONFIRMED SOURCE**: Successful VLV/CHV eDP connector B/C-only guard; eDP detection bypasses general external HPD live status; B/C/D G4X IRQ family; eDP long-pulse suppression in NetBSD; additional short-pulse/panel and RPM conditions in Linux; NetBSD PPS access requires mutex/power discipline.
- **NOT VERIFIED**: HP actual panel HPD pin; early-guard power state synchronization; whether an HP short-pulse VDD loop occurs; native C compilation; executable seven-mutation test; physical KMS; complete semantic closure (300 OPEN).
- **NO C FILES CHANGED**: This report intentionally avoids an untested lock/power change that could increase crash/black-screen risk.

Governance audit owner: `Agent-Governance/state/events/hp-i915-chv-hpd-a-edp-power-20261019.jsonl`; live state: `Agent-Governance/handoffs/HP-I915-CURRENT.md`. Next safe step: source-review the PPS/wakeref lock ordering and CHV panel power-owner functions before selecting a minimal source patch.
