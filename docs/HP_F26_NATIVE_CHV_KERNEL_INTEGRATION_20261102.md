# F26 — complete Cherryview patch composition for HP-native compile-only kernel

**Project:** i915 Cherryview/Braswell → NetBSD 11.0 amd64, HP TPN-W121 (PCI 8086:22b1).

**Status (2026-11-02): SOURCE PUBLISHED / NATIVE HP BUILD NOT_RUN /
HARDWARE KMS NOT_RUN / RELEASE NO-GO.** F26 source is isolated on
`work/hp-f26-chv-full-integration-20261102`, descended from exact
F25 commit `9a9110352e9a4f65d5a6d41326c797863141929e`.
Do not change, select or boot `/netbsd`, F77 or `/boot.cfg`.

## What is implemented

`tools/run_f26_native_chv_kernel.py` reuses the previously source-audited
F25 empty-object NetBSD `build.sh` implementation; it replaces the F25
four-patch list with eleven pinned real NetBSD patches:

- Console failure-preflight/F22 failover: F19, F20, F21, F22 (4).
- Cherryview-specific old-NetBSD driver updates: 0001 full PPGTT,
  0002 PHY powerwell, 0003 MSA, 0005 HDMI/DP audio,
  0006 display-error IRQ, F17 physical DPIO PHY signal-level consumer,
  F15 GPLL RPS lock-order correction (7).

The older F14 GPLL-only and F16 DPIO-provider-only patches are **excluded**:
their hunks overlap and their newer counterparts contain their shared
changes. The aggregate touches exactly 17 original NetBSD source files.

### Source and execution gates

1. Verify exact NetBSD 11 pinned source revision
   `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6` via
   the 17 original Git blob IDs obtained from that commit's tree.
2. Verify all 11 published candidate patch Git blob IDs and the exact
   permitted path set for each via `git apply --numstat`; forbid
   unpinned or path-traversal changes.
3. Require actual `NetBSD 11`, `amd64/x86_64` and physical hostname
   `hp-tpnw121` before any project/build file output. Linux/Legion
   must refuse. An explicit `--ack-compile-only` flag is required.
4. Require the existing RTL8723BE PHY NetBSD stage source Git blob from
   F25, nonbootable baseline kernel config, new scratch path under
   `/tmp`, private copied toolchain and available scratch disk.
5. Apply all eleven ordered patches with real Git checks, isolate all
   changed source files in a symlink-forest overlay, generate distinct
   `F26_CHV_FULL_RTL_TEST` NetBSD kernel configuration, rebuild a
   **new** object tree, require kernel ELF64 and key i915 objects.

The runner has **no install, bootloader, firmware or reboot operation**.

## Tests and current limits

- Code files published and independently read back:
  `tools/run_f26_native_chv_kernel.py` and
  `tests/test_f26_native_chv_kernel.py`.
- Regression source covers patch identities/scopes, 17 source pins,
  non-HP/NetBSD-version refusal, unsafe numstat paths, F25 builder
  reconfiguration, and refusal without explicit compile-only acceptance.
- Attempts to execute the current F26 source/model test through Legion
  encountered a provider security denial; equivalent execution was not
  retried via another tool or host. Treat Python regression execution
  as **NOT_RUN**, not PASS.
- F25's 3265-object Linux cross-build was previously completed for
  **F19–F22 only**. It did NOT compile this 11-patch F26 composition
  and does not replace the required genuine HP NetBSD 11 native test.
- No actual HP-native `build.sh`, compile/link, display trace, modeset,
  complete GEM/DRM ABI or RTL WPA2 acceptance exists for F26.

## Next independent hardware-owner gate

First confirm a presently authorized HP native shell and separately verify
actual source-stage paths, disk capacity, original source snapshot, tools,
`git status`, the physically known F77 default and working recovery.
Only then run the F26 **compile-only** script on HP using an explicitly
authorized new scratch path. Preserve output and native object/build logs.
A successful kernel compile is still **not** TESTREADY for boot. Physical
early-console transport, failure-path display traces and rollback must be
independently proven before considering any experimental boot.

A provider-refused shell/access route may not be retried through an alternate
account, tool or machine. Source-only work remains distinct from native HP
execution evidence.
