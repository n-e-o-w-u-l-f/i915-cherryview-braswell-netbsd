# Project status

Date: 2026-09-29

## Hardware

HP TPN-W121, Intel Celeron N3060 / Braswell, NetBSD 11.0 amd64.

GPU:

```text
PCI vendor/device: 8086:22b1
Revision:           0x35
Subsystem:          103c:8205
Platform:           Intel Cherryview (CHV), Gen8 LP
```

## Current boot-proven state

The target currently runs `RTWN8723BE-F77-LINUX-EFUSE-MAP`.

The boot chain is UEFI-based: the running kernel reports an EFI system table, NetBSD provides `/usr/mdec/bootx64.efi`, and the disk has a FAT/MSDOS boot wedge plus an FFS NetBSD root wedge. The active `/boot.cfg` entries intentionally execute `userconf disable i915drmkms*` before loading their kernels.

With i915 disabled the live console is:

```text
genfb0: Intel HD Graphics (rev. 0x35)
genfb0: framebuffer at 0x80000000, size 1024x768, depth 32, stride 4096
wsdisplay0 at genfb0
drm at genfb0 not configured
```

Therefore EFI and the NetBSD bootloader path reach the kernel correctly; the normal recovery menu deliberately prevents i915/KMS takeover.

## Reproduced graphics problem

Booting with `i915drmkms` enabled has historically produced a black screen on this target. The safe F77 path must remain available and must not be replaced while the KMS path is under test.

## Source findings

- NetBSD 11 already maps `8086:22b1` to `INTEL_CHERRYVIEW` / Gen8 LP.
- NetBSD 11's `chv_info` device-information block matches the Linux 5.6 CHV block; the PCI identity/platform description is not the missing piece.
- CHV-specific DPIO routing is present.
- BXT firmware is not a valid substitute for CHV; no CHV DMC/GuC/HuC firmware fabrication is planned.
- NetBSD's i915 probe intentionally treats `-EIO` from `intel_gt_init()` as a wedged-GT condition where GPU submission is disabled but KMS is kept alive.
- In that error path `intel_gt_pm_fini()` tears RPS down. A later fbdev modeset can still call `intel_rps_mark_interactive()`, whose unguarded first operation is locking `rps->power.mutex`.
- This exact Braswell/Cherryview-style failure has been reported upstream: GT initialization/reset fails, RPS is finalized, then fbdev reaches `intel_rps_mark_interactive()` and panics on an uninitialized/destroyed mutex.

## Current isolated fix candidate

Branch: `work/chv-rps-kms-recovery-20260929`

Patch: `patches/0001-i915-rps-kms-recovery-guard.patch`

The patch adds one narrow condition before touching the RPS mutex:

```c
if (intel_gt_has_init_error(rps_to_gt(rps)))
        return;
```

This changes behavior only for a GT explicitly wedged during initialization. Healthy runtime RPS behavior is unchanged. The companion source-level test verifies that the guard exists and executes before the mutex lock.

## Verification state

- Source comparison: VERIFIED.
- Regression condition against vanilla NetBSD 11 source: RED (guard absent).
- Patched source condition: GREEN (guard before mutex lock).
- Kernel compile on target: NOT YET RUN.
- Hardware boot with i915 enabled: NOT YET RUN.
- Production `/netbsd`: untouched.
- F77 fallback: untouched.
- Automatic reboot: prohibited.

## Next work package

1. Apply the isolated RPS/KMS recovery patch to the target NetBSD source tree.
2. Run the regression check against the patched source.
3. Build a separate i915 diagnostic kernel; do not replace `/netbsd`.
4. Add a separate boot-menu entry that enables i915 only for that kernel while preserving the F77 `genfb` fallback.
5. Boot only under explicit user control and collect the complete i915/GT/RPS/intelfb log.
6. If KMS survives, distinguish display success from GPU-submission success; a wedged GT may still provide usable KMS but not acceleration.
7. Continue CHV engine-reset/root-cause work only from the captured log.
