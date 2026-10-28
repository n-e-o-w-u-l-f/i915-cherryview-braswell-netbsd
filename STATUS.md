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


## 2026-10-27 F17 native-source follow-up — strict checkout gate CLOSED

Legion fetched a real sparse NetBSD/src Git checkout with HEAD
`03d918f6d0e81fa05b8f1160eca0628ad39988a6`. Both original
F17 and F15+F17 `--netbsd-tree` test modes now PASS (previous
NOT_RUN status superseded). Additionally, the actual patched
`intel_sideband.h` passed host GCC/Clang under GNU99/GNU11
with both enum declaration orders: 8/8 -Werror compiler configurations.
The exact original NetBSD `i915_drv.c` and `i915_reg.h` prove the
Cherryview DPIO IOSF PHY0/PHY1 mappings are initialized in early
probe after `sb_lock` and before display setup. The new test
rejected four independent wrong-order/mapping/index mutations.

The previous checked-status native IOSF adapter and modern guard
also compose with F17 as either checked -> modern -> F17 or
F17 -> checked -> modern; actual pinned-original git apply
succeeds and resulting three files are byte-identical. All
five F17/F15 source gates were added to the common pinned-source
runner; the F16/F17 host C mutant suites remain GCC/Clang 28/28 PASS.

**Gate distinction:** No native NetBSD C object/kernel compile or
hardware test was performed. Linux-host mock-header builds and
source patch applications do not replace NetBSD kernel compilation.
The independent G01–G09 trace and HP F77 recovery restrictions remain
in force. See
`docs/HP_I915_F17_SIGNAL_PHY_SOURCE_GATE_20261026.md`.

## 2026-10-27 F18 HP option-5 vpanic — hardware regression triage OPEN

Owner physically attempted boot-menu option 5 and observed a failing kernel
stopping in vpanic. The literal panic string, DDB trace, selected kernel
image and live menu config have **not** been retrieved. Do not conflate
the test kernel with the source-only F17 branch. The last documented
live F77 boot.cfg on 2026-10-11 and the uninstalled four-mode staging
do not identify a fifth active menu entry.

NetBSD pinned sys/dev/cons.c shows an established independent failure
class: cnopen panics when cn_tab exists but cn_dev == NODEV and
NNULLCONS == 0. Historic F81 and a NetBSD i915 problem report exhibit
the same console ownership problem; **not yet proved for option 5**.
The exact panic string and trace decide between a console/DRM handoff,
actual i915 assertion, UVM fault or unrelated subsystem error.

New tools/hp_boot5_vpanic_readonly.sh (live F77 only or offline
--config mode) captures literal fifth menu command, safe image identity,
firmware/mount provenance and surviving crash filenames with no writes.
tests/test_hp_boot5_vpanic_readonly.py PASSes 6 parser scenarios
including the dangerous NetBSD boot flags/image order, symlink and
non-NetBSD refusal (executed with host POSIX sh). Source-level findings
and DDB read-only evidence instructions are in
docs/HP_BOOT5_VPANIC_TRIAGE_20261027.md.

**Next action:** obtain option 5 image/menu source and actual
panic message + first non-panic stack frame from owner evidence.
No new graphics kernel boot, suppression of cnopen panic, reboot,
installation or F77 modification is authorized by this result.


## 2026-10-27 F18 genuine NetBSD console-handoff instrumentation

Owner-observed boot entry 5 `vpanic` remains an **OPEN physical failure**:
exact panic text, DDB trace, loaded image and active UEFI/BIOS menu
source remain unknown. Further boot attempts are on hold.

Actual pinned NetBSD 11 console-chain audit of `intelfb.c`,
`drmfb.c`, `genfb.c`, `wsdisplay.c`, and `cons.c`
identified a specific failure window: `genfb_attach` can invoke
`wsdisplay_cnattach` (which leaves `cn_dev=NODEV`) without
checking whether a subsequent `config_found` actually created
the wsdisplay child which assigns the real console device number.
If this occurs, a later `cnopen` may panic. **This window is proven
in pinned code; its reachability for boot entry 5 is unproven.**

New isolated *actual NetBSD C patch candidate*
`patches/candidates/netbsd11-f18-i915-console-handoff-trace-20261027.patch`
adds seven compile-time guarded `HP_I915_CONSOLE_TRACE` markers
covering intelfb → drmfb → genfb → wsdisplay → return. No functional
changes when the macro is absent. Real scratch `git apply` from
the four exact pinned original Git blobs and exact reversal of guarded
regions PASSed on Legion:
`F18_PINNED_4_NETBSD_FILES_7_TRACE_MARKERS_NO_BEHAVIOR_DIFF_PASS`.
`tests/test_f18_console_handoff_trace_source.py` now owns this gate.
No NetBSD object/kernel build or live HP experiment was undertaken.
F77, firmware, actual boot menu and recovery hashes were not touched.


