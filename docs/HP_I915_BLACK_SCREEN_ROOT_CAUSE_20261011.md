# HP TPN-W121 i915 black-screen investigation — 2026-10-11

Status: **REPRODUCED / ROOT CAUSE NOT YET OBSERVABLE / NO FIX CLAIMED**.

## Exact observation

The safe F77 kernel boots and shows the firmware framebuffer with i915drmkms disabled. Both F83 and F84 show the firmware's green boot text, then the internal panel becomes black while its backlight remains enabled.

The two test kernels differ only in the F84 NetBSD fbdev scheduling adapter:

- F83 used the prior synchronous compatibility behaviour.
- F84 deferred the same initial fbdev configuration through the existing i915 autoconfiguration task queue, matching Linux's post-registration asynchronous boundary.
- F84 was linked successfully and carried the expected F84 identity.
- F84 produced the same black screen with backlight.

Therefore the historical NetBSD `async_schedule()` reentrancy difference is **not sufficient to explain the HP failure**. The F84 patch is preserved under `research/rejected/` for traceability and must not be promoted to a release driver.

## Available evidence

- Current live system is F77: `RTWN8723BE-F77-LINUX-EFUSE-MAP`.
- F77's recovery configuration explicitly disables i915drmkms and retains the firmware framebuffer.
- The black transition occurs after visible firmware output, placing the failure at or after i915 takeover rather than basic panel power/backlight firmware initialization.
- No i915/DRM diagnostic survived in `/var/log/messages*`; after recovery, the only related line is F77's `drm at genfb0 not configured`.
- F83 and F84 test kernels and menu entries were removed after the failed hardware test. F77 remains default.

## What cannot be concluded

There is no retained trace identifying a failing register write, DP AUX timeout, eDP link-training failure, PLL failure, plane/pipe mismatch, or intelfb console handover. Treating any of those as the root cause would be speculation.

## Root-cause boundary

The evidence narrows the failure to the shared i915drmkms display/takeover path before a usable NetBSD console is re-established. The next test must make the boundary observable before it changes display ownership:

1. retain an independent serial or network console that does not rely on the internal panel;
2. record each boundary: PCI probe, GEM/GT initialization, VBT/eDP discovery, panel power sequence, AUX/link training, pipe/plane enable, fbdev creation, and wsdisplay takeover;
3. test one boundary at a time against the F77 recovery kernel;
4. preserve logs off-machine before any display-state transition.

No further display-register change is justified until that trace exists.

## Linux reference

The authoritative behavioral reference is Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab` (v5.6-rc3 lineage), not a modern current-Linux file copy. NetBSD must adapt OS lifecycle APIs while retaining the Linux hardware transition order.
