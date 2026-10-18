# NetBSD 11 i915: five Linux-split Cherryview display source owners — 2026-10-18

Status: **STRUCTURAL OWNER IDENTIFIED ONLY**. Not semantic, kernel-build, runtime or KMS acceptance. The 323-unit requirement is unchanged.

## Frozen references

- Linux i915: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`, `drivers/gpu/drm/i915/`.
- NetBSD 11: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, `sys/external/bsd/drm2/dist/drm/i915/`.
- NetBSD selected objects: frozen `sys/external/bsd/drm2/i915drm/files.i915drmkms`, each mapped native C file is selected by **i915drmkms**.
- Owner matrix: `docs/I915-STRUCTURAL-COVERAGE.tsv`, Git revision `ddc8af1171c6df9716989217669935a5230d1f98`, SHA256 `c254dc54d7d0ef66b737e6b15f717481cf675f5423143534fbc44706262769dc`.

## Actual function ownership verified against frozen C

| Active Linux 2026 source | Selected NetBSD 11 C owner | Source-matched anchors; exact interface parity **not** claimed |
|---|---|---|
| `display/intel_dp_aux.c` | `display/intel_dp.c` | `intel_dp_aux_init` (NetBSD line 1738), `intel_dp_aux_xfer` (1345) |
| `display/intel_pps.c` | `display/intel_dp.c` | `vlv_detach_power_sequencer` (3648), `wait_panel_on` (2634) |
| `display/intel_backlight.c` | `display/intel_panel.c` | `vlv_setup_backlight` (1753), `vlv_enable_backlight` (1063) |
| `display/intel_display_power_well.c` | `display/intel_display_power.c` | `chv_pipe_power_well_enable` (1768), `chv_dpio_cmn_power_well_enable` (1490) |
| `display/intel_vblank.c` | `i915_irq.c` | `i915_get_vblank_counter` (585). Other scanline functions appear in selected `display/intel_display.c`. |

Five rows changed **only** their `structural_class` from `UNRESOLVED_NO_BASENAME` to `ACTIVE_OVERRIDE_OR_MOVED` and populated the corresponding native source name. Every `semantic_state` remains **UNREVIEWED**.

## Differences requiring actual porting/verification

1. **AUX / PPS:** current Linux's split AUX and panel power sequencer has APIs and IRQ interactions absent or differently organized in imported NetBSD 5.6-era C. Validate CHV precharge, transfer timeout/retry, AUX IRQ behavior, DPCD result, VDD/panel delay and power-sequencer detach semantics. Finding `intel_dp_aux_init` in NetBSD does **not** prove these match.
2. **Backlight:** Linux's `vlv_disable_backlight` takes an extra brightness value compared with imported native definition; audit register write sequence, PWM ownership and on/off restore, including actual eDP panel handover.
3. **CHV power wells:** Linux `chv_pipe_power_well_enable` takes `struct intel_display *`, whereas imported NetBSD takes `struct drm_i915_private *`; audit lifetime, power dependencies and PUNIT/DPIO sideband sync, not just same-name functions.
4. **VBlank:** import splits scanline/vblank owners across `i915_irq.c` and `intel_display.c`; the separate project's NetBSD VBlank workqueue generation/pending-stage and SCHED_FIFO-versus-RR semantics are still unverified.
5. **Display/KMS:** for any promoted semantic row, provide a source-to-source call graph, required native object/selector, register order, error propagation, unwind/teardown and source-specific native test. Do not mark complete from symbol/path overlap.

## Executed source-only acceptance (SentinelX Legion)

Frozen Linux and NetBSD native C files were fetched from immutable commits. A one-off Python source fixture checked five precise matrix rows, the native `files.i915drmkms` selector for every owner, nine function anchors in **both** versions, and all 323 classification totals. **PASS**: 136 EXACT_ACTIVE_DIST, 18 ACTIVE_OVERRIDE_OR_MOVED, 7 PRESENT_NOT_BUILT, 162 UNRESOLVED_NO_BASENAME; 300 semantic UNREVIEWED plus 23 CHV UC/PXP reference-inapplicable. HP native compile, kernel link, hardware boot and KMS **NOT RUN**.

## Required execution order

Finish source/ABI/lifecycle closure for the full frozen 323-unit inventory (with individually evidenced target-inapplicable code), only then native compile/link on the authorized HP; preserve real standard-kernel recovery, stage a separate candidate, and let the user test the installed kernel **before** claiming physical KMS acceptance. Ensure panic dump, early-console and message-buffer survival are independently verified; 32 G01–G09/G08 progress prints do not prove complete logging.
