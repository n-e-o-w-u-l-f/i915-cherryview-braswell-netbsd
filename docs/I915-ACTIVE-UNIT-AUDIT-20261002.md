# Pinned full-i915 active-unit audit — 2026-10-02

Status: STRUCTURAL/REVIEW-QUEUE EVIDENCE ONLY; NOT SEMANTIC PARITY OR TESTREADY.

## Immutable inputs

- Linux: torvalds/linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`.
- NetBSD: NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- Selected active Linux units: `i915-reference-stage-20261001/i915-active.filelist` (323 lines).
- Classifiers: `tools/classify_netbsd_i915_coverage.py`, then `tools/classify_i915_semantic_candidates.py`.
- Frozen Linux and NetBSD HEADs were read back on Legion and each tree's tracked files passed `git diff --quiet`.
- Generated intermediate JSON is a reproducible temporary audit, not authoritative project source.

## Structural results

| Class | Active Linux C files |
|---|---:|
| EXACT_ACTIVE_DIST | 136 |
| ACTIVE_OVERRIDE_OR_MOVED | 13 |
| PRESENT_NOT_BUILT | 7 |
| UNRESOLVED_NO_BASENAME | 167 |
| **Total** | **323** |

The 149 active NetBSD matches/overrides and seven non-built basename matches still require source-semantic, build-graph, API and lifecycle verification. Exact names do not establish equivalent hardware behavior.

## Review queue for the 167 unresolved source paths

| Candidate class | Files | Interpretation |
|---|---:|---|
| PARTIAL_FUNCTION_OVERLAP | 113 | Existing NetBSD functions cover part of the Linux symbol inventory; inspect each missing behavior and dependency. |
| NO_FUNCTION_OVERLAP | 28 | No matching extracted function names; establish whether a real target implementation or justified adapter exists. |
| ALL_FUNCTIONS_PRESENT_ELSEWHERE | 3 | Names are present elsewhere; verify ordering, side effects, error paths and build inclusion. |
| REFERENCE_INAPPLICABLE_CHV | 23 | uC/GSC/PXP implementation paths are predicate-inapplicable **for the HP Cherryview first target only**; generic whole-driver coverage remains open. |
| **Total** | **167** | No row is automatically PORTED or CLOSED. |

Selected dependency-first review candidates within PARTIAL_FUNCTION_OVERLAP:

- `i915_driver.c`: 35 extracted functions, 19 names matched in current NetBSD, 16 not matched. Review probe/early-probe and reverse unwinds before integrating remaining subsystem changes.
- `display/intel_display_driver.c`: 26 extracted functions, 7 names matched, 19 not matched. Review noirq/nogem/display registration ordering, UEFI/VBT/OpRegion prerequisites and console handoff.
- `display/g4x_dp.c`: 32 extracted functions, 14 matched, 18 not matched. Review DP/eDP training, PPS/AUX, connector and post-enable sequencing against the existing patch 0004/0005.
- `display/g4x_hdmi.c`: 17 extracted functions, 11 matched, 6 not matched. Review encoder/HDMI audio post-enable semantics against patch 0005.

Function extraction is regex-based: counts are **triage candidates, not verified missing features**; false matches and renamed functions require manual source/call-graph review. Inapplicability is hardware-target-specific and cannot narrow the original all-platform parent scope.

## Next implementation gate

Review `i915_driver.c` and `display/intel_display_driver.c` against the exact pinned NetBSD driver probe/lifecycle. Materialize a call-order and OS-adapter delta with per-function target evidence; implement reference-backed changes, verify on isolated objects, and update the whole-driver matrix. Preserve the six-edit NetBSD overlay and F77 recovery state. No combined kernel build or HP reboot before the parent i915 prerequisite gate.
