# Full Linux i915 -> NetBSD 11 Port

## Objective

Port the complete pinned Linux i915 implementation at
`fd179f8a05be3ccae366b9b96e176b51fbe54aab` to NetBSD 11 so that the
NetBSD driver performs the same hardware-visible state transitions in the
same dependency order as Linux.

The HP 17-x037ng / Intel 8086:22b1 Cherryview system is the first hardware
verification target.  Cherryview is not the scope boundary.

Runtime boot experiments are verification only.  Hardware behaviour is
derived from the working Linux implementation and translated onto NetBSD
kernel/DRM APIs.

## Source anchors

- Linux working reference: `fd179f8a05be3ccae366b9b96e176b51fbe54aab`
- NetBSD 11 reference: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`
- Original Linux baseline imported by NetBSD DRM/i915: Linux v5.6-rc3
  `f8788d86ab28f61f7b46eb6be375f8a726783636`
- NetBSD import commit: `4a352a70313258edd1e53a9576dc62c168b9bb9e`

## Measured import size

GitHub tree inventory at the pinned revisions:

| Scope | Linux pinned | NetBSD 11 |
|---|---:|---:|
| Complete i915 tree | 915 files | 496 files |
| Same relative paths | 420 | 420 |
| Linux-only relative paths | 495 | - |
| NetBSD-only relative paths | - | 76 |
| Active i915 C files for the selected build | 323 | 150 dist + 14 local glue/overrides |

The 187 current Linux build files missing from the active NetBSD dist build
split as:

- display: 92
- GT: 40
- top-level/core: 39
- PXP: 9
- GEM: 7

This is therefore a subsystem import, not a small Cherryview patch set.

## Required current DRM dependency set

For the i915-compatible configuration, the pinned Linux Makefiles select at
least:

- DRM core: 48 C objects
- DRM KMS helper: 17 C objects
- DRM display helper: 9 C objects
- TTM: 12 C objects
- plus DRM Buddy, DRM Exec, MIPI DSI, Sync File, IOSF MBI, firmware,
  workqueue/timer/IRQ, ACPI/backlight, PCI/DMA and LinuxKPI facilities.

The NetBSD DRM core and LinuxKPI must therefore be advanced together with
i915 where the current i915 API contract requires it.

## Official NetBSD import mechanism

NetBSD already provides the correct import architecture:

- `sys/external/bsd/drm2/prepare-import.sh`
- `sys/external/bsd/drm2/drm/drm2netbsd`
- `sys/external/bsd/drm2/i915drm/i915drmkms2netbsd`

The port uses these mechanisms rather than maintaining hundreds of ad-hoc
per-file patches.

`i915drmkms2netbsd` derives NetBSD's kernel file list directly from the
Linux i915 Makefile.  The current pinned Linux Makefile resolves to 323 C
files with the selected NetBSD-equivalent configuration.

## Current Linux probe state machine

The target top-level order from pinned Linux is:

1. `pci_enable_device()`
2. `i915_driver_create()`
3. `intel_display_device_probe()`
4. `i915_driver_early_probe()`
   - runtime device info / stepping
   - MMIO debug early state
   - SBI + VLV/CHV IOSF sideband locking
   - runtime PM early state
   - i915 workqueues
   - VLV suspend state
   - TTM region device
   - root GT early state
   - GEM early state
   - IRQ early state
   - display early hooks
   - clock-gating hooks
5. `intel_vgpu_detect()`
6. `intel_gt_probe_all()`
7. `i915_driver_mmio_probe()`
   - GMCH bridge
   - uncore MMIO
   - MCHBAR
   - runtime device/display info
   - GT MMIO, uC MMIO, SSEU, MCR, engine MMIO
   - GPU sanitization
8. `i915_driver_hw_probe()`
   - eDRAM
   - DMA information
   - perf
   - GGTT probe
   - conflicting framebuffer removal
   - GGTT hardware init
   - tile/memory-region probe
   - GGTT enable
   - PCI bus master
   - MSI where supported
   - pcode
9. GVT initialization
10. `intel_display_driver_probe_noirq()`
    - OpRegion setup
    - DRAM/bandwidth
    - vblank
    - VBT/BIOS
    - display power domains
    - DMC interface
    - mode config / CDCLK / color / dbuf / bandwidth / quirks / FBC
11. `intel_irq_install()`
12. `intel_display_driver_probe_nogem()`
    - watermark model
    - panel SSC
    - PPS
    - GMBUS
    - CRTCs / planes / DPLLs
    - display hardware init
    - output/encoder setup
    - hardware-state reconstruction
    - BIOS initial plane takeover
13. `i915_gem_init()`
    - uC firmware interface
    - WOPCM
    - PAT
    - GGTT software init
    - clock-gating/workarounds
    - full GT/engine initialization
14. PXP initialization
15. `intel_display_driver_probe()`
    - HDCP component
    - flip queue
    - initial atomic commit
    - overlay
    - HPD
    - watermark IPC
16. `i915_driver_register()`
    - GEM/PMU/vGPU
    - DRM device
    - perf / GT registration
    - HWMON
    - display registration
    - OpRegion/ACPI video/audio
    - fbdev
    - runtime PM

The NetBSD port must retain this hardware ordering even where the operating
system integration calls differ.

## NetBSD adapter boundary

These are OS adaptation points, not reasons to change Intel hardware
semantics:

- PCI attach/detach and BAR mapping
- bus_dma / scatter-gather representation
- MSI/INTx allocation and interrupt establishment
- ACPI/OpRegion callbacks
- firmware loading
- workqueues, tasklets, timers, wait queues and atomics
- TTM/GEM VM integration
- sysfs/debugfs equivalents or stubs where they are non-hardware-facing
- fbdev -> drmfb/intelfb/wsdisplay console handoff
- module/autoconfiguration glue

Existing NetBSD local overrides are reviewed and either:
1. retained as thin adapters around current Linux code,
2. replaced by new LinuxKPI/DRM compatibility APIs, or
3. deleted when the current upstream implementation is directly portable.

## Port pipeline

1. Materialize the complete pinned Linux i915 tree.
2. Materialize the current DRM core/display/TTM dependencies selected by the
   Linux Makefiles.
3. Generate the active i915 file list through NetBSD's
   `i915drmkms2netbsd` model.
4. Overlay the new Linux source into an isolated NetBSD staging tree.
5. Run the NetBSD DRM import preparation.
6. Rebase NetBSD-specific glue onto the new upstream interfaces.
7. Compile without booting and run a compiler-driven API dependency closure:
   missing headers/types/functions are implemented in the proper DRM or
   LinuxKPI layer, not patched around inside i915.
8. Repeat compile closure until the complete selected i915 module and its DRM
   dependencies build cleanly.
9. Audit every hardware-visible initialization stage against the pinned Linux
   call graph, including GT/GTT/PPGTT, MMIO/forcewake, power, IRQ, OpRegion,
   VBT, ports, AUX/PPS, DPIO/PHY/PLL, planes/CRTC/transcoders and recovery.
10. Build one integrated NetBSD kernel candidate.
11. Verify on 8086:22b1 while keeping F77 as the safe default.
12. Promote only a runtime-verified stable candidate to the safe default.

## Firmware policy

The whole driver keeps the current Linux firmware interfaces for platforms
that require DMC/GuC/HuC/GSC firmware.  Cherryview itself does not gain
invented DMC/GuC/HuC requirements; its working reference boundary is the
platform firmware state (UEFI GOP/VBT/OpRegion) plus the normal Gen8 driver
state machine.

## Acceptance criteria for the first Cherryview gate

The integrated port is not considered successful merely because it compiles.

On 8086:22b1 it must at minimum:

- complete PCI/GT/MMIO/GGTT/GEM initialization without panic/hang;
- preserve correct VBT/OpRegion-derived internal-panel topology;
- establish the correct CHV power/DPIO/PHY/PPS/AUX state;
- install and service IRQ/HPD/vblank paths correctly;
- take over the firmware framebuffer without losing the NetBSD console;
- produce an active internal display with KMS;
- reach normal userland and network;
- support suspend/resume/recovery paths without corrupting the display/GTT;
- leave F77/recovery available until this state is verified.
