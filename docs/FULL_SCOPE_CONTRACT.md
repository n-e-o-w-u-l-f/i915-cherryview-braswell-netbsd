# FULL-SCOPE CONTRACT — Linux i915 -> NetBSD

Status: IN_PROGRESS

## OBJECTIVE
Port the complete pinned Linux i915 driver subtree and its required DRM/TTM/kernel dependency closure to NetBSD 11, preserving all upstream active build units, platform-specific hardware state machines, ordering, errors, recovery and NetBSD OS-adapter semantics. The HP 17-x037ng Intel 8086:22b1 Cherryview is the FIRST hardware acceptance target, not a reduction of the generic whole-driver port.

## REQUIRED_COVERAGE
All 323 active C translation units in the frozen Linux i915 build selection, corresponding reachable headers, build/Kconfig dependencies, required DRM core/display/TTM and LinuxKPI/NetBSD interfaces, plus every platform path selected by the full-driver scope. The COV-I915-000..015 lifecycle table is necessary but NOT a substitute for per-file semantic/dependency coverage. Existing F-series/Cherryview patches are inputs, not evidence that missing translation units or adapters are completed.

## ACCEPTANCE_CRITERIA
Every lifecycle AND active-unit/dependency/OS-adapter coverage row is CLOSED with Linux source/call-path and NetBSD implementation evidence; the complete imported driver and required DRM/TTM build graph compile/link cleanly. The FIRST HP target must then attach i915 without panic/hang, preserve console/rollback, activate its internal panel with correct KMS topology, reach userland and exercise runtime/recovery without invalidating F77. HP runtime success alone is not whole-driver parity proof.

## EXPLICIT_EXCLUSIONS
No silent whole-driver exclusions. The Linux-reference-inapplicable Cherryview uC/PXP path is justified for the FIRST HP hardware target only; required behavior on other upstream-supported platforms remains in whole-driver scope unless an explicit authorized scope change is recorded.

## SCOPE_CHANGE_AUTHORITY
none

## COVERAGE

| ID | Phase/component | Reference/spec evidence | Target implementation/adapter | Ordering/dependencies | Error/rollback/teardown | State | Verification |
|---|---|---|---|---|---|---|---|
| COV-I915-000 | PCI/device identification | i915_driver_probe: pci_enable_device, i915_driver_create, intel_display_device_probe | NetBSD PCI attach + device-info adapter | first | detach before later init | OPEN | source parity + attach evidence |
| COV-I915-001 | Early probe | i915_driver_early_probe | runtime info, PM early, workqueues, GT/GEM/IRQ/display early state | after device create | early unwind | IN_PROGRESS | call-graph + object/kernel build |
| COV-I915-002 | GT discovery | intel_gt_probe_all | GT topology/context allocation | after early probe | GT release | OPEN | source parity + build |
| COV-I915-003 | MMIO/uncore/forcewake | i915_driver_mmio_probe | BAR, uncore, MCHBAR, forcewake, engine MMIO | after GT discovery | MMIO release | IN_PROGRESS | register/state audit + build |
| COV-I915-004 | DMA/GGTT/memory regions | i915_driver_hw_probe | DMA info, GGTT probe/init/enable, memory regions, bus master/MSI | after MMIO | GGTT/memory release | OPEN | state audit + build |
| COV-I915-005 | Display noirq/VBT/power | intel_display_driver_probe_noirq | OpRegion, VBT, display power, DMC interface, CDCLK/dbuf/FBC | after HW probe | noirq remove | OPEN | topology/power evidence |
| COV-I915-006 | IRQ install | intel_irq_install | MSI/INTx + i915 masks/handlers | after noirq display | IRQ uninstall | OPEN | IRQ/vblank/HPD verification |
| COV-I915-007 | Display hardware setup | intel_display_driver_probe_nogem | PPS, GMBUS, CRTCs, planes, DPLLs, outputs, HW-state reconstruction | after IRQ | modeset teardown | OPEN | internal-panel state evidence |
| COV-I915-008 | GEM/engines/GT init | i915_gem_init | GGTT SW, PAT, workarounds, engine/GT init, uC interfaces | after display nogem | GEM/GT release | OPEN | build + engine init evidence |
| COV-I915-009 | Protected/uC platform interfaces | intel_pxp_init, HAS_PXP/HAS_GT_UC/GSC0 predicates | CHV first-target inapplicability proven; generic upstream uC/PXP implementations and NetBSD adapters remain part of whole-driver scope | after GEM | no PXP/uC allocation on CHV; correct full lifecycle on supported platforms | IN_PROGRESS | CHV classification documented in docs/CHV-UC-PXP-EVIDENCE.md; generic build/API/semantic coverage remains OPEN |
| COV-I915-010 | Display commit/HPD | intel_display_driver_probe | initial atomic takeover, HPD, overlay, watermark IPC | after GEM/PXP | display remove | OPEN | panel active + console takeover |
| COV-I915-011 | Driver registration | i915_driver_register | DRM device, GT/perf/display/audio/fb console integration | after display commit | unregister | OPEN | device nodes + console/userland |
| COV-I915-012 | Runtime PM/power domains | Linux runtime PM + display power domains | NetBSD PM callbacks preserving wake/power ordering | after registration | runtime disable | OPEN | idle/wake cycle evidence |
| COV-I915-013 | Suspend/resume | Linux i915 suspend/resume paths | GT/display/GTT save-restore ordering | runtime capable | rollback to safe state | OPEN | suspend/resume verification |
| COV-I915-014 | Reset/recovery | GT/engine/display reset paths | reset semantics + error recovery | runtime capable | recovery unwind | OPEN | induced/recovered error evidence |
| COV-I915-015 | Remove/shutdown | i915_driver_remove/shutdown | reverse dependency teardown | final lifecycle | complete cleanup | OPEN | teardown audit |

## CURRENT_DELTA
Four pinned-reference Cherryview patches (full PPGTT, PHY_CONTROL power-well ordering, PIPE_MSA_MISC reset, and AUX precharge) pass git apply --check against the frozen clean NetBSD tree. These are PARTIAL and have no new integration build or runtime verification. Continue source/semantic classification of all 323 active Linux units and the required DRM/TTM/OS-adapter closure before building another full-scope candidate. Preserve the separate modified NetBSD port worktree and F77 safe boot.

## NEXT_UNRESOLVED
All whole-driver lifecycle rows COV-I915-000..015 remain unresolved; COV-I915-001, COV-I915-003 and COV-I915-009 are IN_PROGRESS. The CHV-specific no-uC/PXP subcase of COV-I915-009 is reference-justified but cannot close the generic full-driver row. The 323-unit per-file matrix and mandatory DRM/TTM/API/firmware dependencies must be semantically classified and closed before PARITY/TESTREADY.

## PARENT_STATUS
IN_PROGRESS
