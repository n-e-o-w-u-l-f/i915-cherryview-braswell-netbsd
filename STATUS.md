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

The pinned source-check runner is host-independent. Historic checks that
compiled a private HP staging tree are not part of that runner after the
staging tree was removed; they require a fresh explicit NetBSD stage. See
`docs/PINNED_SOURCE_CHECK_SCOPE_20261011.md`.

The one manual GitHub Actions run after this conversion,
`38111117392` on 2026-10-11, failed before its first job step and supplied no
job log. It is an infrastructure failure, not evidence for or against any
i915 source check. See `docs/GITHUB_ACTIONS_INFRASTRUCTURE_20261011.md`.

The authoritative hardware-order reference remains Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab (Linux 7.3-rc4). The older NetBSD DRM/i915 import is the v5.6-rc3 lineage; it must not be confused with the current frozen comparison tree. Modern Linux files must be ported by behavior and dependency, not copied over that older import.

## 2026-10-12 source-prebuild gate: Cherryview full PPGTT

A previously false-positive prebuild route was closed. Without `--overlay-tree`,
`tests/test_chv_full_ppgtt_source_contract.py` previously exited successfully
after comparing *different* frozen Linux and NetBSD sources, without actually
testing application of the published `0001-chv-full-ppgtt` patch. This did
not establish a ported NetBSD behavior.

- Test source commit `1ae194bf01a34b787f8a5474e015382e22d328bc`
  now requires `--patch`, runs `git apply --check` against the exact pinned
  NetBSD checkout and applies the actual published patch to disposable copies
  of `i915_pci.c` and `intel_lrc.c`. It checks exact CHV policy-only change
  and normalized Linux PDP ring/request-allocation semantics.
- Source-check runner commit `fea70a1c08b8e5b5f507d8ca0ca0000fbe4c2180`
  now supplies the actual `patches/0001-chv-full-ppgtt-linux-1c8ee8b-netbsd11.patch`.
- Independent source-only verification: 3 actual patch hunks (2 in
  `gt/intel_lrc.c`, 1 in `i915_pci.c`) were applied in memory to exact
  NetBSD `03d918f6d0e81fa05b8f1160eca0628ad39988a6`, then compared
  with frozen Linux
  `fd179f8a05be3ccae366b9b96e176b51fbe54aab`. The target
  `emit_pdps` command sequence (omitting the duplicate final advance)
  and `execlists_request_alloc` gate match expected reference behavior,
  and CHV policy selects full 32-bit PPGTT. Source-only gate: PASS.

**Verification boundary:** The updated Python source-check runner has not
yet been executed on the real frozen checkout, and no NetBSD C object,
fully selected kernel, HP KMS, Black Screen recovery or physical mode-setting
pass is claimed. Full 323-C-unit DRM/TTM closure and early G01–G09
console trace remain OPEN. A PPGTT difference is not the observed display
black-screen root cause without a causal stack/phase trace.

## Required next gate

Before another i915 boot:

1. Provide a physically attached serial console configured for bootloader and
   kernel output. An ordinary post-boot network/syslog path is not evidence
   that G01--G09 is observable during built-in i915 attachment.
2. Persist a trace at PCI probe, GT/GEM setup, VBT/eDP discovery, panel power,
   AUX/link training, DPIO/PLL, pipe/plane enable, fbdev creation, and
   wsdisplay handover.
3. Execute one transition boundary per test, returning to F77 on failure.

No display register or firmware change is justified until this trace makes the failure observable.

The F77 transport audit found no attached serial console and does not treat
the post-boot remote agent, Tailscale, or ordinary syslog as an early-KMS trace
sink. The required trace gate is documented in
`docs/HP_I915_TRACE_TRANSPORT_20261011.md`.

The completed, manifest-driven removal of obsolete F16.0/F83/F84-era artifacts
and three byte-identical i915 source backups is recorded, with preflight and
postflight hashes, in `docs/HP_ARTIFACT_CLEANUP_20261011.md`. It did not alter
the recovery boot set or provide new evidence about the KMS failure.

## Release gate

