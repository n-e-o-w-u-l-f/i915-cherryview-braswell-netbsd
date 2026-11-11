# HP-I915 F47: exact native prerequisite recovery

F47 attempt A02 is **PASS for native prerequisite recovery**. All 49 historical missing files were reproduced byte-for-byte, and the unchanged full F32 core verification passed. All 1364 preserved states remain unchanged. Native Poll compilation is still a separate gate; F46's original complete admission criterion is revalidated next.

## Verified restoration

The restored tree is the original /tmp/hp-i915-f26-build-20261106-a01 path. The reviewed plan enumerates 724 source-forest entries and 1641 tool paths, totalling 305516952 regular tool bytes. Only the existing trusted source and tool inputs were used. The original make wrapper was reconstructed to its exact 1495 bytes and SHA256 dda9680d9b13eb34abc0107adcccbaa9ff505a74cd3114bbc26a22f4c91cd5a5; compiler and nm identities also match their historical receipts.

Native configuration produced 522 inventoried entries and 953537 regular bytes within the declared bounded object resource. The original 252564-byte Makefile, SHA256 ffa140e1552a45d2cf15c6f312290668b5a6b4635c1266498f59f75f6b96a1e8, and every frozen generated-header identity matched before any stock compilation.

The real process executed exactly ten successful commands: one nbconfig followed by dependency generation, GCC compilation and CTF conversion for each of sys_generic, kern_descrip and netbsd32_ioctl. The nine original object/dependency/stack-use files all match their old hashes. CTF conversion used the default label independently recovered from a same-build durable object.

All 49 original path/size/SHA256 identities then matched. Actual unchanged verify_core passed against the original F32 status SHA256 d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794. No core receipt, contract hash, source body or original acceptance condition was replaced.

## Attempt history and verification

A01 failed in its fresh Git network guard before any native output. That new guard had incorrectly disabled the existing authorized Git authentication configuration. Normal configured Git access worked; the isolated network route exited 128. The A01 controller, launch record and independently labelled failure evidence are retained at [immutable report commit d6f5f16](https://github.com/n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd/commit/d6f5f1666c510629ee297718faaba29c79025044).

The A02 correction preserves normal configuration only for network reference checks, removes inherited Git environment overrides, and keeps local Git object and validator isolation unchanged. Five focused local mock regressions passed, and independent source review approved the corrected controller. Those mocks were not native HP tests.

A02 PRE 86d77217080690fe7cf674500aeef4373cda5250 bound executor a90d2d29335376f1e729393160dcce52811936f5f4f4ed861d84545269b42134 and plan b657aae97cc821e4f454f7a54b69821eae7c01263482368be9e38b7e57bcafe6. Real process 14668 exited zero after 274.66 seconds; terminal status records completion at 2026-11-11T04:56:20.184405+00:00. No unresolved child process or unknown effect remains.

The final preservation check passed for 1364 states, including source, seven contracts, old tests, protected boot files, archived inputs and durable native artifacts. An independent cold readback verifies the restored files, command logs, configuration inventory and unchanged full core separately. [Machine-readable evidence](evidence/HP_F47_NATIVE_PREREQUISITE_RECOVERY_20261111.json) contains the exact receipts and independent result.

## Scope and continuation

Only the private historical native prerequisite tree was restored. No modern provider object, production generator, full kernel build/link, installation, boot, EFI/radio change, cleanup or hosted CI ran. F77 and the protected /netbsd and /boot.cfg remain unchanged. The parent project remains PARTIAL.

The existing 287 F46 tests remain tied to unchanged implementation/test bytes. Next, revalidate the original F46 admission criterion with the restored full core and actual public CLI rejection checks, publish its own PRE/POST, and only then plan a separate native Poll object attempt. Source/evidence and scoped Governance are published and fetched back on their canonical branches; other hosts remain unverified.
