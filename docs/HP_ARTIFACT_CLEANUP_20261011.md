# HP artifact cleanup record — 2026-10-11

## IST

- The live HP TPN-W121 system is still F77:
  `NetBSD 11.0 (RTWN8723BE-F77-LINUX-EFUSE-MAP) #0: Sat Sep 26 19:13:52 CEST 2026`.
  Its kernel file is
  `/netbsd.v1-f77-linux-efuse-map-20260926`, not `/netbsd`.
- The checked boot configuration has SHA-256
  `aaf16e4c185f59e925ab8cff9aaf1d45545896ab84a5cf46ddcb3d3c85ba6b1f`.
  It names only the F77 kernel and `/netbsd` (F16.2 recovery); all menu
  entries keep `i915drmkms` disabled. It contains no F16.0, F83, or F84
  token.
- There are 93 regular root-level `/netbsd*` files. The three protected
  files are listed in the manifest; the remaining 90 exact paths are deletion
  candidates. Their total size is 7,282,422,471 bytes. The sorted candidate
  path-list SHA-256 is
  `1b255abeeeb716ec26fba1d846b01dbc11fae434014b074567a6441d083afe96`.
- The pre-delete candidate audit is represented by the 90 candidate rows in
  [the TSV manifest](manifests/HP_ARTIFACT_CLEANUP_20261011.tsv). Its corrected
  path/size/SHA-256 stream hashes to
  `8f5f94a2d7f2d5886c9b1685c10a08ee8bdb63340d922a452d9f0a149a8220f8`.
  One root-owned candidate required a root-only hash read; its value is recorded
  in the TSV.
- Three i915 source backups are byte-identical to an explicitly retained
  counterpart. All other i915 backups, in particular `intel_fbdev.c.orig`,
  remain outside this cleanup.

## ÄNDERUNGEN

- This commit creates a tracked, hash-pinned preflight manifest before any
  deletion. It neither changes a boot entry nor installs, boots, or modifies a
  kernel. F16.0, F83, and F84 remain excluded from testing.
- The only authorized source-backup removals are:
  - `i915_params.h.pre-bsw-displaytest` and
    `i915_params.h.pre-f80-display-off-20260929`: each 3,553 bytes and
    byte-identical to current `i915_params.h`
    (SHA-256 `fff4f1b3ba82fa71c2d71797b8fd5f1ebd89fce59eac2d18672e9a9b2a2df0d4`).
  - `display/intel_dp.c.pre-i915-diag-20260927`: 220,222 bytes and
    byte-identical to the retained
    `display/intel_dp.c.pre-chv-audio-port`
    (SHA-256 `da6f6fa3ddc62c6f99891e996cd10ce4ffa4caa788d186db91a219cd69875bc1`).

## NEXT

1. Commit and push this exact preflight manifest before deleting any file.
2. Recheck every TSV row against the live HP filesystem, including the three
   protected kernel identities, the boot configuration hash, candidate count,
   path-list hash, and the three backup equality checks.
3. Remove only the verified candidate paths and the three listed backups,
   using absolute individual names with root authority; do not use a glob or a
   recursive source-tree deletion.
4. Recheck the protection set, `/boot.cfg`, and free space after deletion, then
   add the postflight result to this record.
