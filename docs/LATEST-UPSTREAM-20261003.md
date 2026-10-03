# 2026-10-03 latest-upstream comparison: i915 Cherryview / NetBSD 11

Status: SOURCE COMPARISON / PARTIAL — not a reference rebase, complete port, native build or hardware acceptance.

## Exact reference authority

- Project's frozen Linux reference: `torvalds/linux fd179f8a05be3ccae366b9b96e176b51fbe54aab`.
- Newest published stable Linux verified on 2026-10-03: `v7.2.8`, released 2026-09-25; `gregkh/linux` stable tag `v7.2.8`. The newer `v7.3-rc5` is a release candidate, not the latest stable.
- NetBSD target: 11.0 amd64; frozen project source baseline `NetBSD/src 03d918f6d0e81fa05b8f1160eca0628ad39988a6`. Do not silently change either project pin because a newer release exists.
- `i915_pci.c` is **byte-identical** in frozen Linux and stable Linux v7.2.8: Git blob `2f03f95945f1b9a243a61db163576d0071d53e9c`. Both identify CHV as Gen8 LP and set `__runtime.ppgtt_type = INTEL_PPGTT_FULL`, `__runtime.ppgtt_size = 32`. The older Linux `v7.2` tag has a different blob `82415af47d54088bb01e8eafc3079acf1c911dcb` and lacks a later `if (!intel_info) return -ENODEV;` guard, so blindly using the base v7.2 release would regress this guard.
- This is a **single-file** source-diff result. The other 322 frozen active i915 C units, generated headers, DRM/TTM and LinuxKPI dependency closure, current stable v7.2.8 change set and newer mainline changes have not been established as equal. The full-driver coverage and native NetBSD compilation remain OPEN.

## Firmware and platform

- Latest published `linux-firmware` release observed: `20260916`. The project previously established that Gen8 Cherryview is not eligible for later-generation i915 GuC/HuC/DMC selections and found no CHV-specific firmware to load; the latest release's individual `i915/` blobs have not been exhaustively inspected at this checkpoint. Never substitute Broxton (BXT) or other generation firmware without a hardware-ID and loader-protocol match.
- Preserve historical recovery F77 and the independent six-edit dirty NetBSD port overlay. Legion's i915 project checkout remains at `d8ba08c2694a61f2df03337f946e26c7bfd99074`, behind canonical GitHub `main e446a48d54b171333636bc478b8038242fa6f894` at the beginning of this audit.
- The local `test_early_probe_unwind.py` hash `f7424121...` does **not** match current GitHub `1a9a2ed1...`; the local `test_vlv_chv_audio_phase.py` and generator match canonical `fc7ad194...` and `04905297...`, but a follow-up local patch hash verification was externally safety-denied before a usable result. No i915 test or source synchronization was executed by this checkpoint; do not reroute the blocked hash/sync operation.
- HP direct Desktop Commander agent is offline in the current inventory; current target boot/kernel is UNKNOWN. No reboot, installed kernel, boot configuration, build or overlay mutation was performed.

## Next allowed dependency-ordered work

1. Enumerate and diff the **full** relevant v7.2.8 and mainline active build closure against the frozen 323-unit pin, then intentionally approve/pin any source revision upgrade and rerun generator tests. Do not treat the one-file identity above as whole-driver currency.
2. Reconcile candidate PPGTT 0016/0017 with canonical GitHub and unpublished target overlay only through a legitimately available ordinary synchronization/test route, preserving local dirty files and exact source hashes.
3. Close native NetBSD type/ABI/API, object, link and integration gates before constructing a selectable kernel. Retain F77 rescue and rollback; no full-scope runtime or `COMPLETE` claim before contract validation.

References: https://www.kernel.org/ ; https://github.com/gregkh/linux/blob/v7.2.8/drivers/gpu/drm/i915/i915_pci.c ; https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/i915_pci.c ; https://www.netbsd.org/releases/ ; https://gitlab.com/kernel-firmware/linux-firmware/-/tags/20260916