Packaging is deliberately deferred. A release requires a clean NetBSD 11.0 build, repeatable KMS boot, usable DRM/ioctl/mmap behavior, display recovery, and target-hardware acceptance. Only then may the project produce signed source/binary installer archives (.tgz, .tbz, .txz) and pkgsrc/pkgin metadata.

## 2026-10-15 source-only continuation (isolated development branch)

Development branch: `work/hp-native-drm-stage-replay-20261015`,
based on `main@27fd4d7d483be456158884c08d04446dd5312326`.
The HP native compiler-argv replay source test ran on Legion and PASSed;
a new recursive symbol-owner provider scan test independently ran on
Legion and PASSed (nested objects, de-duplication and symlink exclusion).
These are host-independent Python tests, **not** NetBSD object/kernel builds.

The native `fd_clone()` contract from frozen NetBSD
`03d918f6d0e81fa05b8f1160eca0628ad39988a6`
returns `EMOVEFD` unconditionally after `fd_affix`. The existing
`KASSERT(error == EMOVEFD)` in DRM native open is consequently not an
identified panic cause and was **not changed**. Native DRM close has
a separate task-context/lifetime concern (see
`docs/HP_DRM_FILE_LIFETIME_AUDIT_20261015.md`), but the corresponding
Linux-file callback provider and quiescence contract must be checked on
HP before implementing a guaranteed final-close path.

The full 323-unit i915 + DRM/TTM build closure, actual symbol-owner audit,
NetBSD kernel link, independent early-console transport, and hardware
KMS/black-screen recovery remain **OPEN**. Neither kernel nor firmware,
display MMIO, boot menu or host network was modified. No test kernel
was installed or rebooted. Current HP boot identity is unverified.

## 2026-10-16 native file bridge stage prerequisites

- Current source-only continuation branch `work/hp-native-drm-stage-replay-20261015`: native
  three-unit replay now requires all four NetBSD-specific bridge
  headers in the explicit staged include paths and follows compiled
  objects with a separately recorded `ld -r` partial link.
- Host-independent Python tests of argument replay and new header/link
  command gate **PASSED** on Legion. Native C/ELF execution still HP-only.
- Frozen NetBSD's `linux/file.h` does not supply the imported Linux
  `fput` contract; bridge owners and `drm_native_close` final-release
  lifecycle are **OPEN**.
- Hardware, source tree on HP, kernel, firmware, recovery and boot
  configuration have **NOT** been changed or freshly checked.

## 2026-10-16 native archive provider audit

`tools/audit_hp_native_drm_symbol_owners.py` separately reports
relocatable native `.o` symbols and *unlinked candidate* definitions
from recursively discovered NetBSD `.a` archives, with path confinement
and input bounds. These archive members must still be proven extracted
and valid in the HP kernel ABI. The archive discovery Python regression
passed on Legion; the real NetBSD `nm` run remains HP-only and OPEN.
SSH via Legion to `andreas@10.1.0.44` was reached but publickey
authentication was refused; the rejected attempt was not repeated and
no credentials or host settings were modified.

## 2026-10-16 all-323 direct header include closure

Read-only frozen-reference audit on Legion scanned all 323 active i915 C
units and their exact structural coverage rows. 215 distinct direct
linux/drm/uapi header names observed: 150 same-path NetBSD DRM plus
common LinuxKPI root matches, 65 unmatched, referenced by 140 active units. Also recorded 553 distinct
local quote-style includes. These are structural source gaps only, not
65 proven missing APIs. See docs/I915_DIRECT_INCLUDE_CLOSURE_20261016.md
and tools/audit_i915_direct_include_closure.py with regression test.
All 323 per-unit ABI, semantic and lifecycle acceptances remain OPEN.

## 2026-10-16 NetBSD LinuxKPI iopoll adapter candidate

