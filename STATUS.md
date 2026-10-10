# i915 Cherryview/Braswell NetBSD status

Date: 2026-10-11

## State

**Diagnostic recovery only — not a functional i915drmkms release.**

Target hardware is the HP TPN-W121 with Intel Cherryview GPU 8086:22b1 (revision 0x35) on NetBSD 11.0 amd64.

The live recovery kernel is RTWN8723BE-F77-LINUX-EFUSE-MAP. It disables i915drmkms and retains the firmware framebuffer. It is the only normal boot target.

## Reproduced KMS failure

Both isolated i915 test kernels showed the same hardware result:

1. Firmware green boot text is visible.
2. i915drmkms takes the display path.
3. The internal panel turns black while its backlight remains on.

F83 used the original NetBSD fbdev scheduling path. F84 deferred initial fbdev setup through the existing i915 autoconfiguration task boundary to match Linux's asynchronous registration boundary. F84 linked successfully, but reproduced the same black screen.

Thus the async compatibility difference is rejected as a sufficient cause. There is no retained early i915 trace identifying the failing display boundary.

The F83/F84 kernels, source configurations, build objects, temporary scripts, boot-menu entries and boot configuration backups were intentionally removed after the test. The rejected F84 patch and evidence are retained in Git history only:

- research/rejected/20261011-f84-fbdev-async-parity.patch
- docs/HP_I915_BLACK_SCREEN_ROOT_CAUSE_20261011.md

## Port status

The project contains selected NetBSD adapter work and source-level checks. It does **not** yet prove a complete i915 driver port, a working KMS console, a working DRM user ABI, or successful HP hardware operation.

The authoritative hardware-order reference remains Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab (v5.6-rc3 lineage). Modern Linux files must be ported by behavior and dependency, not copied over the older NetBSD DRM import.

## Required next gate

Before another i915 boot:

1. Provide an independent serial or network console that survives internal panel takeover.
2. Persist a trace at PCI probe, GT/GEM setup, VBT/eDP discovery, panel power, AUX/link training, DPIO/PLL, pipe/plane enable, fbdev creation, and wsdisplay handover.
3. Execute one transition boundary per test, returning to F77 on failure.

No display register or firmware change is justified until this trace makes the failure observable.

## Release gate

Packaging is deliberately deferred. A release requires a clean NetBSD 11.0 build, repeatable KMS boot, usable DRM/ioctl/mmap behavior, display recovery, and target-hardware acceptance. Only then may the project produce signed source/binary installer archives (.tgz, .tbz, .txz) and pkgsrc/pkgin metadata.