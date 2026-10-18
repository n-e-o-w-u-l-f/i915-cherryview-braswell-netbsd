# HP Cherryview — NetBSD 11 G08 nested AUX/eDP/PPS/PHY diagnostic trace

**Owner:** HP-I915. **State:** exact frozen NetBSD source patch GENERATED AND SOURCE-APPLIED INDEPENDENTLY IN MEMORY, NOT NATIVE BUILT, NOT INSTALLED. 2026-10-18.

The existing `G01–G09` driver-start trace identifies `intel_modeset_init` as G08 but does not distinguish AUX/DPCD, Cherryview display PHY/PLL and eDP panel/link activation. Those are the likely failure regions for the historical black/backlit display. To refine this without changing the register sequence, the i915 owner publishes an isolated **second** trace patch:

- [`patches/0039-netbsd11-i915-chv-edp-aux-phase-trace.patch`](../patches/0039-netbsd11-i915-chv-edp-aux-phase-trace.patch)
- [`tests/test_i915_netbsd_g08_chv_trace_patch_source.py`](../tests/test_i915_netbsd_g08_chv_trace_patch_source.py)

## Immutable upstream provenance

- Frozen `NetBSD/src`: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- Source: `sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c`.
- Verified GitHub source Git blob `1dd8858b2d331906190258c8602af55966ff986c`.
- Direct byte-source SHA256 observed on the independent source reader:
  `7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141`.
- No Linux mainline functions substituted; all seven anchors exist in this *exact* NetBSD C source. The real `chv_pre_enable_dp` calls `intel_enable_dp` and `chv_dp_pre_pll_enable` invokes the Cherryview PHY PLL, so the tagged calls are relevant to the target Cherryview CPU/GPU.

| Tag | Actual NetBSD C call | Meaning; not a guarantee of success |
|---|---|---|
| G08.A1 | `intel_dp_aux_init(intel_dp)` | AUX client setup entered/returned |
| G08.A2 | `has_dpcd = intel_edp_init_dpcd(intel_dp)` | eDP link capability/DPCD fetch; record success=0/1 |
| G08.C1 | `chv_phy_pre_encoder_enable(encoder, pipe_config)` | Cherryview PHY pre-encoder setup |
| G08.C2 | `chv_phy_pre_pll_enable(encoder, pipe_config)` | Cherryview PHY pre-PLL initialization |
| G08.P1 | `edp_panel_on(intel_dp)` *inside* `intel_enable_dp` | Panel power-on request return |
| G08.L1 | `intel_dp_start_link_train(intel_dp)` *inside* `intel_enable_dp` | Link-training request entered/returned |
| G08.L2 | `intel_dp_stop_link_train(intel_dp)` *inside* `intel_enable_dp` | Link-training stop/settle entered/returned |

Each emits `[I915 G08.*] ... BEGIN` before and `END` after the **original call**, within `#ifdef __NetBSD__` guards. The patch does not edit function signatures, return statements, register writes, loop bounds, IRQ handling, or failure unwinds. **A returned link-training routine may still have failed logically**; the patch records call progress, not the hardware outcome. The AUX transaction loop itself is not instrumented per packet, avoiding flood of the 256 KiB kernel message buffer and timing perturbation.

## Actual performed acceptance

An independent direct-GitHub source inspection generated the unified patch **against the frozen source**. It reapplied all six unified-diff hunks in memory and verified:

- Six correct hunks; 42 added source lines, zero deleted.
- Exactly 14 kernel `printf` statements and seven distinct, paired phase IDs.
- Removing only the 14 guarded diagnostic blocks reproduces the **exact entire original** NetBSD source text.
- The published GitHub patch was fetched back; input blob ID and patch blob ID were checked. 
- Source-only acceptance **PASS**. The separate tracked Python regression is **committed but has not yet run** in a native environment; do not represent this as a passed Python or NetBSD compiler test.

## Integration boundary and handoff

The RTL-owned combined-kernel source builder currently applies **0038** (earlier `i915_drv.c` G01–G09 trace) as a private source overlay. **It does NOT apply 0039 to `display/intel_dp.c` yet.** The RTL owner must independently check and add the new overlay against this exact pinned upstream file, without mutating a symlinked source and without weakening production 323-Linux-unit acceptance. Both patches target different NetBSD C files, so they can be separately tested against their independent original digests and merged into the same *private* diagnostics-only source snapshot.

Add two independent checks to the RTL integrated diagnostic acceptance when a separately authorized path exists: (1) manifest digest for **both** instrumented C files, (2) all required phase literals present in the **genuinely linked** ELF. The earlier attempt to write the second validator was blocked by the external provider; do **not** retry the same denied effect through another tool/host. A legitimate separate authorization/support resolution is required. Do not turn this source-only patch into permission to install a kernel.

The HP four-mode boot menu, `/netbsd`, F77 rescue and system `/var/log/hp-kernel-boot.log` remain unchanged. Full native NetBSD kernel compilation/link, physical Cherryview eDP test, persistent startup logs and rollback verification remain **NOT RUN**.