New BSD-licensed isolated Linux API polling adapter in
`compat/native-runtime/iopoll/include/linux/iopoll.h`.
Host C mock regression `tests/test_i915_netbsd_iopoll_contract.py`:
14 positive/negative timeout and accessor cases PASS on Legion, not
HP-native compile. The candidate addresses a direct header-path gap in
19 of 323 pinned Linux i915 units, including CHV/VLV CDCLK readiness.
Pinned NetBSD `ktime_get` exists, `ktime_compare` does not.
NetBSD `usleep_range` is DELAY (busy wait); native sleep/IRQ fairness
and complete i915 driver runtime ABI remain OPEN. Kernel/boot unchanged.

## 2026-10-16 atomic iopoll LP64 delay fix

The isolated adapter's two atomic udelay call sites previously
narrowed unsigned-long Linux delay arguments to NetBSD unsigned-int
and could truncate on LP64. New bounded 1ms slicing helper prevents
this, while CHV-sized delays remain unchanged. Host mock 14-case
regression plus separate 2501us and UINT_MAX+1 long-delay tests
PASS on Legion. No native NetBSD kernel compile, install or KMS boot.

## 2026-10-16 CDCLK/GMBUS source-pinned C polling proof

323 active source units: 32 normal iopoll invocations and one
atomic invocation; native generic readl wrappers not used at these
C-level call sites and their MMIO provider owners remain UNVERIFIED.
Pinned CHV CDCLK 500us/50ms and GMBUS 2us atomic→50ms fallback
source-hash checked. Five additional C-host mock cases PASS; no NetBSD
kernel link, physical modeset, or hardware MMIO proof.

## 2026-10-17 parent callback provider closure gate

A source-only fail-closed parent-interface auditor now validates all 323
active Linux C units, all 16 parent provider assignments, all four
independent callback functions, 95 declared struct methods and 94
initialized provider methods. The only omitted method is NULL-guarded
fb_pin.reuse_vma. CHV IOSF get/put/read/write all have Linux providers.
Four adversarial missing-owner/probe-order regression tests pass.
Provider source owners and hashes are reported to per-run JSON.
This does NOT prove NetBSD ABI, callback bodies, kernel link or KMS.

## 2026-10-17 CHV IOSF enum lock-mask translation contract

Pinned modern Linux VLV IOSF enum has 9 units (includes DPIO_2 at
index 4) while frozen NetBSD `intel_sideband.h` has 8; old
`intel_sideband.c` is an active partial transport provider despite
no same-basename `vlv_iosf_sb.c`. Directly passing Linux PUNIT
BIT(8) to the NetBSD BIT(7) legacy lock protocol is incorrect.
New isolated BSD-2-Clause enum/lock-mask translator has source-hash
checks and host-C -Werror regression rejecting unsupported DPIO_2;
no IO register changes. NetBSD old write discards status, old
sideband has no modern locked_unit_mask; these must still be ported.

## 2026-10-17 source-derived CHV IOSF transaction/status patch

On branch work/hp-native-drm-stage-replay-20261015, a tested isolated
C route/transaction contract and a **native NetBSD source patch
candidate** for `intel_sideband.c/.h` are now published. Route/opcode
values are pinned and matched to both Linux and NetBSD register sources.
The existing NetBSD static int `vlv_sideband_rw` already reports
-EAGAIN/-ETIMEDOUT, but its legacy void write wrapper discards status.
The patch provides a checked accessor while preserving the void ABI.
Regression tests retrieved from the published GitHub branch PASS on
Legion: host-C -Werror and exact native diff apply to frozen source
with six status/error cases. This is *not* applied to HP NetBSD,
has no kernel-native compiler/link validation, no sb_lock runtime
ownership proof, and does not make DPIO_2 or the 323-unit i915
DRM/GEM/UVM/TTM graph functional. See
docs/I915_VLV_IOSF_CHECKED_NATIVE_PATCH_20261017.md.

## 2026-10-17 actual HP native 323-unit compiler checkpoint

Verified over strict Legion -> andreas@10.1.0.44 SSH: HP NetBSD 11 amd64
actually boots F77; no kernel processes, compiler/nbconfig/linker present.
Pinned old-NetBSD intel_sideband.c with both work-branch checked-status and
modern-IOSF-guard patches compiled on the actual HP NetBSD kernel toolchain
with -Werror: intel_sideband.o 348304 bytes, SHA256
94ce1b608b3f7fae444c9e40c9ab324acbe4dc619756b547d6bff3bb9f0cfda8.
Scratch path: /home/andreas/projects/i915-iosf-netbsd-native-04a97b3-20261017.

