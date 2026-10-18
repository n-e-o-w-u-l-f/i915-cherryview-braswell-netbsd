# Cherryview/Valleyview IOSF sideband — semantic owner audit (2026-10-19)

**Status:** CHV DPIO PHY/port routing source contract **PASS**; three actual IOSF C function bodies **match after documented API-field normalization**; remaining unit-level semantic closure **OPEN**. No native NetBSD C compiler, IRQ, PHY/eDP or HP KMS acceptance. This is *not* full `display/vlv_sideband.c` or `vlv_iosf_sb.c` completion.

## Frozen evidence (actual source, not symbol-only)

Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`:
- `drivers/gpu/drm/i915/display/vlv_sideband.c`, Git blob `068f58bd9a2b2229e2792fca06de455c0a1d797f`, includes `vlv_dpio_phy_to_unit`.
- `drivers/gpu/drm/i915/vlv_iosf_sb.c`, Git blob `1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758`, includes `vlv_sideband_rw`, `__vlv_punit_get`, `__vlv_punit_put`, `vlv_iosf_sb_{get,put,read,write}`.
- `display/intel_parent.c`, blob `a5e41ea66921398ee0f38911ac6266ed07f4bed7`, forwards through `intel_display_vlv_iosf_interface`.

NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
- `sys/external/bsd/drm2/dist/drm/i915/intel_sideband.c`, blob `1cc6a956b90cc44a85fa153ea1aa9ba58a605eed`.
- `i915_drv.c`, blob `bf64ff40059fc38188f6f3d7b55bef9793abeb57`; `intel_init_dpio` initializes the physical port array in `i915_driver_early_probe` **before** `intel_power_domains_init`.
- `intel_sideband.h`, blob `ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea`. The local `i915_reg.h` is one of the six already modified WIP sources and is not asserted byte-identical to frozen NetBSD; the reviewed `DPIO_PHY(pipe)` and IOSF port macro values match the pinned source.

## CHV physical route match

| Platform/selector | Modern Linux | NetBSD native source | Evidence |
|---|---|---|---|
| CHV `DPIO_PHY0` | `VLV_IOSF_SB_DPIO_2` | `IOSF_PORT_DPIO_2` = `0x1a` | Match |
| CHV `DPIO_PHY1` | `VLV_IOSF_SB_DPIO` | `IOSF_PORT_DPIO` = `0x12` | Match |
| VLV `DPIO_PHY0` | `VLV_IOSF_SB_DPIO` | `IOSF_PORT_DPIO` = `0x12` | Match |

NetBSD `DPIO_PHY(pipe)` is `pipe >> 1`, yielding PHY0 for pipe indices 0/1 and PHY1 for 2. This is the older driver's internal *pipe-index* mapping; it does not mean its pipe indices directly name physical display outputs B/C/D. Both NetBSD `vlv_dpio_read` and `vlv_dpio_write` reference the port array. These invariants are verified by `tests/test_chv_iosf_sideband_semantic_contract.py`.

## Transport and PUNIT semantics checked at actual C-body level

`tests/test_chv_iosf_transport_normalized_source_parity.py` pins the whole Linux and NetBSD transport source Git blobs, extracts the complete **real** bodies for `vlv_sideband_rw`, `__vlv_punit_get`, `__vlv_punit_put`, strips comments/whitespace and applies only three explicit textual adaptations:
- Linux `i915->vlv_iosf_sb.lock` → native `i915->sb_lock`
- Linux `i915->vlv_iosf_sb.qos` → native `i915->sb_qos`
- Linux `cpu_latency_qos_` prefix → native `pm_qos_` prefix.

**All three C bodies then have identical normalized tokens**, including idle-wait `-EAGAIN`, 10,000-unit completion-wait `-ETIMEDOUT`, preemption disable/reenable, PUNIT acquisition/release order, and Valleyview QoS/cross-CPU ping operations. This is a strict *source-text behavior comparison under assumed API adapters*, **not** proof that these different OS-specific APIs preserve identical execution semantics under load.

The first test passes three PHY and three pipe route cases, native global `sb_lock`, PUNIT sequencing/timeout source assertions and **eight deliberately corrupted input source variants refused**. The second passes three normalized genuine C-body comparisons and **seven deliberately corrupted C-body variants refused**. The test-harness mutation anchors were corrected to the owning functions after initial overbroad whole-file matching, then both full tests passed. These are Python source tests, **not compiled C or actual IRQ/DMA tests**.

## Known behavioral/ABI differences requiring separate closure

- Modern Linux `vlv_iosf_sb_get/put` stores `locked_unit_mask` and checks a unit was reserved before read/write. The older NetBSD implementation serializes a shared `sb_lock` but does **not** track/verify individual reservations. Physical bus serialization is source-confirmed; per-unit ownership diagnostics and API parity are **not**.
- Modern `vlv_dpio_get` acquires `DPIO | DPIO_2`; NetBSD's `vlv_dpio_get` passes `DPIO` only. Its global lock is retained regardless of the mask (except the PUNIT acquisition case), so no unproven runtime regression is asserted, but fine-grained lifetime and interaction with other backends remain open.
- `intel_parent_vlv_iosf_{get,put,read,write}` in Linux return early (read=0, write=`-EINVAL`) if its parent IOSF interface is absent; NetBSD uses direct native `vlv_sideband_rw` and `sb_lock` and has no equivalent absent-parent path. Functional reachability during attach/detach remains open.
- Linux backend rejects unknown unit-to-port enum values; NetBSD direct helper accepts a port number and has a different set of warning checks.
- Actual NetBSD mutex/preemption/QoS implementation, PUNIT package sleeping, IRQ context admissibility, PCI chipset register ordering and interaction with DRM/KMS, detach and PHY power wells still require native tests and further semantic owner review.

**Coverage accounting:** Two Linux units (`display/vlv_sideband.c` and `vlv_iosf_sb.c`) now have explicitly documented **PARTIAL_SOURCE_REVIEW** evidence in this audit but **neither is PORT_COMPLETE**. Canonical `docs/I915-STRUCTURAL-COVERAGE.tsv` continues to report **300 UNREVIEWED** until its lifecycle/status schema and the 323-wide review are updated together. The 23 CHV UC/PXP reference exclusions remain separate. No native HP build/install/boot or physical KMS acceptance is authorized.

Next: inspect all upstream `unit_to_{port,devfn,opcode}` versus native callers, `intel_parent` registration/cleanup, verify the IOSF lock-unit warning and power/IRQ contexts as native NetBSD ABI obligations, and continue the other 298 uncompleted Linux i915 units with whole-function error/PM/DRM/TTM evidence.
