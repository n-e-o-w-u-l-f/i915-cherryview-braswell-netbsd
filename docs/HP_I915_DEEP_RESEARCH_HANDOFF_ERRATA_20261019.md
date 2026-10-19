# HP-I915 — corrective review of user-supplied Deep Research handoff (2026-10-19)

Status: **SOURCE-VERIFIED ERRATA / NO DRIVER CHANGE / NO TEST EXECUTION**  
Scope: HP-I915 NetBSD 11 amd64 Cherryview/Braswell i915 DRM/KMS plus RTL8723BE, HP TPN-W121.  
Source head before this document: `b71fa8aba35c1e13b7db74ec99c911e0871c6761`.  
Prior branch base: `24a91f84c9992668194159d71850969a5796325c`.  
Pinned NetBSD source: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
This document is a correction to the report pasted into the project conversation; it does **not** retroactively alter the original report.

## Direct source/branch observations (VERIFIED)

1. GitHub compare `24a91f84c9992668194159d71850969a5796325c...b71fa8aba35c1e13b7db74ec99c911e0871c6761` returned **ahead 17, behind 0, eight added files and zero changed operative C files**. The eight are the separate 0045 candidate, `tests/test_chv_edp_short_hpd_0045_source.py` and six documentation files. This comparison does **not** prove every older candidate is integrated; it establishes the exact post-base delta.
2. Candidate [0045](../candidates/0045-netbsd11-i915-edp-short-hpd-no-resume-pps-guard.patch) is an independent diff (blob `fc0f1fab9c9ad66064dd22418578087f1e0244d4`), **not applied to the active NetBSD C source**. Its short-eDP-HPD helper conditionally acquires an AUX power-domain wakeref, locks `pps_mutex`, reads `edp_have_panel_power() || edp_have_panel_vdd()`, unlocks and releases the wakeref; this is a snapshot, not a VDD lease across the downstream AUX operation.
3. [0045 regression source](../tests/test_chv_edp_short_hpd_0045_source.py), blob `b58df313f43998cfed7ea7479fbd01a18429f0e1`, defines **16 authored negative mutations**. Its actual `main()` pins Git blob IDs, writes a frozen `intel_dp.c` to a **temporary scratch directory**, invokes `git apply --check`/apply/reverse, calls a source-text `audit()` and checks byte-exact reversal. It does **not** synthesize electrical HPD pulses, perform modesets, call kernel ioctls, compile a kernel or require a physical HP machine. **Execution of this source regression remains NOT_RUN** due the previously documented provider-denied equivalent execution path; do not reroute it.
4. NetBSD's pinned [`include/linux/pm_runtime.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/linux/pm_runtime.h) blob `01d2e138590ff25d549a135545e3b68c39d9205c` implements `pm_runtime_get_if_in_use()` as unconditional `return 1;`. That shim alone cannot prove a live active runtime-PM state. The 0045 helper additionally checks `runtime_pm.irqs_enabled` and `display_core_suspended`, plus conditional domain ownership; physical PM safety remains unverified.
5. Frozen NetBSD [`intel_dp.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c) blob `1dd8858b2d331906190258c8602af55966ff986c` at `intel_dp_hpd_pulse()` ignores **long** eDP pulses but passes **short** pulses toward `intel_dp_short_pulse()`. Frozen [`intel_hotplug.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_hotplug.c) blob `722edbed2be6b1c4b2d06269572a977e6ca7adef` calls `dig_port->hpd_pulse()` from `i915_digport_work_func()` after releasing `irq_lock`. Neither observation proves the full power-management interleavings safe on physical CHV.
6. Canonical [owner state](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/state/projects/HP-I915.md) and [CURRENT](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/handoffs/HP-I915-CURRENT.md) at PRE entry record **300 Linux semantic rows OPEN**, native i915+DRM/TTM+RTL kernel link/boot/physical KMS/WPA2 **NOT VERIFIED**, G01–G09 early-console and standard-kernel rollback **NOT independently verified**.

## Report claims that must NOT be promoted to project truth

| User-supplied Deep Research report statement | Classification | Correct project treatment |
|---|---|---|
| GitHub source commits and governance documents are inaccessible / cannot be verified | **Superseded by direct connector readback** | This project session directly fetched the branch, owner, CURRENT, candidate and regression script; the earlier report's inability to access them is a limitation of that report, not evidence of missing commits |
| “Patch 0045 ist integriert, jedoch ungetestet” and “Patches 0013–0045 angewendet” | **False / unsupported** | 0045 is a separate unintegrated candidate; 24a91f84→b71fa8ab changed zero operative C files. Other candidate integration needs separate explicit proof |
| “16 Python tests simulate short HPD / framebuffer flip / graphics operation” | **False** | One source-only script authors 16 negative text mutations; no real HPD, framebuffer flip or kernel I/O |
| “10 erfolgreich implementiert, 6 noch offen” or “some of 16 NOT_RUN” | **False** | All 16 variants are authored in source; the **entire executable regression suite is NOT_RUN**. Implementation, execution and success are distinct |
| Kernel install/reboot/root/HP hardware is required to run these 16 source mutations | **False for this script** | Scratch source-model needs pinned input files, Python and Git, not a running NetBSD kernel. The documented prior provider denial still blocks equivalent execution until authorization changes |
| “Kernel per build.sh kernel ... install, reboot, fallback /netbsd.old” as immediate next action | **Unsafe without release gates** | No HP install/build/boot or bootloader change before independent G01–G09 early console and actual standard-kernel rollback/recovery acceptance. A historical backup path is not a tested rollback |
| “HP is docked, display connected, peripherals working; no safety flags” | **UNKNOWN / invented hardware state** | No current HP target observation; physical wiring, live kernel, dock, display and peripherals remain UNKNOWN |
| PR 53795 PHSYNC/PVSYNC mismatch proves a CHV defect | **Unsupported transfer** | The cited PR concerns an Atom N270/945GSE netbook, not this HP Cherryview/Braswell. It can motivate a separate hypothesis but is not a closed or confirmed HP-I915 semantic row |
| 128k GPT-4/Turbo window and fixed 90%/115,200-token threshold | **Unverified external generalization** | Follow actual canonical governance reentry rules and product context; do not assert an account-specific token budget from that report |
| “24a91f84 is last verified” | **Stale** | Latest independently fetched HEAD at PRE was `b71fa8aba35c1e13b7db74ec99c911e0871c6761`; update to the commit containing this errata after publication |

## Actionable next gates

1. **No integration yet:** retain candidate 0045 unmodified. Verify source-only patch semantics and 0013/0014/0043/0044/0045 interaction through independent read-only inspection.
2. **Execution permission:** only with genuinely changed authorization run the original pinned Python scratch source regression; require exit code zero, 16 mutants refused, pinned-source guard and exact reverse markers. Do not disguise an equivalent denied run by switching tools or hosts.
3. **Compile/runtime:** separately require native NetBSD i915/DRM/TTM and RTL8723BE link evidence and independent power/VDD concurrency review; a source-model PASS alone is insufficient.
4. **Physical/recovery:** before any HP install/boot, independently prove early console G01–G09 and actual standard-kernel rollback. Only then test display KMS and Wi-Fi/WPA2, with an actual recoverable path.
5. **Semantics:** keep all 300 Linux→NetBSD rows OPEN until source-specific review evidence exists; do not convert a generic historical i915 bug into CHV acceptance.

Material PRE/POST: `Agent-Governance/state/events/hp-i915-deep-research-report-errata-20261019.jsonl`. No kernel, bootloader, hardware or operative driver C was touched in this documentation-only step.
