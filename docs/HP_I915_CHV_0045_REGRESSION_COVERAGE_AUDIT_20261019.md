# CHV/VLV eDP 0045 — fail-closed source regression coverage review

Date: 2026-10-19  
Project: HP-I915 (NetBSD 11 / amd64, HP TPN-W121)  
Status: **TEST SOURCE HARDENED — NOT EXECUTED / NO DRIVER INTEGRATION**

## Inputs and exact source identities

- Previous owner i915 HEAD: `3f61031a383674bcfe3815dabbac89d26b0641a1`
- Candidate: [0045](../candidates/0045-netbsd11-i915-edp-short-hpd-no-resume-pps-guard.patch), Git blob `fc0f1fab9c9ad66064dd22418578087f1e0244d4`, separate, **unintegrated**, frozen NetBSD source hunk original 30 → candidate 74 lines.
- Regression script: [test_chv_edp_short_hpd_0045_source.py](../tests/test_chv_edp_short_hpd_0045_source.py). Before hardening: blob `144e7d36867357337211402aefea6e0e8805607b`; after hardening source will be read back and linked in PRE/POST.
- NetBSD/src pinned `03d918f6d0e81fa05b8f1160eca0628ad39988a6`: `display/intel_dp.c` blob `1dd8858b2d331906190258c8602af55966ff986c`, `display/intel_display_power.c` blob `b11bfb6dfc8d67877770c0820c23d6541188cd10`, `include/linux/pm_runtime.h` blob `01d2e138590ff25d549a135545e3b68c39d9205c`, `display/intel_hotplug.c` blob `722edbed2be6b1c4b2d06269572a977e6ca7adef`.

## Discovered regression-oracle defects

Before hardening, `audit()` checked only whether important source substrings appeared **in order**. This missed dangerous edits preserving the substrings but changing semantics:

| Unchecked prior variant | Failure mode | New oracle |
|---|---|---|
| Replace `intel_aux_power_domain(dig_port)` with `POWER_DOMAIN_INIT` | References wrong power domain for PPS/AUX data read | Require exact AUX-domain expression once |
| `if (!wakeref) return true;` | Erroneously accepts a powered panel when no wakeref exists | Require **fail-closed** return false under failed acquisition |
| Suspend early gate `return true` | Reports panel powered during disabled interrupts or display suspend | Require early two-state OR gate with return false |
| `edp_have_panel_power() && edp_have_panel_vdd()` | Drops legitimate `panel power OR forced-VDD` interpretation | Require correct locked **OR** predicate |
| Call `intel_display_power_put()` twice | Domain refcount and wakeref ownership corruption | Require exactly one matching domain/ref put |
| Use `powered = irqs_enabled || ...` | Incorrect positive result with suspended display/panel off | Require locked suspend **AND** before panel/VDD OR |

Six corresponding negative mutants were added, bringing the authored suite from **10 to 16**. The original ten still test missing IRQ gate, missing display suspend gate, unconditional power GET, missing PPS lock/unlock, wakeref leak, absent VDD branch, missing second suspend guard, external DP route contamination, and removed long eDP HPD suppression.

The revised checker requires the exact frozen C and shim SHA values before scratch operations. It checks source ownership (correct AUX domain, conditional single acquisition, early fail-closed returns, correct locked boolean predicate and exactly one power release). This detects specific source mutations but **is not a C compiler, executable behavioral test, lock proof or physical validation**.

## Execution boundary and unresolved acceptance

The script is **AUTHORED, NOT_RUN**. The previous provider denied the equivalent execution path; running it through another executor to evade that denial is not allowed. A genuinely authorized scratch executor must separately execute the original test against the exact four frozen NetBSD C/shim files plus patch, demanding actual exit code 0, byte-for-byte `git apply --reverse` recovery and these exact markers:

- `CHV_EDP_HPD0045_PINNED_SOURCE_GUARD_PASS`
- `CHV_EDP_HPD0045_SIXTEEN_MUTATIONS_REFUSED`
- `CHV_EDP_HPD0045_BYTE_EXACT_REVERSE_PASS`

Even a future executable PASS is limited to a **source-model** acceptance layer; it does not close live NetBSD C compilation, i915+DRM/TTM+RTL native link, the VDD-off/short-pulse race, HP physical KMS/boot recovery or WPA2. Further 300 Linux→NetBSD semantic units remain OPEN.

Material PRE/POST: `Agent-Governance/state/events/hp-i915-edp-0045-regression-coverage-review-20261019.jsonl`. Owner and active handoff remain `Agent-Governance/state/projects/HP-I915.md` and `Agent-Governance/handoffs/HP-I915-CURRENT.md`.
