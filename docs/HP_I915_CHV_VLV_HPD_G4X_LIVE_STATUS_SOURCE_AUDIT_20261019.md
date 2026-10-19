# NetBSD i915 VLV/CHV external HPD register routing — candidate 0044

**Date:** 2026-10-19. **Status:** source-confirmed platform-dispatch inconsistency; isolated patch candidate; pure in-isolate source verification PASS; no native NetBSD/HP hardware test; no whole-unit semantic acceptance.

## Exact frozen sources and call-chain owners

- NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6` — `sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c` Git blob `1dd8858b2d331906190258c8602af55966ff986c`: `__intel_digital_port_connected()` routes GMCH via GM45/G4X, modern PCH via PCH-specific checks, and then *all* `IS_GEN(dev_priv, 8)` to `bdw_digital_port_connected()` and `IS_GEN(dev_priv, 7)` to `ivb_digital_port_connected()`. No explicit CHV/VLV branch precedes these decisions. Broadwell's helper reads `GEN8_DE_PORT_ISR` for HPD A and otherwise calls `cpt_digital_port_connected()` — a chipset-specific decision not independently proven valid for Cherryview external B/C/D.
- The *same pinned* NetBSD `intel_dp.c` has an existing `g4x_digital_port_connected()` implementation for `HPD_PORT_B`, `HPD_PORT_C`, `HPD_PORT_D`, reading respectively `PORTB_HOTPLUG_LIVE_STATUS_G4X`, `PORTC_HOTPLUG_LIVE_STATUS_G4X`, `PORTD_HOTPLUG_LIVE_STATUS_G4X` via `PORT_HOTPLUG_STAT`.
- The *same pinned* NetBSD `sys/external/bsd/drm2/dist/drm/i915/i915_irq.c` Git blob `73f8deec8404481c4e457bb72631456b3b11ff69`: `i9xx_hpd_irq_ack()` and `i9xx_hpd_irq_handler()` explicitly include **both `IS_VALLEYVIEW` and `IS_CHERRYVIEW`** in the G4X `PORT_HOTPLUG_STAT` IRQ-acknowledgment/per-pin status selection. This establishes cross-owner source consistency for the G4X status layout, not a physical HP display measurement.
- Linux frozen `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab` — `drivers/gpu/drm/i915/display/intel_dp.c` Git blob `3152122e6aefe926e9ab128248dc2941da9958a6`: modern digital-port detection uses `dig_port->connected` callbacks and `intel_digital_port_lock()`. This does **not** imply that copying the NetBSD branch is Linux runtime equivalence; port-specific locking and callback owner remain separate semantic gates.

## Change

Standalone [candidate 0044](../candidates/0044-netbsd11-i915-vlv-chv-hpd-g4x-live-status.patch) changes only the original NetBSD `__intel_digital_port_connected()` platform dispatch, **before** the PCH and Gen8/Gen7 generic branches:

```c
/* VLV/CHV external HPD B/C/D uses PORT_HOTPLUG_STAT (G4X). */
if ((IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) &&
    (encoder->hpd_pin == HPD_PORT_B ||
     encoder->hpd_pin == HPD_PORT_C ||
     encoder->hpd_pin == HPD_PORT_D))
    return g4x_digital_port_connected(encoder);
```

**Critical scope guard:** an initial candidate would have routed *all* VLV/CHV pins to the G4X helper, which has no `HPD_PORT_A` case. That is potentially regressive, so candidate 0044 was revised **before report acceptance** to cover only pins **B/C/D**, preserving existing HPD A and other-platform routing. eDP uses a distinct detection path in the native `intel_dp_detect()`; no user-facing claim about HP eDP or an attached external monitor is made.

## Tests and evidence

- The final candidate was committed and GitHub content readback exactly verified at `4d120f51a821e445c7e557c3cc39468e6b2792e5` (replacing first unscoped candidate `6acbfd001ba2c1867fbd2d0b8bd8a0c19362bf0f`).
- `tests/test_chv_vlv_hpd_g4x_live_status_route.py` adds pinned-DP/IRQ read checks, a scratch-tree `git apply`/reverse procedure and **seven** negative mutation controls, including accidental HPD A selection. Corrected fixture revision: `05943be9a622b5448a34e1e54337845bd4f3329c`, with exact GitHub content readback. **The fixture was authored but not executed**; no claims of Python syntax/negative mutant results.
- A separate, pure JS-isolate structural source checker compared the actual frozen NetBSD owner against final patch 0044: **1/1 exact-context hunk** matched original line counts and text; reverse reconstruction matched the frozen source byte-for-byte; **8** source/IRQ constraints and **25** platform × pin route model cases passed. This is not native C compilation nor actual execution of HPD hardware/IRQ interrupts.
- Candidate 0044 and prior `0043` modify widely separated regions of the same frozen `intel_dp.c`; their combined application to the **six-file modified NetBSD working tree** and native compilation are not verified. Do not assume WIP patch composability merely from disjoint-looking source hunks.

## Remaining engineering requirements

1. Confirm the HP's actual external connector HPD pins and register live status read against its NetBSD 11 kernel and ACPI/VBT data using an independently recoverable, authorized and source-complete test kernel. A source register-family match is **not** physical link-up proof.
2. Port the Linux per-digital-port lock/callback ownership when justified by actual concurrent HPD, Type-C and AUX paths; maintain device-power wakeref and interrupt/lifecycle ordering. Avoid adding a blanket non-eDP `-ENXIO` check to `intel_dp_aux_xfer()` until the live-status route is sufficiently proven for the target, since a false negative would disable a viable AUX sink.
3. Check hotplug IRQ acknowledgment and live-status register races, HPD storm handling, VDD/PPS, power-well retention, suspend/resume and error unwind. Preserve existing `0013` IRQ-disabled AUX polling, `0014` AUX precharge and `0043` length checks.
4. Run actual pinned Python fixture/negative mutants on an authorized source execution provider only; native NetBSD 11 compile and HP hardware remain separate later gates under governance.

**Closure:** zero of the 300 whole Linux i915 units accepted, no HP build, boot menu edits, display testing, or user-installed kernel attempted.
