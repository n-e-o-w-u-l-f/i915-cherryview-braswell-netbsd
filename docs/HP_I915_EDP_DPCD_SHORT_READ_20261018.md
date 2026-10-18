# Cherryview eDP DPCD supported-rate short read — 2026-10-18

**Status:** frozen NetBSD source correction/host-C behavior **PASS**, full 323-i915 semantic integration **OPEN**. No native NetBSD kernel build or HP hardware test.

## Frozen sources and issue

- NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, `sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c`, SHA256 `7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141`.
- Existing owner patch: `candidates/0012-i915-edp-dpcd-rates-failed-aux-read-netbsd11.patch`, SHA256 `a50717c043eff10e31c5dd8d9582632d71197203c5a13738e12e7e520817a5fa`.
- The original `intel_edp_init_dpcd()` reads `DP_SUPPORTED_LINK_RATES` into a local **uninitialized** `__le16 sink_rates[DP_MAX_SUPPORTED_RATES]`, discards `drm_dp_dpcd_read()`'s byte count/error and parses all entries until zero. Negative/zero/short AUX replies therefore leave undecided stack words feeding rates and `num_sink_rates`.
- Patch `0012` checks for **exactly** `(ssize_t)sizeof(sink_rates)` bytes and clears the entire array on any other result. Existing `num_sink_rates == 0` logic then selects `intel_dp_set_sink_rates()`; successful full reads retain their original rate-order parsing and `use_rate_select`.

## Verified implementation and failure injection

New permanent test `tests/test_edp_dpcd_rate_shortread_pinned.py` extracts the **actual patched NetBSD source fragment** and compiles/runs it as an isolated C11 strict `-Wall -Wextra -Werror -pedantic -fsanitize=undefined` fixture.

Five cases **PASS**: full valid advertised rates, negative `-EIO`, a two-byte short read, a zero-byte read, and a full valid all-zero rate set. Failure/short/empty replies yield zero custom rates and the default-rate fallback; the successful case preserves three decoded rates and uses rate-selection mode. Five deliberate source/patch corruptions refuse. Real `git apply --check`, application, duplicate rejection, exact source comparison and byte-exact reversal PASS. The test's mock `ARRAY_SIZE` is `int`-cast only to avoid an unrelated host `-Wsign-compare` compilation warning in imported code; this is not a target kernel warning fix.

**Legion marker:** `I915_0012_DPCD_RATE_SOURCE_PATCH_5_CASES_5_MUTANTS_PASS` at i915 branch `6d0d78c2882a372a59b5ebaf56e3e4e9c9121974`.

## Shared nonrelease source staging

RTL owner `wip/hp-rtl-runtime-48-merge-20261010` at `f7d89b444a0cf9e27c37fb39ff6ad84b9cb0d39a` applies `0012` **after** existing `0004` (AUX precharge), `0013` (IRQ fallback) and `0039` (14 G08 phase prints), while retaining `0002` power well and `0038` main G01–G09 trace in a separate private file.

- Real frozen-source private mirror of 50 RTL C units: **PASS**.
- Final private `intel_dp.c` SHA256: `712c7364f821320af523b140881cb64b00092e664c07706b7b8e884d57f6aecc`; checked in `diagnostic-source-manifest.json`.
- Five negative source/stage cases refused; original pinned files byte-for-byte unchanged.
- Source syntax, shell syntax, no unrelated diff whitespace and off-HP execution refusal PASS.
- `status=STAGED_DIAGNOSTIC_NONRELEASE_NO_KERNEL_BUILD`, `eligible_for_install=false`, `eligible_for_boot=false`, `kernel_build=NOT_RUN`.

This guards *one* eDP DPCD error route. Pending: complete modern Linux i915 323 source semantics including actual AUX IRQ/PM/hotplug, DRM/TTM ABI, genuine native NetBSD compiler and kernel link, recoverable kernel install, user's installed-kernel test, then physical KMS verification. Do not classify a Linux i915 unit as `PORT_COMPLETE` based on isolated old NetBSD source tests.
