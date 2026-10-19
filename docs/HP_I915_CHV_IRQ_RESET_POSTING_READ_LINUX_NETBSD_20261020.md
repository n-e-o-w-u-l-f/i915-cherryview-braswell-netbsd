# HP-I915 — Cherryview IRQ reset posting reads, MMIO mapping, and suspend ordering

Date: 2026-10-20 (Europe/Berlin).  
Status: **PINNED SOURCE VERIFIED / NO NEW C PATCH / RUNTIME NOT VERIFIED**.  
Source branch prior head: `5845ee9a9acbe0d8c42d7b74442f84e66144e8a1`.  
NetBSD pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Linux comparison pin: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Source identities

| File | Pinned blob | Source anchor |
|---|---|---|
| [NetBSD `i915_irq.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.c) | `73f8deec8404481c4e457bb72631456b3b11ff69` | `gen3_irq_reset` lines 177–194, `vlv_display_irq_reset` ~2709, `cherryview_irq_reset` ~2912, `cherryview_irq_postinstall` ~3475, IRQ runtime suspend/resume ~4193–4230 |
| [NetBSD `i915_irq.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.h) | `1e1bb82c96c3267d4ee6331bd969713e2b7c2dff` | `GEN3_IRQ_RESET` and `GEN8_IRQ_RESET_NDX` expand into `gen3_irq_reset`, ~136–143 |
| [NetBSD `gt/intel_gt_irq.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/gt/intel_gt_irq.c) | `6882d2877bc361225d9df6a38d7f4fcd44ea9450` | `gen8_gt_irq_reset()` loops GT IRQ groups 0–3 via `GEN8_IRQ_RESET_NDX` |
| [NetBSD `i915_drv.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.h) | `009764d0c1bd6b60d34ab3b2c5864b28f7566211` | `POSTING_READ(reg)` expands to `intel_uncore_posting_read(&dev_priv->uncore, reg)`, ~2021–2027 |
| [NetBSD `intel_uncore.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/intel_uncore.h) | `2962d53ce73363fa8b7662e1563092fef3ba3ab6` | `intel_uncore_posting_read` = actual notrace MMIO read ~419; NetBSD raw MMIO read/write = `bus_space_read_4`/`bus_space_write_4`, ~290–330 |
| [NetBSD `intel_uncore.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/intel_uncore.c) | `3a6513360eff015eb226a2a393f07bdf9e754dba` | `uncore_mmio_setup` ~1720–1747 uses `pci_iomap` and NetBSD `regs_bst/regs_bsh`, with an AGP borrowing fallback; mapping attributes on actual HP not inspected |
| [Linux `i915_irq.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/i915_irq.c) | `932409b943ad252c2ad63b91384385fba0936a99` | `cherryview_irq_reset` ~665–681 writes zero to master and posting-reads before GT/PCU/display IRQ reset; `cherryview_irq_postinstall` ~746–760 also posting-reads |
| [NetBSD bus_space(9)](https://man.netbsd.org/bus_space.9) | live online manual, independent external reference | Basic register reads/writes and `bus_space_barrier()` semantics; read/write ordering may depend on cacheable/prefetchable mappings. **Not a hardware readout.** |

## Verified Cherryview reset ordering in frozen NetBSD

```text
intel_runtime_pm_disable_interrupts()
  -> intel_irq_reset()
     -> cherryview_irq_reset()
        I915_WRITE(GEN8_MASTER_IRQ, 0)
        POSTING_READ(GEN8_MASTER_IRQ)       <-- PRESENT
        gen8_gt_irq_reset()
          -> GEN8_IRQ_RESET_NDX(GT, 0..3)
             -> gen3_irq_reset(group)
        GEN3_IRQ_RESET(GEN8_PCU_)
          -> gen3_irq_reset(PCU group)
        spin_lock_irq(&dev_priv->irq_lock)
          if (display_irqs_enabled)
            vlv_display_irq_reset()
              -> status/hotplug/PIPestat cleanup
              -> GEN3_IRQ_RESET(VLV_)
        spin_unlock_irq(...)
  dev_priv->runtime_pm.irqs_enabled = false
  intel_synchronize_irq() -> NetBSD xc_barrier(0)
```

For each `gen3_irq_reset`: set **IMR all masked**, *posting read IMR*, set **IER=0**, clear **IIR=all ones**, *posting read IIR*, clear IIR again, *posting read again*. Its source comment explains that IIR can theoretically hold two queued events. The GT 0..3 and PCU reset paths genuinely pass through this helper, and VLV display IRQ group does so only when `display_irqs_enabled`.

On resume `intel_runtime_pm_enable_interrupts` writes `runtime_pm.irqs_enabled=true` **before** reset and postinstall. The CHV `cherryview_irq_postinstall` ultimately writes `GEN8_MASTER_IRQ=GEN8_MASTER_IRQ_CONTROL` and then `POSTING_READ(GEN8_MASTER_IRQ)`. Neither this report nor an attempted native reproduction changes that existing order.

## Linux parity versus unresolved runtime guarantees

**SOURCE VERIFIED — missing posting-read hypothesis rejected.** The pinned Linux `cherryview_irq_reset` uses the same top-level sequence: write zero to `GEN8_MASTER_IRQ`, read back, then GT reset, PCU reset, display reset. Current Linux has refactored display and generic IRQ register helpers; do **not** infer identical register accessibility, masks or synchronization just from the high-level order.

**SOURCE VERIFIED — POSTING_READ is not an empty macro.** In NetBSD `POSTING_READ` expands through `intel_uncore_posting_read` to an actual untraced MMIO read; the raw MMIO implementation uses `bus_space_read_4` with the mapped PCI BAR handle. This supplies an intentional register write/readback ordering point. A mere added `POSTING_READ(GEN8_MASTER_IRQ)` candidate would be a duplicate, **not** a bug fix.

**OPEN — actual MMIO mapping and architecture bus ordering.** The NetBSD bus_space(9) manual notes potential ordering differences for prefetchable/cacheable mappings and describes `bus_space_barrier`. Actual HP `pci_iomap` mapping attributes, borrowed AGP mapping and effective memory type have NOT been read on the target or fully audited from kernel sources; do **not** assert this is a cacheable mapping bug or that an extra `bus_space_barrier` is required. A device register readback is also **not a CPU handler completion primitive**.

**OPEN — CPU IRQ handler lifetime.** CHV's ISR checks `intel_irqs_enabled` before MMIO. Since disable sequence is **reset → flag=false → xc_barrier(0)**, a handler entering before the flag change could still be in progress while the reset starts; the subsequent xcall supplies CPU scheduling-order evidence but not an explicitly device-specific `synchronize_irq` guarantee for all pending MSI/INTx. Prior [vector analysis](HP_I915_AMD64_VECTOR_PENDING_XCALL_CHV_IRQ_20261019.md) confirms `IPENDING`/`IMASKED` can be processed later.

**OPEN — display conditional reset.** The display register IRQ reset under `irq_lock` is conditional on `display_irqs_enabled`. This is source behavior in NetBSD and similar high-level display IRQ behavior exists in Linux; a concrete bug needs proof that pending display IRQs reach unsafe MMIO while the display domain is unavailable, not a guess from this condition.

## No proposed 0047; bounded next acceptance

1. Inspect *the exact* NetBSD `pci_iomap` mapping and `agp_i810_borrow` setup for BAR and cache attributes; determine whether additional bus barriers are meaningful for this memory type. Track 0013 AUX pending wait separately.
2. For a real authorized HP read-only audit, collect actual loaded kernel, PCI bus/IRQ mode (MSI vs INTx), GPU MMIO mapping and native kernel messages. SentinelX authenticated host inventory on this date listed **only `legion`**, not HP, so no HP observations were made through that connector.
3. If runtime instrumentation becomes genuinely authorized under fully verified G01–G09 recovery, observe events at pre-reset/master posted-read/flag=false/xcall completion and CHV ISR entry/exit, including `IPENDING`/late pending MSI/INTx. Do **not** claim CPU race-freedom from source-only parity.
4. Do not invent a second posting-read patch or blindly insert `bus_space_barrier`, `pci_intr_disestablish` or source-wide `intr_mask` into suspend. Shared INTx and in-flight CPU handlers require their own acceptance.
5. Original staged patches 0013/0014/0043/0044/0045/0046 still UNINTEGRATED. Combined `git apply`, 0045 sixteen-negative-source regression (provider-denied equivalent), native i915+DRM/TTM+RTL and HP KMS/WPA2 remain **NOT_RUN / NOT VERIFIED**; **300 semantic rows OPEN**. No HP kernel/boot until independent G01–G09 early console plus working standard-kernel recovery.

This is a source-only checkpoint, not a kernel-build, hardware-test or a semantic-row closure. Canonical PRE/POST: `Agent-Governance/state/events/hp-i915-chv-irq-posting-read-reset-source-parity-20261020.jsonl`.
