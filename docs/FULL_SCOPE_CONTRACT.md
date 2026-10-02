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
| COV-I915-001 | Early probe | i915_driver_early_probe | runtime info, PM early, workqueues, GT/GEM/IRQ/display early state; patch 0007 restores native workqueue-failure/QoS unwind | after device create | workqueue / S0ix / power-domain early-unwind host C verified; full TTM/GT/display lifetime remains OPEN | IN_PROGRESS | source-derived generator + actual-function strict host-C fault-injection test + clean/overlay apply checks; native object/kernel pending |
| COV-I915-002 | GT discovery | intel_gt_probe_all | GT topology/context allocation | after early probe | GT release | OPEN | source parity + build |
| COV-I915-003 | MMIO/uncore/forcewake | i915_driver_mmio_probe | BAR, uncore, MCHBAR, forcewake, engine MMIO | after GT discovery | MMIO release | IN_PROGRESS | register/state audit + build |
| COV-I915-004 | DMA/GGTT/memory regions | i915_driver_hw_probe | DMA info, GGTT probe/init/enable, memory regions, bus master/MSI | after MMIO | GGTT/memory release | OPEN | state audit + build |
| COV-I915-005 | Display noirq/VBT/power | intel_display_driver_probe_noirq | OpRegion, VBT, display power, DMC interface, CDCLK/dbuf/FBC | after HW probe | noirq remove | OPEN | topology/power evidence |
| COV-I915-006 | IRQ install | intel_irq_install and Linux VLV/CHV EIR/EMR/DPINVGTT ACK and per-plane fault capture | patch 0006 implements EIR/EMR and DPINVGTT ACK/masking, double EIR reset and posting reads, per-pipe primary/sprite/cursor fault bitmap and CTL/SURF/SURFLIVE capture; whole-driver IRQ and NetBSD build remain open | after noirq display; error ACK before IIR clear | IRQ reset and disable sticky GTT status | IN_PROGRESS | generator reproduces committed patch byte-identically; git apply --check on frozen NetBSD and separate overlay exit 0; kernel compilation and runtime unverified |
| COV-I915-007 | Display hardware setup | intel_display_driver_probe_nogem | PPS, GMBUS, CRTCs, planes, DPLLs, outputs, HW-state reconstruction | after IRQ | modeset teardown | OPEN | internal-panel state evidence |
| COV-I915-008 | GEM/engines/GT init | i915_gem_init | GGTT SW, PAT, workarounds, engine/GT init, uC interfaces | after display nogem | GEM/GT release | OPEN | build + engine init evidence |
| COV-I915-009 | Protected/uC platform interfaces | intel_pxp_init, HAS_PXP/HAS_GT_UC/GSC0 predicates | CHV first-target inapplicability proven; generic upstream uC/PXP implementations and NetBSD adapters remain part of whole-driver scope | after GEM | no PXP/uC allocation on CHV; correct full lifecycle on supported platforms | IN_PROGRESS | CHV classification documented in docs/CHV-UC-PXP-EVIDENCE.md; generic build/API/semantic coverage remains OPEN |
| COV-I915-010 | Display commit/HPD | intel_display_driver_probe; pinned Linux g4x_dp/g4x_hdmi audio-enable phases | VLV/CHV DP/HDMI audio presence and codec setup moved to enable phase after port pre-enable by patch 0005; generic display/HPD/atomic/console paths still pending | after GEM/PXP and port readiness | display remove | IN_PROGRESS | two-file patch checks against frozen NetBSD and existing overlay; host C real-function sequencing test exit 0; NetBSD build/panel/HPD pending |
| COV-I915-011 | Driver registration | i915_driver_register | DRM device, GT/perf/display/audio/fb console integration; NetBSD void registration currently logs DRM register failure then continues | after display commit | missing return-code propagation + full reverse registration/probe unwind under review | OPEN | pinned function-level delta in docs/I915-PROBE-DELTA-20261002.md; implementation/build pending |
| COV-I915-012 | Runtime PM/power domains | Linux runtime PM + display power domains | NetBSD PM callbacks preserving wake/power ordering | after registration | runtime disable | OPEN | idle/wake cycle evidence |
| COV-I915-013 | Suspend/resume | Linux i915 suspend/resume paths | GT/display/GTT save-restore ordering | runtime capable | rollback to safe state | OPEN | suspend/resume verification |
| COV-I915-014 | Reset/recovery | GT/engine/display reset paths | reset semantics + error recovery | runtime capable | recovery unwind | OPEN | induced/recovered error evidence |
| COV-I915-015 | Remove/shutdown | i915_driver_remove/shutdown | reverse dependency teardown | final lifecycle | complete cleanup | OPEN | teardown audit |

## CURRENT_DELTA
Patch 0007 corrects the NetBSD-specific `i915_driver_early_probe` workqueue-init error path and removes the sideband PM-QoS request on all previously unhandled early-failure paths. Its pinned generator and published patch are byte-identical on Legion; strict host C11 compilation/failure-injection of the actual adapted C function passes workqueue/S0ix/power-domain failure and success cases, and clean frozen NetBSD plus six-edit overlay `git apply --check` pass. This closes only a bounded COV-I915-001 unwind defect; full early-probe parity, native object build and runtime remain OPEN. The source-anchored Linux/NetBSD lifecycle delta is recorded in docs/I915-PROBE-DELTA-20261002.md, including COV-I915-011's observed registration-failure handling gap.

Patch 0006 generator/committed artifact were synchronized in commit d2d86bb152710474ae291ccaf36ae5a01aafcdf0: two IRQ-context DRM_ERROR calls now use the existing NetBSD DRM_ERROR_RATELIMITED macro. On Legion the generator's output is byte-identical to the published patch (cmp exit 0), and git apply --check passes on both frozen clean NetBSD and the preserved six-edit port overlay. This closes only the generated-artifact consistency defect within COV-I915-006; NetBSD object compilation, IRQ integration and runtime evidence remain OPEN.

Six pinned-reference Cherryview/VLV patches (full PPGTT, PHY_CONTROL power-well ordering, PIPE_MSA_MISC reset, AUX precharge, VLV/CHV DP/HDMI post-enable audio sequencing, and VLV/CHV display error IRQ fault capture) pass git apply --check individually against frozen NetBSD. Patches 0005 and 0006 also pass against the existing six-edit overlay; patch 0005 has a strict host-C audio phase test. The sixth patch still requires NetBSD compilation and runtime validation. These are PARTIAL and have no new integration build or runtime verification. Continue source/semantic classification of all 323 active Linux units and the required DRM/TTM/OS-adapter closure before building another full-scope candidate. Preserve the separate modified NetBSD port worktree and F77 safe boot.

## NEXT_UNRESOLVED
All whole-driver lifecycle rows COV-I915-000..015 remain unresolved; COV-I915-001, COV-I915-003, COV-I915-006, COV-I915-009 and COV-I915-010 are IN_PROGRESS. The CHV-specific no-uC/PXP subcase of COV-I915-009 is reference-justified but cannot close the generic full-driver row. The 323-unit per-file matrix and mandatory DRM/TTM/API/firmware dependencies must be semantically classified and closed before PARITY/TESTREADY.

## PARENT_STATUS
IN_PROGRESS
