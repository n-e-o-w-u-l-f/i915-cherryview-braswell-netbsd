# i915 Linux-to-NetBSD lifecycle contract

## Authority and rule

Hardware ordering is frozen to Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab (v5.6-rc3 lineage), using the i915 driver state in that revision. NetBSD may replace OS services only: PCI attachment, bus_space/bus_dma, workqueues/tasks, locking, firmware loading, DRM device publication, memory mapping, console attachment, power management and teardown.

A port is complete only when every phase below has an owner, dependency, error exit and target-hardware result. Copying a current Linux file into the older NetBSD drm2 import is not a port.

| Phase | Linux behavioral anchor | Required NetBSD owner | Acceptance evidence |
|---|---|---|---|
| G00 select | PCI i915 ID match and platform information | i915 PCI autoconfiguration match/attach | CHV 8086:22b1 is selected, no duplicate genfb ownership |
| G01 early probe | i915_pci_probe -> i915_driver_probe -> i915_driver_early_probe | PCI/BAR/forcewake/runtime service adapter | reversible PCI/BAR trace and error unwind |
| G02 memory/GT | GGTT, stolen memory, GEM and engine setup | bus_dma/UVM/GEM object and mmap lifetime | allocation, fence and release tests |
| G03 MMIO/platform | i915_driver_mmio_probe and device-info/VBT/OpRegion discovery | bus_space, ACPI/VBT and platform quirk adapter | CHV device and VBT values captured without display takeover |
| G04 display foundation | i915_driver_modeset_probe / intel_modeset_init | DRM mode_config, power-domain and encoder/connector graph | connector graph and error paths exist before output enable |
| G05 eDP discovery | VBT port decision then intel_dp_init for CHV port C | eDP connector/AUX/HPD adapter | panel is identified, but no pipe is enabled yet |
| G06 panel/link | panel power sequencer, AUX transactions, DPIO/PLL and DP link training | NetBSD delay/poll/lock adapters preserving register order | off-panel log records every completion/timeout |
| G07 atomic output | CRTC state, pipe, transcoder, plane and vblank enable | DRM atomic/modeset/vblank adapter | a known mode lights the panel and survives mode disable/re-enable |
| G08 DRM registration | i915_driver_register, HPD polling and connector notifications | character device, ioctl, event/poll/kqueue, file/minor lifetime | /dev/dri userspace interface passes smoke test |
| G09 console handover | intel_fbdev_initial_config_async, fb helper and intelfb/drmfb attachment | task boundary and wsdisplay lifetime | console moves from firmware framebuffer without black screen |
| G10 userspace data path | GEM ioctl, execbuffer, mmap, fence, PRIME where supported | ABI translation and UVM synchronization | libdrm/modesetting render and scan-out smoke tests |
| G11 PM/recovery | runtime suspend/resume, reset, hang/error paths | NetBSD PM, callout/workqueue and reset lifetime | display and DRM recover without leaked resources |
| G12 detach | driver unregister, fbdev teardown, engines/GEM/memory/PCI release | inverse-order detach with blocked new work | repeated attach/detach has no dangling device or mapping |

## HP black-screen implication

F83 and F84 show firmware text and then a black panel with backlight. That places the reproducible failure somewhere from G04 through G09. F84 rejected only one G09 scheduling hypothesis. It does not identify the failed phase.

The next instrumented test must log G01 through G09 to a serial or independent network console that remains live after panel ownership changes. A single test may cross one unobserved boundary only; all other phases remain at their F77 recovery behavior.

## Explicit non-claims

This contract is an implementation and test matrix, not proof that the current repository has a usable KMS console, full DRM ABI, accelerated rendering or a release-quality driver.