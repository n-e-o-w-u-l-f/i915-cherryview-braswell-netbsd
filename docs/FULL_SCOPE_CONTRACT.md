# FULL-SCOPE CONTRACT — Linux i915 -> NetBSD

Status: IN_PROGRESS

## OBJECTIVE
Port the complete pinned Linux i915/DRM behavior required for the HP 17-x037ng Intel 8086:22b1 Cherryview target to NetBSD while preserving Linux hardware-visible state transitions, dependency ordering, error handling, teardown/recovery, and NetBSD-specific adapter boundaries.

## REQUIRED_COVERAGE
All material i915 lifecycle phases from PCI/device creation through GT/MMIO/GGTT/GEM, display/PHY/power/IRQ, runtime PM, suspend/resume, reset/recovery, and shutdown. Existing partial F-series patches are evidence/inputs, not substitutes for unresolved rows.

## ACCEPTANCE_CRITERIA
Every required coverage row is CLOSED with source/call-path evidence and NetBSD implementation evidence; the integrated kernel builds cleanly; the HP target completes i915 attach without panic/hang, preserves console/rollback, activates the internal panel with correct KMS topology, reaches normal userland, and exercises runtime/recovery paths without invalidating the safe recovery kernel.

## EXPLICIT_EXCLUSIONS
No silent exclusions. Platform firmware interfaces not required by Cherryview may be adapted/stubbed only when Linux/reference evidence shows they are not hardware requirements for this target; such decisions must be recorded against the affected row.

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
| COV-I915-009 | Protected/uC platform interfaces | intel_pxp_init and platform firmware interfaces | target-appropriate adapter/stub only where evidenced | after GEM | fini paths | OPEN | platform applicability audit |
| COV-I915-010 | Display commit/HPD | intel_display_driver_probe | initial atomic takeover, HPD, overlay, watermark IPC | after GEM/PXP | display remove | OPEN | panel active + console takeover |
| COV-I915-011 | Driver registration | i915_driver_register | DRM device, GT/perf/display/audio/fb console integration | after display commit | unregister | OPEN | device nodes + console/userland |
| COV-I915-012 | Runtime PM/power domains | Linux runtime PM + display power domains | NetBSD PM callbacks preserving wake/power ordering | after registration | runtime disable | OPEN | idle/wake cycle evidence |
| COV-I915-013 | Suspend/resume | Linux i915 suspend/resume paths | GT/display/GTT save-restore ordering | runtime capable | rollback to safe state | OPEN | suspend/resume verification |
| COV-I915-014 | Reset/recovery | GT/engine/display reset paths | reset semantics + error recovery | runtime capable | recovery unwind | OPEN | induced/recovered error evidence |
| COV-I915-015 | Remove/shutdown | i915_driver_remove/shutdown | reverse dependency teardown | final lifecycle | complete cleanup | OPEN | teardown audit |

## CURRENT_DELTA
Reconcile the existing Cherryview/IOSF/F82 partial work against COV-I915-001 and COV-I915-003, then continue dependency closure into COV-I915-002 and COV-I915-004 without treating any local compile or black-screen change as parent completion.

## NEXT_UNRESOLVED
COV-I915-000 through COV-I915-015 remain unresolved; COV-I915-001 and COV-I915-003 are currently IN_PROGRESS.

## PARENT_STATUS
IN_PROGRESS
