# F23 — F21/F22 actual native i915 attach-real integration regression

**Date:** 2026-10-28
**Status:** real pinned NetBSD source extracted, full function host-compiled
and executed, GitHub branch published. **No NetBSD kernel object/link,
no HP boot, no installed kernel changes.**

## Why F23 was needed

F22's prior 80 host-C scenarios exercised the exact newly added
i915drmkms_fwfb_failover() helper but not its caller. This failed to
prove the *real* i915drmkms_attach_real() control flow would call
failover only after the correct probe error and only with no queued
synchronous tasks, or preserve normal i915 initialization.

F23 solves this test gap without altering the production F21/F22
patches. It extracts the entire unmodified function body of
i915drmkms_attach_real() from the real original NetBSD C source AFTER
applying the F21 and F22 patches, together with the exact F22 helper.
A narrowly mocked external NetBSD/DRM layer allows compiling and
executing the unchanged native C in host GCC/Clang.

## Source and builds

Native source commit:
NetBSD/src 03d918f6d0e81fa05b8f1160eca0628ad39988a6

Verified original git blob IDs:
- i915_pci_autoconf.c:
  9798385b02f247c08db9b16624d5ddc9d11a8ca5
- files.i915drmkms:
  23d352b64eb1799caf3e9b2770f78795accc8439

Production patches unchanged:
1. patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch
2. patches/candidates/netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch

Exact source test:
tests/test_f23_i915_attach_real_integration.py

Test uses actual git apply --whitespace=error --check and git apply on
both full pristine NetBSD source files, then GCC and Clang each under
GNU99 and GNU11; each configuration is built both with
HP_I915_FWFB_FAILOVER undefined and defined. -Wall -Wextra -Werror
and UBSan are used, with -Wno-unused-function solely because the
option-off harness intentionally provides external API stubs not
referenced without failover.

There are 56 situations per build:
2 probe results x 2 task queue states x 7 console/fallback conditions
x 2 power-management registration outcomes. 8 builds * 56
= **448/448 PASS**.

The queue is populated INSIDE the mocked i915_driver_probe call,
after the actual native function sets sc_task_thread = curlwp:
this models the real synchronous callback scheduling point more
accurately than prepopulating the queue before the attach function.
The native success path still drains the queue in FIFO fashion,
registers PMF handlers and resets task ownership. Failure with queued
callbacks does not discard them or claim a successful fallback.
Failure with an empty queue clears ownership; only an option-on
build attempts the firmware framebuffer console and only if its
native preflight conditions pass.

One *negative mutant* inverts the native failure-branch queue guard.
It compiles but is rejected by the same runtime assertions, proving
that the regression would detect incorrectly executing failover with
a nonempty queue or leaving the empty-queue owner stale.

Executed on the Legion Linux host:
- F23: F23_F21_F22_REAL_I915_ATTACH_REAL_448_GCC_CLANG_UBSAN_CASES_PASS
- Native-branch negative mutant rejected.
- F22 standalone 80/80 host-C source test PASS again.
- F21 standalone test was NOT rerun in this invocation: its CLI
  requires a full pinned NetBSD Git checkout, whereas the latest
  regression used individually Git-blob-verified original files.
  Earlier full-pinned-tree F21 test passed in the prior stage.

## Scope / blocking conditions

This is NOT a real NetBSD ABI compilation:
external NetBSD kernel/DRM/autoconf calls were represented by
mock headers and functions; no generated NetBSD config and no
native NetBSD compiler executed.

Current connected Linux host does not have nbmake-amd64,
x86_64--netbsd-gcc or bmake installed. NetBSD's documented
cross-build process begins with ./build.sh -U -m amd64 tools from
an appropriately complete NetBSD source checkout; the pinned
two-file fixture does not provide that environment.

No HP boot-menu-5 kernel pathname/image hash, actual panic string,
or diagnostic stack has yet been captured. Therefore F23 proves
the source-side F22 invocation semantics, NOT that the HP boot
failure is resolved. Moreover, the real framebuffer mapping or
display hardware might be unusable after failed i915 probe,
and F22 cannot fix every type of i915 failure.

F77, boot.cfg, /netbsd, firmware and installed HP kernels have
not been touched. F22 remains disabled by default and MUST NOT
be enabled for HP hardware solely on host-C test evidence.

Reference native NetBSD build steps:
https://www.netbsd.org/docs/guide/en/chap-build.html