## 2026-10-27 F19 — functional NetBSD DRMFB console preflight candidate

On this separate F19 development branch an actual one-function native
NetBSD candidate now protects the VGA console from an avoidable takeover:
drmfb_attach checks for a matching configured wsemuldisplaydev
console child via config_search under KERNEL_LOCK before calling
vga_cndetach/disable VGA. If the child is absent, it returns ENXIO,
and the existing intelfb_attach_task error/unwind path handles it.
Normal successful VGA/framebuffer ownership order remains unchanged.

New patch:
patches/candidates/netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch

Actually executed on Legion with the REAL pinned NetBSD Git checkout:
- Real git apply --check and git apply to exact original drmfb.c.
- Source-accurate extracted C compiled/executed with GCC and Clang,
  GNU99/GNU11, NVGA=0/1, -Werror and UBSan: **64/64 PASS**.
- Inverted null-check negative mutant failed as required.
- F18->F19 and F19->F18 full-source patches applied via real
  git apply and produced byte-identical output (four pinned files).
- New checks wired into the pinned source runner, with CI sparse
  checkout additions. GitHub-hosted Actions remains quarantined.

**LIMITS:** Only a missing MATCHING CONSOLE CHILD is checked. A child
can still fail attach after search; previously preattached console
state, bad CRTC/eDP/AUX or unrelated panic sites are not fixed.
Most importantly, the physical HP boot-menu 5 vpanic message,
backtrace and candidate kernel identity are still UNOBSERVED.
This patch has not been compiled by the native NetBSD kernel toolchain,
linked into a kernel or tried on HP. F77, existing kernel images,
firmware and boot.cfg are unchanged. Do not boot F19.

Detailed review:
docs/HP_F19_DRMFB_CONSOLE_PREFLIGHT_20261027.md


### 2026-10-27 F19: complete patched native function now host-compiled

The new tests/test_f19_complete_drmfb_attach_host.py applies F19 to
the entire pinned original NetBSD drmfb.c, extracts the whole genuine
drmfb_attach() function without modifying its body, mocks only the
external NetBSD/DRM APIs and compiles/runs the complete extracted function
with host GCC/Clang, GNU99/GNU11, NVGA=0/1, -Werror and UBSan.
**256/256 cases PASS**, including positive/negative console ownership,
fallback firmware/genfb detection, missing-child rejection and
successful genfb attach with balanced locking. Runner wired. The
existing 64-case exact preflight-block suite, inversion mutant and
two-order F18+F19 git-apply composition continue to pass.

Source review additionally confirmed that a drm_fb_helper with
no CRTC/sizes already fails upstream with -EAGAIN, so no speculative
dimensions guard was introduced. Still **NOT_RUN**: compilation of a
complete drmfb.o against native NetBSD kernel headers, kernel link,
menu entry 5 image/panic capture and HP hardware boot. F77 remains
untouched. See docs/HP_F19_DRMFB_CONSOLE_PREFLIGHT_20261027.md.


## 2026-10-27 F20 — x86 firmware console return-zero defect and earlier i915 gap

In the exact pinned NetBSD 11 original x86_genfb_cnattach():
-1 means defer, 0 means unsuccessful GOP framebuffer setup, 1
means successfully preattached wsdisplay. Original x86 consinit.c
treated result 0 as success, invoked genfb_cnattach and skipped
the VGA/text console fallback. The new one-file actual C patch
candidate F20 handles return 0 by continuing the existing
fallback; successful and deferred paths are unchanged.

Candidate:
patches/candidates/netbsd11-f20-x86-genfb-early-fallback-20261027.patch

Executed on Legion against the real pinned NetBSD source: 7
exact original Git blobs checked; real git apply (check + apply)
to the entire consinit.c; exact native console branch compiled
and executed with GCC and Clang GNU99/GNU11, -Werror and UBSan,
9 cases per build = **36/36 PASS**. The original unfixed code
and a broadened success-guard mutant both FAILED the same
executable check as expected. Runner and workflow sparse
manifest now include F20.

A separate source-proven F19 scope gap remains: UEFI
wsdisplay_preattach can hold cn_dev=NODEV; NetBSD PCI i915
priority 6 beats firmware genfb priority 5; deferred
i915_driver_probe failure can return before intelfb attaches
a console, so downstream F19 preflight is never executed.
**F20 does not resolve this i915 probe failure**; further
console ownership remediation must follow actual HP panic
image/string and stack evidence.

