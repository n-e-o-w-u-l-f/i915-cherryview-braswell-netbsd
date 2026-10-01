# Cherryview driver mapping

## PCI identity

| Item | Value |
|---|---|
| Vendor | Intel `0x8086` |
| Device | `0x22b1` |
| Class | VGA / display |
| Revision | `0x35` |
| Subsystem vendor | HP `0x103c` |
| Subsystem | `0x8205` |
| Architecture | Cherryview / Braswell |
| Generation | Gen8 LP |

## NetBSD mapping

The NetBSD 11 i915 PCI table already contains `INTEL_CHV_IDS(&chv_info)`.
The associated `chv_info` identifies the platform as Gen8 and enables the Cherryview-specific engine and display characteristics.

The imported driver also contains CHV-specific DPIO mapping. Cherryview uses two PHY groups: one path for the x2 PHY serving DP/HDMI B/C and another for the x1 PHY serving DP/HDMI D.

This means PCI identification is not the missing component. The investigation is further down the initialization path.

## Current safe state

F77 (`netbsd.v1-f77-linux-efuse-map-20260926`) is the verified safe/default recovery kernel with i915drmkms disabled and UEFI GOP/genfb retained.

F79/F80 are failed historical diagnostic artifacts and are no longer primary boot-menu entries. F81 proved that the imported i915 `early_probe` path can complete; its later `cnopen: no console device` panic was a diagnostic-cutoff console-ownership side effect after i915drmkms had displaced genfb, not evidence that `early_probe` itself hung.

Runtime isolation is secondary verification only. The primary repair method is reference reconstruction and porting from the working Linux Cherryview implementation.

## Reference baseline

NetBSD's imported DRM/i915 source is based on **Linux v5.6-rc3**, Linux commit:

`f8788d86ab28f61f7b46eb6be375f8a726783636`

The NetBSD import is commit:

`4a352a70313258edd1e53a9576dc62c168b9bb9e`

The pinned working Linux reference for this project is:

`fd179f8a05be3ccae366b9b96e176b51fbe54aab`

Therefore the porting problem is treated as:

`Linux v5.6-rc3 hardware semantics -> post-import CHV fixes -> NetBSD framework translation`

rather than as register experimentation or repeated boot bisecting.

## Cherryview post-import hardware delta matrix

| Linux commit | Hardware-visible change | NetBSD 11 import | Local project state | Port action |
|---|---|---|---|---|
| `1a2466fe13c6` | Defer initial `DISPLAY_PHY_CONTROL` application to CHV pipe power-well synchronization | Initial value is written immediately by `chv_phy_control_init()` | A matching local `chv_pipe_power_well_sync_hw()` change was observed in the 2026-09-29 source audit; must be re-read before further mutation | Preserve/verify exact upstream semantics |
| `8ec7d10a5479` | Fix pre-SKL DP AUX precharge to 3 x 2us | v5.6 logic uses 5 except Gen6 | Local AUX/precharge modifications were observed; exact current source must be re-read | Preserve/verify exact upstream semantics |
| `a467a243554a` / `b2e9e6a9cb87` (historical references); pinned Linux `g4x_dp.c` and `g4x_hdmi.c` (direct semantic reference) | Fix VLV/CHV DP/HDMI audio-enable ordering; separate port pre-enable from late audio presence/codec enable | Audio is enabled too early in the generic DP/HDMI pre-enable path | Patch 0005 staged in canonical repo; applies cleanly to pinned NetBSD and retained six-edit overlay; host C actual-function timing test passes | NetBSD kernel/object compile and hardware display/audio verification still pending |
| `c931ef0041fe` | Program `VLV_PIPE_MSA_MISC(pipe)=0` on VLV/CHV pipe enable | Register/programming absent | Matching local register definition/write was observed | Preserve/verify exact upstream semantics |
| `1c8ee8b92fb6` | Restore Cherryview from aliasing PPGTT to **full PPGTT** and program Gen8 PDPs on request allocation | `chv_info.ppgtt_type = INTEL_PPGTT_ALIASING`; no `emit_pdps()` in execlists | **Confirmed missing** from the imported/current audited core path | **Backport required** |
| `eb9fcf638575` | Route CHV port information through the VBT port-data model | v5.6 already parses DDI-style CHV child devices, but uses older representation | Semantics need comparison, not literal struct backport | Classify VBT port-presence/eDP semantics |
| `cc018c262674` | Prevent HPD polling/runtime-PM power-reference loop | Older connector-detect power flush model | Not yet classified in NetBSD | Backport only if old semantics reproduce the loop/race |
| `a72e1c139194` | Dedicated VLV/CHV IOSF-sideband mutex | Shared sideband/pcode-era locking model | Not yet classified | Verify lock ownership; port only semantic concurrency delta |
| `c19f5a0341e0` | Hook VLV/CHV display page-table fault interrupts | Missing modern fault reporting/handling | Not required to discover initial hardware state, but part of parity | Port after core initialization parity |

### Confirmed Full-PPGTT prerequisite coverage in NetBSD 11

The v5.6-derived NetBSD tree already contains the primitives required by Linux commit `1c8ee8b92fb6`:

- `GEN8_3LVL_PDPES == 4`
- `i915_page_dir_dma_addr()`
- `i915_vm_is_4lvl()`
- `GEN8_RING_PDP_UDW/LDW`
- `MI_LRI_FORCE_POSTED`
- Gen8 execlists/ring infrastructure

The missing semantic delta is therefore bounded:

1. set Cherryview `ppgtt_type` to `INTEL_PPGTT_FULL`;
2. add the upstream `emit_pdps()` sequence to the v5.6-style execlists path;
3. invoke it for non-4-level VMs before the normal invalidate in `execlists_request_alloc()`;
4. retain NetBSD bus-DMA abstractions already used by `i915_page_dir_dma_addr()`.

## Reference-derived porting order

1. Re-read the live NetBSD source after recovery and classify each already-local display fix against its exact upstream commit.
2. Backport the confirmed missing Cherryview Full-PPGTT/PDP sequence.
3. Complete VBT/OpRegion/port-presence semantic comparison for the internal eDP path.
4. Complete CHV power-well/DPIO/PHY/PPS/AUX sequencing comparison.
5. Complete GT/GGTT/PPGTT, IRQ, RC6/RPS and console-handoff parity.
6. Review the complete source delta against Linux before building.
7. Build one integrated reference-derived candidate.
8. Use runtime boot only to verify the ported state machine; do not use reboot experiments to invent hardware behavior.

## Important distinction

Do not change the CHV PCI ID to BXT and do not enable BXT firmware on this hardware. CHV and BXT are separate i915 platforms despite both being low-power Intel graphics generations.