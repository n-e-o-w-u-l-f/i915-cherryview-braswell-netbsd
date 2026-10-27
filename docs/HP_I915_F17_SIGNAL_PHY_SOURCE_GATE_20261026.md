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

## 2026-10-27 executed Legion follow-up

The F17 branch sources were freshly checked out on the Legion Linux development
host in an isolated /tmp directory; branch HEAD was checked against GitHub.
Host C11, -Werror, UBSan model suites were actually executed:

- F16 provider: GCC 7/7 PASS; Clang 7/7 PASS.
- F17 signal consumer: GCC 7/7 PASS; Clang 7/7 PASS.
- Total: 28/28 PASS across four suite/compiler runs.

The complete original C files were separately retrieved from pinned NetBSD
`03d918f6d0e81fa05b8f1160eca0628ad39988a6` and their raw Git blob SHA-1s
verified before use. The actual `git apply --check --whitespace=error` and
`git apply --whitespace=error` operations succeeded for both the F16 and F17
published patches in disposable directories. F16 and F17 sideband provider
files were identical; the displayed F17 signal function, fixture and all four
original hunks matched.

The newly published `test_f17_chv_signal_patch_application.py` was
executed successfully in its **explicit --verified-blob-dir mode**.
That mode checks exact Git blob identities but does NOT assert the presence
of the original NetBSD git commit in a checkout. The stricter
`--netbsd-tree` mode remains NOT_RUN this session.

### F14/F15/F17 canonical composition

A new `tests/test_f15_f17_source_composition.py` is in the branch and
wired into the common pinned-source runner. Its verified-blob mode
was actually run on Legion and PASSed:

- All six original NetBSD Git blobs verified against the pinned revision:
  `intel_sideband.c`, `intel_sideband.h`,
  `display/intel_dpio_phy.c`, `display/intel_display.c`,
  `display/intel_display.h`, `gt/intel_rps.c`.
- Real `git apply` succeeds for F15 then F17 **and** F17 then F15,
  with byte-identical outputs.
- F15's two display outputs equal F14's; F15 **supersedes F14**.
  Do not apply F14 then F15.
- F15 RPS/GPLL call sites, F17 nine PHY reads/writes and exact
  signal function were checked in the composed output.
- The CI sparse checkout now includes `gt/intel_rps.c`.

The attempted deliberate source-corruption negative run was not
executed because its remote execution request was blocked by
a tool safety check; this is NOT_RUN rather than PASS.

**Remaining gates:** actual pinned-checkout-mode Python tests,
NetBSD native C compilation of affected units, full selected kernel link,
GitHub-hosted CI (quarantined), an early-console G01–G09 trace and HP
Cherryview hardware KMS/black-screen validation. F77 boot recovery and
production firmware/kernel/boot settings were not touched.

## 2026-10-27 follow-up: pinned Git checkout and header/IOSF closure

The earlier NOT_RUN result for both strict Git-checkout modes is now **superseded**.
On Legion a sparse NetBSD/src checkout was fetched and checked out at the
actual `03d918f6d0e81fa05b8f1160eca0628ad39988a6` Git HEAD.
The following tests executed with `--netbsd-tree` and PASSed:

- `test_f17_chv_signal_patch_application.py`: full three-file/four-hunk
  F17 candidate, literal native C fixture, checksums and unchanged remainder.
- `test_f15_f17_source_composition.py`: six exact original files,
  F15/F17 two-order actual `git apply`, F14 supersession.
- `test_f17_sideband_header_compile.py`: full F17-patched original
  `intel_sideband.h` plus isolated mock system includes,
  host GCC and Clang with `-std=gnu99` and `-std=gnu11`,
  `-Wall -Wextra -Werror`; both physical-PHY enum declaration orders:
  **8/8 source-header compiler configurations PASS**.
- `test_f17_dpio_bootstrap_source.py`: actual pinned
  `i915_drv.c` and `i915_reg.h`, early `intel_init_dpio()`
  after `sb_lock` setup and before display initialization;
  CHV PHY0 -> IOSF_PORT_DPIO_2, PHY1 -> IOSF_PORT_DPIO;
  **four intentionally wrong in-memory variants all rejected**.
- `test_f17_iosf_patch_composition.py`: the earlier checked-status
  adapter and modern IOSF guard compose with F17 both as
  `checked -> modern -> F17` and `F17 -> checked -> modern`;
  both sequences apply cleanly to complete pinned source files and
  produce identical output bytes, preserving the native F17 caller.

These new tests are invoked by `tools/run_pinned_i915_source_checks.py`.
The existing CI workflow already checks out the relevant original
`i915_drv.c`, `i915_reg.h`, `intel_sideband.c/.h`,
`intel_dpio_phy.c`, `intel_display.c/.h`, and `gt/intel_rps.c`.

F16/F17 exact C model test suites were rerun GCC and Clang:
**28/28 tests PASS**. The project Git working tree was clean after
the test-only checkout update. All new scripts were compiled by
Python syntax verification as a separate host check.

**Still OPEN / NOT_RUN:** compiling the *actual* modified NetBSD
C units against NetBSD kernel headers and native compiler flags,
a fully linked selected NetBSD kernel, and a physically observable
HP KMS boot/early G01–G09 trace. Legion's installed compilers are
Linux host GCC/Clang, not a demonstrated NetBSD kernel cross-toolchain.
Mock-header compilation is not a native kernel object build.
GitHub Actions hosted execution remains quarantined.

No i915 production source in a NetBSD kernel worktree was committed,
no HP kernel or bootloader replaced, and the F77 recovery boot target
was not touched.
