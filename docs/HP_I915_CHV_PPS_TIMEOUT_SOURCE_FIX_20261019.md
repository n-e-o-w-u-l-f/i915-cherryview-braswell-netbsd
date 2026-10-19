# Cherryview PPS panel-wait timeout diagnostics — verified source fix

Status **2026-10-19**: narrowly scoped i915 producer patch `0041` with pinned source test, five negative cases, and compatible private nonrelease RTL combined stage. This fixes a **false success log**, not a panel failure and not full driver integration.

## Exact Linux-to-NetBSD difference

Frozen Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab:drivers/gpu/drm/i915/display/intel_pps.c` function `wait_panel_status` polls the masked PP_STATUS at 10 ms intervals, 5,000 ms maximum. On timeout it emits `drm_err` **and returns**. It logs “Wait complete” only when the condition was satisfied.

Frozen NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6:sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c` has the equivalent `intel_de_wait_for_register(..., mask, value, 5000)` and holds `pps_mutex`, but previously emitted `DRM_DEBUG_KMS("Wait complete")` after `DRM_ERROR("Panel status timeout")` because its timeout branch had no `return`.

`patches/0041-netbsd11-i915-chv-pps-timeout-no-false-success.patch` adds braces around the failing condition and an immediate `return;`. It does **not** change the return type (`void`), mask, expected value, 5,000 ms timeout, register addresses, lock, VDD handling, IRQ mode or physical panel-power sequence.

- Frozen NetBSD source SHA256: `7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141`.
- Frozen Linux `intel_pps.c` SHA256: `f1f9c08347630a7ff9f7e5c9fb3e527d3db6ae81320b31519843b0ec0cc92866`.
- Producer patch SHA256: `4eda6344f97d6e9a5d5c3677150878f9b008c376f9a387799c0bc3c82c3eeb45`.
- Source test: `tests/test_chv_pps_timeout_diagnostic_source.py` checks these three SHA values, applies to a **throwaway** frozen source, verifies byte-for-byte **only** the desired code replacement, compares Linux timeout/return ordering, performs reverse/roundtrip/duplicate refusal, and rejects five source mutations. On Legion: `CHV_PPS_TIMEOUT_FROZEN_NETBSD_LINUX_5_NEGATIVE_TESTS_PASS`.
- Compatibility test: 0004 AUX precharge + 0039 guarded G08 trace + 0041 applied and reversed byte-exact on the frozen NetBSD C owner: `CHV_PPS_0041_COMPOSES_WITH_0004_G08_0039_AND_ROUNDTRIPS_PASS`.

## Nonrelease combined NetBSD source staging

RTL consumer branch `wip/hp-rtl-runtime-48-merge-20261010` (commits `75412edc` helper and `e33bdeb9` stager) SHA-validates producer 0041 after existing i915 0002/0004/0013, G01–G09/G08 traces, eDP DPCD correction and before the VBlank source integration. This stays entirely within a **private source-only stage**, not the approved NetBSD kernel or production boot path.

Legion `prepare()` returned `HP_RTL50_VBLANK55_CHV_PPS_0041_PINNED_NONRELEASE_STAGE_PASS`: 50 RTL native sources, both VBlank units in the 55-object manifest, unchanged frozen NetBSD original, all 18 G01–G09 + 14 G08 labels, and a final `display/intel_dp.c` SHA256 `d7c3b10aa394801907ed47524be8bd152387902dfa4648a4f07d66e1f7e48308`. The manifest asserts release/boot/install FALSE. Six direct private-overlay refusals passed: double apply, altered timeout, duplicated site, missing G08 guard, missing owner patch, tampered owner patch.

## Acceptance boundaries

This source fix is narrow enough to be independently verified but does **not** demonstrate native C compilation, actual eDP panel power, elapsed time, HP i915 KMS or full Linux-to-NetBSD semantic parity. Other PPS owners, pipe power-sequencer remapping, VDD/reference lifecycle and recovery capture remain OPEN; the 300 Linux units stay `UNREVIEWED`. No native HP kernel was built, installed or tested; standard `/netbsd` and boot entries were not touched.

A technical note for Git: `git diff --check` across the **new raw unified-diff patch file** reports its intentional leading diff-context spaces (`" \t"`) as whitespace; that is not a malformed `git apply` patch. The actual patch applies and reverses byte-exact; source Python files are independently whitespace-checked.
