# HP NetBSD 11 — pinned G01–G09 i915 boot-phase trace

Status **SOURCE-PATCH-TESTED ONLY**, not native compiled and not installed.
Only the pinned `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`
`sys/external/bsd/drm2/dist/drm/i915/i915_drv.c` is in scope.
This is instrumentation, NOT a complete Cherryview DRM/KMS port.

Published artifacts:

- Generator: `tools/generate_hp_i915_boot_phase_trace_patch.py`;
  refuses a dirty/wrong NetBSD source pin and existing output.
- Ready patch: `patches/0038-netbsd11-i915-g01-g09-boottrace.patch`;
  changes only the frozen driver's `i915_drv.c` through
  `#ifdef __NetBSD__`-guarded kernel `printf` statements.
- Regression: `tests/test_hp_i915_boot_phase_trace_source.py`;
  validates source vs commit-pinned actual NetBSD C, exact nine paired
  markers, no control-flow/unwind changes, deliberate mutation rejection,
  byte-for-byte generated-patch equality and real `git apply` in
  disposable source fixture.

## G01–G09 actual call-path boundaries

| Marker | Frozen NetBSD C function/call | What can be inferred |
|---|---|---|
| G01 | `i915_driver_probe → drm_pci_attach` | PCI DRM device attach |
| G02 | `i915_driver_probe → i915_driver_early_probe` | early device-owned state |
| G03 | `i915_driver_probe → i915_driver_mmio_probe` | BAR/MMIO initialization |
| G04 | `i915_driver_probe → i915_driver_hw_probe` | GT/GGTT and memory hardware |
| G05 | `i915_driver_modeset_probe → intel_bios_init` | VBT/BIOS setup |
| G06 | `i915_driver_modeset_probe → intel_power_domains_init_hw` | display power-domain setup |
| G07 | `i915_driver_modeset_probe → intel_irq_install` | IRQ installation |
| G08 | `i915_driver_modeset_probe → intel_modeset_init` | display output discovery/modeset including nested AUX |
| G09 | `i915_driver_modeset_probe → intel_fbdev_init` | DRM framebuffer setup |

Each emits `[I915 Gxx] <phase> BEGIN` before the native call and
`[I915 Gxx] <phase> END` afterwards, including `ret=%d` for calls
that return a status. A missing END narrows a hang to that call
boundary; negative return values expose the original failure.
G05 and G06 are void functions and therefore have no return code.
G08 spans a nested modeset workflow: it **cannot identify whether
eDP/AUX, PLL/DPIO or powerwell caused a hang**. Real wsdisplay
handoff is likewise NOT explicitly instrumented by this nine-stage
patch. The later fine-grained trace must be sourced from the
owning NetBSD display callbacks, not invented labels.

## Execution integration and log survival

The patch is NOT auto-applied to HP or to the RTL combined builder.
After legitimate native NetBSD build access, the combined build owner
must apply it to a new, SHA-checked private source snapshot in a known
order with the other approved source patches. Check `git apply --check`
and exact source before integrating; run HP native compiler `-Werror`
and linked full ELF verification. No release manifest may be invented
from a trace-patch test.

The private combined kernel's NetBSD config now selects DDB,
DDB_TEE_MSGBUF=1 and a 256 KiB kernel message buffer.
The **four-mode** staging contains a separate nondefault combined-kernel
entry and `kern.* /var/log/hp-kernel-boot.log` route with a staged
opt-in `hpbootlogprep` rc.d service that precreates a root-readable-only
file before syslogd, without overwriting an existing file.

Messages printed before syslog startup can exist in RAM msgbuf; a
persistent file depends on userland and /var becoming available.
A panic dump depends on actual configured dump device and savecore.
A hard freeze before dump/userland may still lose RAM data.
The physical recovery/independent earlier console has NOT been proved
on the present HP; **do not use this patch to authorize a reboot**.

## Verified source tests

Legion disposable clone at source
`556c348277eaaafb7698ad3fbb3b0c1a8acadf2a`,
NetBSD upstream `i915_drv.c` 79,328 bytes and SHA256
`88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8`.

Four source-only tests PASS with Python exit 0:
boot mode renderer; native NetBSD UEFI/mock HP audit; pre-syslog
no-clobber and link/directory negative tests; nine-phase i915 C
transformation, exact committed patch and `git apply` check.
No target NetBSD native compiler, full i915/RTL link, installation,
boot or actual hardware KMS/WPA2 acceptance.