HP historical /root/i915-full-port-work has 425 Linux i915 C files, 961
uncommitted modifications: DIAGNOSTIC input ONLY, not release-ready i915.
Its 323 selected modern C rows were merged with ORIGINAL NetBSD
i915drmkms/intelfb device definitions and native glue, replacing 150
legacy i915 C rows. Real native nbconfig PASS (exit 0) and generated
Makefile contains modern i915_driver.c and vlv_iosf_sb.c. Private stage:
/home/andreas/projects/i915-323-native-nbconfig-20261017.
First dependall failure: missing sys/../common fixed via private symlink
to /usr/src/common. Second real native dependall EXIT 2 at
drm/display/drm_dp_dual_mode_helper.h missing. Linux/NetBSD same-name
DP helper headers have DIFFERENT signatures (drm_device context and
LSPCON timeout), so a blind header alias is NOT a functional repair.
Logs/native-build-status-v2.json retained on HP. No final i915 kernel
link, install, new boot, physical KMS or recovery-console verification.
F77 remains in use with genfb0 and i915 disabled; no out-of-band
G01–G09 early-console connection demonstrated.

## 2026-10-26 F17 CHV signal-level PHY source gate

On `work/hp-f17-chv-signal-phy-caller-20261026`, the three-file
F17 candidate keeps F16 explicit DPIO access and migrates only
`chv_set_phy_signal_level()` from pipe routing to physical
port routing (B/C -> PHY0, D -> PHY1). All four patch hunks have
been independently matched against the complete pinned NetBSD
original files in memory. The F16 provider files agree byte-for-byte;
nine PHY reads, nine PHY writes and the exact C fixture checksum agree.

A new pinned-tree `git apply` / file-scope / caller-isolation source
regression was committed and added to the common source runner with
the existing F16/F17 GCC-model suites. The CI sparse checkout now
includes `intel_sideband.h`. The **new Python source gate is NOT_RUN**
in this session (no checked-out pinned NetBSD tree available);
the independent in-memory hunk comparison is PASS. Hosted CI remains
quarantined. No native NetBSD object/link, HP KMS, or MMIO test is
claimed. See `docs/HP_I915_F17_SIGNAL_PHY_SOURCE_GATE_20261026.md`.


## 2026-10-27 executed F16/F17 and F15+F17 integration gates

On Legion, F16 and F17 exact-source C11 -Werror/UBSan model regression
suites completed under both GCC and Clang: **28/28 PASS** total.
All three F17 original NetBSD source blobs were verified by Git blob SHA-1;
native `git apply --check` plus `git apply` passed in isolated scratch
directories. The published
`tests/test_f17_chv_signal_patch_application.py` also PASSed in explicit
`--verified-blob-dir` mode, with no Git HEAD assertion.

A newly published `tests/test_f15_f17_source_composition.py` PASSed
on all **six exact original NetBSD source blobs**. F15 then F17 and
F17 then F15 both applied cleanly using actual `git apply` and produced
byte-identical source results. F15 includes F14's original two display
hunks and supersedes it; only **F15 + F17**, not F14 + F15 + F17,
is the proper combined candidate. The common source runner invokes
both gates and CI's sparse list includes `gt/intel_rps.c`.

This is source-only host verification. Strict pinned-NetBSD-checkout
test modes and native NetBSD kernel object compilation/link remain
**NOT_RUN**. GitHub Actions remains quarantined; negative corruption
replay was blocked by a tool safety check and is **NOT_RUN**.
HP KMS, live DPIO registers and G01-G09 serial transport are still OPEN.
No F77 recovery kernel, kernel install, firmware, or boot configuration
was modified. Details: `docs/HP_I915_F17_SIGNAL_PHY_SOURCE_GATE_20261026.md`.
