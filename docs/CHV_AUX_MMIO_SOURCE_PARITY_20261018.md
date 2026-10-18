# Cherryview/Braswell AUX MMIO source parity — 2026-10-18

Status: **exact frozen source-only address equivalence**, NOT full AUX semantic or 323-Linux-unit parity. No HP native build or hardware test.

## Source authority

- Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`: `drivers/gpu/drm/i915/display/{intel_dp_aux.c,intel_dp_aux_regs.h,intel_display_reg_defs.h}`.
- NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`: `sys/external/bsd/drm2/dist/drm/i915/{display/intel_dp.c,i915_reg.h,i915_pci.c}`.
- The CHV NetBSD `chv_info` has `.display_mmio_offset = VLV_DISPLAY_BASE`; both Linux and NetBSD define `VLV_DISPLAY_BASE = 0x180000`.
- Linux's `vlv_aux_ctl_reg`/`vlv_aux_data_reg` use explicit `VLV_DISPLAY_BASE + _PORT(...)`. NetBSD's `g4x_aux_ctl_reg`/`g4x_aux_data_reg` use `DP_AUX_CH_CTL/DATA` with `DISPLAY_MMIO_BASE(dev_priv)` **already inside** the register constants. Both yield the same physical MMIO addresses. Do not apply an extra offset.

## Verified frozen register addresses

| Channel | Control | Five AUX data registers |
|---|---|---|
| B | `0x1e4110` | `0x1e4114` to `0x1e4124` |
| C | `0x1e4210` | `0x1e4214` to `0x1e4224` |
| D | `0x1e4310` | `0x1e4314` to `0x1e4324` |

`tests/test_chv_aux_mmio_source_contract.py` checks the SHA256 of all six original C/header files, source dispatch and register selectors, and independently derives all **18** control/data addresses from each upstream's macros. Six deliberate mutation failures exercise CHV platform base, Linux CHV dispatcher, NetBSD control and data access, Linux display base, and Linux AUX offsets.

**Actual SentinelX Legion execution:** RC0 `CHV_AUX_REGISTER_BANK_FROZEN_SOURCE_18_REGS_6_MUTATIONS_PASS` on i915 `1565350a7df371a2e3195149e73bfb699e14b067`. Two earlier negative test failures were incorrect mutation target selection (an earlier VLV/device-info occurrence and an earlier Linux AUX helper occurrence); fixed before declaring PASS. Git diff and Python syntax checks passed.

## Still-open behavior (do not promote 323 semantic state)

The modern Linux `intel_dp_aux_xfer` takes a digital-port lock and rejects disconnected non-eDP AUX requests; NetBSD's older path locks a Type-C port when applicable and takes its PPS mutex. For Cherryview eDP, the PPS lock exists, but this is **not proof** of full concurrency/hotplug parity for external DP. AUX busy/timeout/retry, 400–500 us receive-error backoff, QoS/power wakerefs, IRQ completion and unregister/teardown also need independent source/runtime contracts. Linux `intel_dp_aux_irq_handler` must not be assumed implemented just because the underlying channel is polled.

The existing i915 patch `0004` adjusts AUX precharge to three 2-us units, and patch `0002` aligns CHV PHY control with power-well `.sync_hw`; these are already staged in the separate **nonrelease** RTL combined source diagnostic. The master 323 matrix remains **300 UNREVIEWED + 23 CHV-specific evidenced exceptions**. Full source/ABI/lifecycle/DRM/TTM verification comes first, then native HP build, recovery-safe kernel installation, user's test, and only afterward physical KMS proof.
