# HP i915 / DP AUX — NetBSD 11 native executable unwind regression (0068)

**Scope:** Native NetBSD 11 **userland execution of actual copied DRM/i915 function bodies with mock kernel interfaces**. NOT a NetBSD kernel fault-injection test, not a Cherryview/Braswell GPU/KMS validation, not an RTL8723BE WPA2 test.

**Canonical PRE/POST:** [Agent-Governance 0068](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/state/events/hp-i915-0068-netbsd-native-unwind-runtime-20261021.jsonl).
**Reference C extracted source:** [0065 provenance](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/docs/HP-I915-0065-CONNECTOR-UNWIND-EXTRACTED-HARNESS-20261021.md).
**0064 native diagnostic kernel:** SHA256 `22d0fd9e4c1aa3eac10cd6a4b0c67de6c16820aeba0150e38a8f6bb65195028e`.

## Content / provenance

`connector_unwind_netbsd_0068.c` is the local Legion 0068 portable C harness **byte-for-byte**, SHA256 `4dfbb5c17b39960ca01744492cc42805f73a0bed155e23a3fb045e7b99f6d10c`. Original unmodified extracted 0065 source was SHA256 `1a1e5923eabdc5b71069a0f26670e2bd51e55e8cd70272e25c482b452f2d207d`. The **only** 0068 source edit was to guard the 0065 *test-prelude* definition of `__UNCONST` with `#ifndef __UNCONST` because NetBSD `sys/cdefs.h` already defines it. All 11 verbatim copied bodies were independently rehashed and found unchanged. The test draws source code from existing GPL-covered Linux i915 and BSD DRM/NetBSD sources; honor the respective upstream licenses when redistributing.

Production i915 files, the NetBSD kernel, and HP boot settings **are never modified by this test**.

## Verify a pinned NetBSD 11 cross-compiler environment

NetBSD/src pinned at `03d918f6d0e81fa05b8f1160eca0628ad39988a6`, NetBSD target compiler GCC 12.5.0. Official NetBSD 11 amd64 userland snapshot pinned to `netbsd-11/20261021045729Z`; `base.tar.xz`, `etc.tar.xz`, `rescue.tar.xz`, and `comp.tar.xz` downloaded from the NetBSD official immutable snapshot and checked against its published SHA512 manifest.

For the `comp.tar.xz` archive, SHA512:

`539f09338ee8b61bd6ed018be8c0d95f3d5ade19fe53547667d5c25f7947c22452d0e1300bdc86013a9da3544b95712f209cd00d81ddd8fa384506a1fac51f2e`.

Create a separate target sysroot by extracting **verified** base and comp into a non-host root. Do not untar system absolute symlinks into the host filesystem unsafely; use a rooted, controlled extraction. The target sysroot must contain `usr/include/stdio.h`, `usr/lib/libc.a`, `usr/lib/crt0.o` and the standard NetBSD startup files.

On Legion's existing verified build checkout:

```sh
export NETBSD11_CC=/opt/ChatGPT/hp-driver-port/netbsd-tools-03d918f6/bin/x86_64--netbsd-gcc
export NETBSD11_SYSROOT=/var/lib/sentinelx/uploads/i915-0068-netbsd-native-unwind-20261021-a01/netbsd11-sysroot
sh tests/hp-i915/native/build_connector_unwind_netbsd_0068.sh ./test0068
file ./test0068
```

Expected native file format: `ELF 64-bit LSB executable, x86-64, statically linked, for NetBSD 11.0`. First successful 0068 build binary SHA256: `cd7182f2be8e8fe922a75f8f7e541c326428024bb7f64d433c0d5ffaee1c2149`. Build flags `-v -O2 -std=gnu11 -Wall -Wextra -Werror -static`, no warnings or build errors.

## Execute **inside NetBSD 11**, not Linux

The executable must run under real NetBSD/amd64. The completed 0068 test used the **0064** native NetBSD 11 i915+RTL kernel with a safe QEMU x86 PC virtual disk, guest command `test0068`, `-nic none`, `-drive ...,snapshot=on`, `-machine pc,accel=tcg`. The binary was placed in the isolated guest `/bin/test0068` in a separate FFSv2 image built with `nbmakefs`, root-owned guest metadata via `nbmtree -c` and `nbmakefs -F` without host privilege escalation.

The actual screenshot `0068-netbsd11-test-output.ppm` SHA256 `bde2432308e408d19cf34e22fba701e6f572876fce3f1653f8f0143bc780742d` displayed all nine PASS cases, `SUMMARY cases=9 assertions=40 failures=0`, and a returned guest root prompt. The QEMU run exited 0 with stderr 0 and preserved original kernel/rootfs SHA.

The nine scenarios cover first connector one-shot injection, backlight failure before the trigger, original i915 checkpoint preservation, modeset failure cleanup, connector rollback, DP AUX deferred finalization, mocked AUX-register failure, normal DP unregister, and the pre-register device state.

**Limitations:** The original functions execute against a **host-designed mock of the kernel API inside a genuine NetBSD guest process**. An I2C/AUX mock can return failure even though current NetBSD i915 I2C registration shim may unconditionally succeed. Real kernel locks, NetBSD kernel unwind, actual DRM error injection, MSI/IRQ/DMA/PCI and physical HP VGA/eDP/KMS are not tested. The QEMU graphics device is standard VGA, not Cherryview. No HP diagnostic boot is authorized absent independent early console and a physically exercised stock/F77 rollback.

## Governance / source management

The C harness was authored and compiled in a unique **local Legion scratch** first, then published on the private i915 work branch and read back byte-for-byte. The work tree source was based on the pinned frozen 0064 source and 0065 exact extraction hashes; the GitHub work HEAD was checked before writing. No local full repository `git pull` occurred because this SentinelX service identity lacks the trusted Git/SSH operator credentials; treat that as a **workflow exception**, not evidence that general project `pull → edit → push` has been met. Reconcile any long-lived checkout with the updated private work branch before further modifications.

Only after tests pass under NetBSD guest can this be described as a validated regression test. It must not be promoted to a public hardware release or treated as the real DRM failure injection requested for HP.