Docs: docs/HP_F20_UEFI_GOP_CONSOLE_SOURCE_AUDIT_20261027.md.
Native NetBSD object compile/kernel link/HP boot all NOT_RUN.
Boot-menu option 5 image/panic reason still unknown. F77 and
installed kernel/boot configurations remain unmodified.


## 2026-10-28 F21 – i915 deferred probe error-state repair

Source-pinned, functional candidate added in
`patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch`.
The original deferred i915 probe sets `sc_task_thread = curlwp` and
returns on probe error without clearing it. F21 clears this stale
owner **only if** the synchronous task queue is empty; no callback
is discarded or executed on the nonempty-queue path.

Actual Linux Legion gate: original NetBSD Git blob SHA verified, real
`git apply --check` and `git apply` pass, byte-identical remaining
source, source-extracted error branch compiled and executed with GCC
and Clang in empty/nonempty queue cases:
`F21_PINNED_GIT_APPLY_TWO_COMPILERS_EMPTY_ONLY_STATE_REPAIR_PASS`.
New test added to pinned-source runner.

**Not a console restoration:** i915 PCI match priority 6 can
supersede genfb PCI priority 5; failing deferred i915 probe can
bypass F19 `drmfb` and leave an early UEFI `wsdisplay` console
without a valid device. F20 fixes a separate GOP return-value bug.
The HP menu-5 panic string/image/stack remain missing. Native NetBSD
kernel compilation, installation and HP boot are NOT_RUN. F77 and
all on-disk boot states untouched. See
`docs/HP_F21_I915_PROBE_ERROR_STATE_20261028.md`.


## 2026-10-28 F22 – opt-in native UEFI genfb console fallback after i915 probe error

F22 is a NEW, separately gated functional candidate addressing the early
UEFI GOP console failure gap left by F19/F20/F21. The patch changes the
native i915 PCI autoconf driver and device-configuration file, and
depends on F21's conditional empty-task-queue cleanup.

An explicit NetBSD config defflag declares HP_I915_FWFB_FAILOVER,
**OFF by default**. Only when enabled AND a deferred i915 probe fails
with an empty synchronous task queue does F22 attempt to complete
early wsdisplay preattach via an embedded, persistent genfb_softc
at offset zero of the i915drmkms device. It requires verified UEFI
32bpp properties, an existing framebuffer mapping and a matching
wsdisplay child; no bogus cn_dev is fabricated. Successful i915 probe
and nonempty queue branch are not changed.

F22 native C patch:
patches/candidates/netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch
Test:
tests/test_f22_i915_fwfb_failover.py
Full technical review:
docs/HP_F22_I915_UEFI_GENFB_FAILOVER_20261028.md

Actually executed on Legion: pinned original NetBSD i915 C/config Git
blob checks; real git apply --whitespace=error --check and git apply
of F21 then F22; compile-time-disabled F22 C path source-equivalent
to F21; exact extracted native F22 failover helper compiled/executed
with GCC+Clang, GNU99+GNU11, -Werror, UBSan, 20 cases each:
**80/80 PASS**. Pinned source runner includes the F22 test.
Hosted Actions were NOT run because of ongoing runner quarantine.

**CRITICAL:** No native NetBSD kernel object compile/link, no HP
menu-5 panic image/stack confirmation, and NO physical HP test.
Failed GPU probes can invalidate the old GOP framebuffer and
genfb_attach itself can still fail. DO NOT enable F22 or install a
kernel without independent checks. F77 and boot.cfg untouched.

## F23 – i915drmkms_attach_real integration regression (2026-10-28)

Production patches F21 and F22 unchanged. The entire F21/F22-patched original NetBSD i915drmkms_attach_real and F22 failover helper were compiled and executed with host GCC and Clang, GNU99/GNU11, F22 option OFF/ON, UBSan and -Werror (unused external mock stubs exempt in OFF variant). All 448/448 scenarios passed. A deliberately inverted native task-queue guard was rejected. Pending tasks are now simulated during i915_driver_probe rather than before attach. The earlier standalone F22 suite was rerun: 80/80 PASS.

Source/trace: tests/test_f23_i915_attach_real_integration.py and docs/HP_F23_I915_ATTACH_REAL_INTEGRATION_20261028.md.

Still NOT RUN: native NetBSD object/kernel build, physical HP boot and capturing the actual menu-5 panic/stack. F22 is disabled by default. F77 and HP boot files unchanged.
