# i915 Cherryview/Braswell NetBSD status

Date: 2026-10-14

## State

**Diagnostic recovery only — not a functional i915drmkms release.**

Target hardware is the HP TPN-W121 with Intel Cherryview GPU 8086:22b1 (revision 0x35) on NetBSD 11.0 amd64.

The historically verified recovery kernel is RTWN8723BE-F77-LINUX-EFUSE-MAP.
It disables i915drmkms and retains the firmware framebuffer. Current governance
also records a later request for a GENERIC default; current HP boot identity
is unverified. Preserve F77 and do not infer or change the current boot default.

## 2026-10-14 safe source/build hardening

Isolated branch `work/i915-hardening-20261014` starts at current `main`
`27fd4d7`. The four full-graph/native-DRM tools now take explicit stage paths;
the old root stage is not an operational fallback. Preflight checks exact
323 i915 + 66 DRM + 8 display + 13 TTM selections, real config(5)
ALLFILES/OBJS owners, source/config/tool/header identity and generated ABI
headers. The owner audit requires fresh, matching native object evidence,
reports unresolved imports and duplicate strong owners, and keeps lexical
candidates separate. Existing three-object links cannot close the full graph.

The native DRM read adapter receives defensive checked-size and centralized
whole-event-progress guards. Existing open/minor/fd/task cleanup and copy-fault
rollback were reviewed; no proven KMS/root-cause fix or native ABI pass is claimed.

Actual local Python-only validation: 30 gate/owner negative controls, four
DRM source contracts, runner scope check and syntax checks of 90 Python files
PASS. See [hardening and reproduction](docs/I915_SAFE_HARDENING_20261014.md)
and [test evidence](docs/evidence/I915_LOCAL_HARDENING_FINAL_20261014.json).
The complete pinned source runner and changed NetBSD C compilation remain
NOT_RUN. HP SSH timed out directly and through Spinnennet and Legion; RDC
reported exhausted quota. No kernel/boot/MMIO/firmware changes or paid/hosted
build resources were used. Complete kernel link, ABI/semantic closure,
physical early trace and KMS acceptance remain OPEN.

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
