# HP i915 F17 — Cherryview signal-PHY source integration gate (2026-10-26)

## Scope

Source-only candidate on `work/hp-f17-chv-signal-phy-caller-20261026`.
The published patch is
`patches/candidates/netbsd-11-chv-dpio-signal-phy-consumer-20261026.patch`.
It combines the F16 explicit-PHY DPIO provider with the port-based
`chv_set_phy_signal_level()` caller in exactly three NetBSD paths:

- `sys/external/bsd/drm2/dist/drm/i915/intel_sideband.c`
- `sys/external/bsd/drm2/dist/drm/i915/intel_sideband.h`
- `sys/external/bsd/drm2/dist/drm/i915/display/intel_dpio_phy.c`

All other legacy pipe-based DPIO callers are unchanged by this candidate.

## Direct independent pinned-original review

Reference NetBSD commit: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

Verified original Git blob IDs:

- `intel_sideband.c`: `1cc6a956b90cc44a85fa153ea1aa9ba58a605eed`
- `intel_sideband.h`: `ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea`
- `display/intel_dpio_phy.c`: `9029d10774992a62a3f2ac84bb8a37f724360442`

An independent line-exact in-memory unified-diff application matched all
four F17 hunks against the **complete** fetched NetBSD original files
(one sideband-C hunk, two header hunks, one display caller hunk).
The F16 provider outputs matched the corresponding F17 patched sideband
files byte-for-byte. The patched F17 function matched the exact
`tests/test_f17_chv_signal_phy_source.c` fixture and its FNV64
`0x25d4c36ad02b2783`. It contains nine PHY reads and nine PHY writes.

This independent verification is a full-original *in-memory* patch review,
**not** a recorded native `git apply` execution on a checked-out pinned tree.

## Newly published reproducible gate

`tests/test_f17_chv_signal_patch_application.py` requires a git checkout
of the exact pinned NetBSD commit and checks:

1. Complete original Git blob identities for all three paths.
2. `git apply --check --whitespace=error` and real `git apply` in
   separate, disposable scratch trees for F16 and F17.
3. Exact patch path scopes (F16 two files, F17 three files) and
   byte-identical F16/F17 sideband-provider outputs.
4. No display changes outside `chv_set_phy_signal_level()`.
5. Exact published C fixture parity, checksum, nine PHY reads/writes,
   port-driven PHY selection, and preserved DPIO get/put boundary.

Reproduction from the project checkout:

```sh
python3 tests/test_f17_chv_signal_patch_application.py \
  --netbsd-tree /path/to/pinned-netbsd-src
CC=gcc python3 tests/test_f16_dpio_phy.py
CC=gcc python3 tests/test_f17_chv_signal_phy.py
CC=clang python3 tests/test_f16_dpio_phy.py
CC=clang python3 tests/test_f17_chv_signal_phy.py
```

The normal pinned-source runner now invokes both existing portable
C mutant suites and the new full-source F17 test. The GitHub Actions
NetBSD sparse checkout now includes `intel_sideband.h`.

## Verification limits / release hold

- Independent full-original in-memory F17 hunk review: **PASS**.
- New pinned-tree Python `git apply` source gate: **NOT_RUN in this session**;
  the pinned NetBSD checkout is not available in the present execution environment.
- Previously reported F17 GCC/Clang 7/7 portable C mutant suites:
  **not independently rerun in this session**.
- GitHub-hosted CI: **quarantined**, no new job PASS claimed.
- NetBSD native objects / kernel link: **NOT_RUN**.
- HP Cherryview/Braswell KMS, DPIO MMIO, display recovery: **NOT_RUN**.

No production kernel, firmware, bootloader, or device register was modified.
An actual native build and the G01–G09 early-console trace gate remain
prerequisites before any new HP hardware-boot attempt.
