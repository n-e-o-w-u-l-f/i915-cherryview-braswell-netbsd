# HP i915 — 300-unit semantic verification ledger (2026-10-19)

**NOT COMPLETED: 0/300 semantically accepted, 300/300 remain open.** This report records what was actually checked and identifies prerequisites for the requested full Linux 7.3-rc4 → NetBSD 11 Cherryview/Braswell port. Blob identity, source discovery, symbol-name overlap and synthetic object-map tests **are not semantic correctness**.

## Frozen source identities and all-unit audit

- Linux: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`; i915 subtree `7539d62f58a7e879ed3899b7805f49ddba109846`. All **323 active Linux source paths** exist in that exact Git tree; the 300 `UNREVIEWED` rows have pinned individual Git blob SHA and byte lengths in [Linux 300 manifest](evidence/HP_I915_LINUX_300_BLOBS_20261019.json).
- NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, i915 subtree `b43c809e1c0651bc09939e8a53f4b9d5d328b92f`; all 264 i915 C and 225 header files have pinned reference blob identities in [NetBSD 489-file manifest](evidence/HP_I915_NETBSD_FROZEN_CODE_BLOBS_20261019.json).
- [All-300 source identity crosswalk](evidence/HP_I915_300_LINUX_NETBSD_BLOB_CROSSWALK_20261019.json): **151** same relative source paths with differing blob content; **149** without the same relative path; **0** byte-identical. A different name/path does *not* establish absence of an implementation, and a matching name never establishes semantic parity.
- Source-identity validation on reachable `legion`: **483/489** local NetBSD C/H blobs exactly match the frozen original; the other **six** are independently identified local WIP modifications, not silently treated as frozen: `display/intel_display.c`, `display/intel_display_power.c`, `display/intel_dp.c`, `gt/intel_lrc.c`, `i915_pci.c`, `i915_reg.h`. Their *observed* Git blob SHA values are separately pinned in the audit script and the original NetBSD tree was not overwritten.
- Of the **300** open Linux entries, **152** have a candidate existing NetBSD C source owner using known selected/moved mapping; **145** of these are selected in the local NetBSD i915 build filelists; the other **148** have no established local C source owner by this conservative mapping. These figures do not count functions with successful semantic equivalence.
- Complete Linux file *contents* were actually checked against their frozen Git blobs for only **seven** local references: `display/intel_backlight.c`, `display/intel_display_power_well.c`, `display/intel_dp_aux.c`, `display/intel_pps.c`, `display/intel_vblank.c`, `display/vlv_sideband.c`, `gt/intel_ggtt_fencing.c`. The remaining **293** reference bodies were not retrieved and semantically analyzed in this execution. Individual blob existence **does not replace reading the code**.

## Reproducible semantic precondition runner

`tools/audit_i915_300_semantic_preconditions.py` executes a fail-closed **300-row** inventory against the frozen Git manifests and the 489 real local NetBSD C/H bytes, including the six known worktree variants. It records source-owner candidates, build selection and function-name candidates for the seven available Linux originals; all ten per-row review gates remain `OPEN` unless source-read evidence exists. The runner returned `total=300`, `netbsd_c_files_indexed=264`, `linux_originals_content_verified=7`, `semantics_verified_and_accepted=0` on Legion.

`tests/test_i915_300_semantic_preconditions.py` executed successfully on Legion with five negative controls: missing row, reordered Linux/NetBSD crosswalk, changed native code Git blob, changed Linux commit pin and changed available Linux backlight blob. All five were rejected. Python syntax and `git diff --check` passed. Actual full row-level output was saved on Legion as `/tmp/hp-i915-300-semantic-preconditions-20261019.json` (temporary host path, not a repository release).

Published row-level slices:
[000–049](evidence/HP_I915_SEMANTIC_PRECONDITIONS_20261019_000_049.json) ·
[050–099](evidence/HP_I915_SEMANTIC_PRECONDITIONS_20261019_050_099.json) ·
[100–149](evidence/HP_I915_SEMANTIC_PRECONDITIONS_20261019_100_149.json) ·
[150–199](evidence/HP_I915_SEMANTIC_PRECONDITIONS_20261019_150_199.json) ·
[250–299](evidence/HP_I915_SEMANTIC_PRECONDITIONS_20261019_250_299.json).
Publishing **200–249** was denied by platform safety checks; its local result exists but the slice is deliberately **not** claimed as published or silently reissued by another route.

## Real hardware-semantic gaps discovered during sampled source reading

- **VLV/CHV backlight:** Frozen Linux and NetBSD differ at panel enable minimum-clamp `< min → min` versus `<= min → max`. Candidate `0019` is committed and its exact two-line transformation was source-verified; a compiler/runtime test is still pending after a host-fixture failure and subsequent provider probe denial. Full backlight source semantics not accepted.
- **DSI fallback:** Frozen NetBSD `intel_panel.c` still has an explicit `panic()` for CHV/Valleyview DSI PWM fallback and the `vlv_dsi.c` caller ignores the backlight setup result. A two-file nonfatal cleanup path passed ten in-memory source/control-flow invariants, but the required governance PRE publication was denied. **No 0020 patch was installed or published.**
- **Sideband/IOSF:** Linux `display/vlv_sideband.c` uses dedicated `intel_parent_vlv_iosf_{get,read,write,put}` operations and DPIO_PHY0/PHY1 → IOSF port selection. NetBSD `intel_sideband.c` uses `vlv_iosf_sb_get/put`, the `sb_lock` and `dpio_phy_iosf_port[DPIO_PHY(pipe)]`. Symbol-name overlap alone is not a valid equivalence proof; lock/ref counting, PHY selection, timeout propagation and PUNIT sleep exclusion remain open.
- **Other previously source-staged cases:** VBlank core/worker (including `SCHED_RR` versus Linux `SCHED_FIFO`), AUX/IRQ/precharge, DPCD short-read and CHV Full-PPGTT have scoped tests and private overlay evidence, **not complete 323-file semantic or HP hardware acceptance**.

## Outstanding mandatory acceptance for each source unit

A unit may be closed only with explicit evidence for actual Cherryview PCI/platform reachability (or fully justified inapplicability); all reachable functions and cross-file owners; exact register side-effect/order; DRM/GEM/TTM and NetBSD ABI types; memory/DMA lifetime; IRQ/locks/workqueue, PM, firmware paths and suspend/resume; partial-allocation error unwinding and detach; build/link ownership; regression cases and negative mutations; then the applicable native kernel/hardware gates. The 23 prior CHV UC/PXP reference-inapplicable records remain separate from the **300 still unreviewed**, and their exemption evidence must not be applied to other source units without proof.

**Do not authorize HP native kernel building yet.** The sequence remains: complete all 323 Linux i915 semantic/source closure with DRM/TTM adapters; verify independent boot diagnostics and recovery; compile/link natively on HP; stage a separate non-default test kernel; **user tests the installed kernel**; only afterward physically validate KMS/eDP and combined RTL/WPA2. No HP kernel, bootloader or OS files were modified in this sweep.
