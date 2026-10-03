# Cherryview/Braswell i915 validation checkpoint — 2026-10-04

Status: HOST-REGRESSION-VERIFIED / NATIVE-NETBSD-BUILD-OPEN / HP-RUNTIME-OPEN
Canonical project `main` observed: `b8101ecc54bf8f8970f44937bdcfaf40ecc26a52`.
Independent historical Legion checkout: `d8ba08c2694a61f2df03337f946e26c7bfd99074`; clean at inspection, not synchronized, promoted, or mutated.

## Exact file provenance

Local `tests/test_vlv_chv_audio_phase.py` matches the current GitHub `main` blob `fc7ad19486cccc877f40d0b995afd0bf237ccd42`. Its generator `tools/generate_vlv_chv_audio_phase_patch.py` matches blob `04905297af7b56fd93fb180bbede93fa1ed023ce`. The older local `tests/test_early_probe_unwind.py` does NOT match the current published test (`f742412108effe6df2d4c8e3d1975d846cbb358c` vs `1a9a2ed102ea1ee8848c1d40e3ca15bac12877f4`); it is NOT treated as current source-identical test evidence.

## Actually executed test

On Legion, `python3 tests/test_vlv_chv_audio_phase.py` returned exit **0** and emitted:
- `I915_AUDIO_PATCH_OK files=2 NetBSD=03d918f6d0e81fa05b8f1160eca0628ad39988a6`
- `I915_AUDIO_PHASE_OK: DP/HDMI audio after port setup; no-audio safe`
- `I915_AUDIO_PATCH_BYTE_MATCH_OK`

This is a targeted host-level regression against the staged/pinned source and the published test/generator, **not** execution of a native NetBSD kernel object or end-to-end display/audio initialization. Legion was running Linux and had no `nbmake`, `nbmake-amd64`, `nbconfig` or `amd64--netbsd-gcc` in PATH at inspection.

## Unresolved parent scope

The 323-active-Linux-unit/DRM/TTM and NetBSD dependency/semantics coverage remains open under `docs/FULL_SCOPE_CONTRACT.md`. The six-edit NetBSD/i915 overlay, historical recovery F77 and failed F82 candidate remain unchanged. Do not initiate a target kernel installation/boot on the basis of the host regression. The separate, previously denied combined Legion hash probe and any denied source update are not retried by this checkpoint. The central `Agent-Governance/LAST_TASKS.md` synchronization remains blocked/out of sync; this report is explicitly a subordinate project-local record.
