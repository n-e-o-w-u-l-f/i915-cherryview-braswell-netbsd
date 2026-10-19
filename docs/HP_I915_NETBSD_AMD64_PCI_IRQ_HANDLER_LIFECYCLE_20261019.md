# HP-I915 — NetBSD/amd64 PCI MSI, MSI-X and INTx: IRQ registration / teardown versus i915 AUX 0013

Date: 2026-10-19  
Status: **PINNED SOURCE REVIEW ONLY — NO PATCH INTEGRATION OR EXECUTED IRQ TEST**  
Owner: HP-I915 / Cherryview–Braswell Intel i915 DRM/KMS and RTL8723BE combined NetBSD 11/amd64 kernel, HP TPN-W121.  
Last i915 HEAD before this document: `57d684a4f09318710f4ad30c2e7a7deac66e477a`.  
NetBSD pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Linux reference pin: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Primary pinned source inventory

| Source | Pinned Git blob | Relevant entrypoints |
|---|---|---|
| [`sys/arch/x86/pci/pci_intr_machdep.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/pci/pci_intr_machdep.c) | `34df2272d57c0c50b6ef97b0a296310a9ab3df53` | `pci_intr_establish_xname_internal()` ~300–351; `pci_intr_disestablish()` ~369–380 |
| [`sys/arch/x86/pci/pci_msi_machdep.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/pci/pci_msi_machdep.c) | `33b1b7df86d3d7069dfb985c7fa0c768b5138826` | `pci_msi_common_establish()` ~225–242; `pci_msi_common_disestablish()` ~245–250 |
| [`sys/arch/x86/x86/intr.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/intr.c) | `7fe7a1813dbe82dbf76b5bddc32d84bc15bff580` | `intr_establish_xname()` ~835–1038, `intr_mask_internal()` ~1120–1150, `intr_disestablish_xcall()` ~1180–1260, `intr_disestablish()` ~1270–1296 |
| [`sys/arch/x86/include/intr.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/include/intr.h) | `12ea58537e33427b1bbccfaae7f1b6850e7f1542` | `struct intrhand`, `struct intrsource` definitions and mask/unmask/disestablish declarations |
| [`sys/external/bsd/drm2/dist/drm/i915/i915_irq.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.c) | `73f8deec8404481c4e457bb72631456b3b11ff69` | `intel_irq_install()` ~4059–4139; `intel_irq_uninstall()` ~4148–4185; `intel_runtime_pm_disable_interrupts()` ~4193–4199; `intel_synchronize_irq()` ~4223 |
| [Linux `kernel/irq/manage.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/kernel/irq/manage.c) | `57eff26fa646a4c818a60ed85fe12950eaee0d77` | `__synchronize_irq(desc)` ~118–132 handles IRQ descriptor, hardirq and threaded handler |
| [NetBSD `sys/kern/subr_xcall.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_xcall.c) | `4541f0887c578bee46f51b8f4fd3c7b845170c11` | `xc_barrier(0)` ~300 uses `xc_broadcast(..., xc_nop)` + `xc_wait()` |

## IRQ routing in the pinned default x86 PCI implementation

```text
NetBSD i915 intel_irq_install()
  ├─ MSI enabled: pci_msi_alloc_exact() or inherited PCI interrupt handle
  │   └─ pci_intr_establish_xname(…, IPL_DRM, intel_irq_handler, …)
  │       └─ PCI default (unless chipset override):
  │           x86_pci_msi_establish()
  │             └─ pci_msi_common_establish()
  │                 └─ intr_establish_xname(…, IST_EDGE, …)
  └─ MSI disabled:
      pci_intx_alloc()
        └─ pci_intr_establish_xname(…, IPL_DRM, intel_irq_handler, …)
            └─ PCI default (unless chipset override):
                pci_intr_find_intx_irq()
                  └─ intr_establish_xname(…, IST_LEVEL, …)

NetBSD i915 intel_irq_uninstall()
  └─ pci_intr_disestablish(pa_pc, pci_intrcookie)
      └─ chipset-specific override if present, else intr_disestablish(cookie)
          └─ intr_disestablish_xcall() on bound CPU
              ├─ disable local interrupts
              ├─ mask the underlying interrupt source
              ├─ clear local pending bit and REMOVE handler from source chain
              ├─ update per-CPU interrupt masks
              ├─ delete route if no handler remains; otherwise conditionally unmask
              └─ free and return after cross-call completion
```

The x86 PCI API checks the chipset `PCI_OVERRIDE_INTR_ESTABLISH` / `PCI_OVERRIDE_INTR_DISESTABLISH` hooks **first**. Therefore the above default chains are proven for the pinned default x86 implementation, **not** a proof that the actual HP PCI chipset uses no override or always chooses MSI rather than INTx. Inspect target PCI identity, runtime interrupt allocation and actual `pdev->msi_enabled` before claiming which branch HP exercises.

### Different lifetimes matter

1. **Interrupt handler installation:** Both MSI's `IST_EDGE` and legacy INTx's `IST_LEVEL` ultimately pass a handler through `intr_establish_xname()` and bind it to `ih->ih_cpu`. Setup updates the handler chain on that CPU through a targeted cross-call and unmasks/reroutes the source. The i915 driver retains the returned cookie as `dev_priv->pci_intrcookie`.
2. **Interrupt handler disestablish:** `pci_intr_disestablish()` uses the chip override if present, otherwise `intr_disestablish(cookie)`. `intr_disestablish()` obtains `cpu_lock`, executes `intr_disestablish_xcall` either locally or using `xc_unicast(0,...,ih->ih_cpu)` plus `xc_wait()`. The target CPU masks the interrupt, removes the handler from its list, and restores/re-routes remaining handlers where appropriate. **This is destructive teardown, not a reusable `synchronize_irq(irq)` while keeping IRQ registered.**
3. **Masking is not a per-handler no-op:** `intr_mask(ih)` reaches `intr_mask_xcall` and increments the **shared `intrsource->is_mask_count`**. On transition 0→1 it calls `pic_hwmask` on the underlying source; `intr_unmask` decrements and may trigger pending edges. On shared INTx this can affect unrelated devices' handlers; it also changes interrupt-delivery semantics on MSI. Do not use mask/unmask as a trivial substitute for an IRQ-drain barrier without explicit shared-line ownership and ordering guarantees.
4. **Existing i915 runtime suspend path:** `intel_runtime_pm_disable_interrupts()` resets hardware IRQs, marks runtime IRQ disabled, then calls `intel_synchronize_irq()`. The NetBSD branch still calls **`xc_barrier(0)`** (all CPUs, low-priority NOP), *not* `intr_disestablish`, so it leaves `pci_intrcookie` registered during suspend. This separation is intentional at the level of lifetime: resume can reprogram IRQs without reestablishing the PCI handler.
5. **Linux reference distinction:** `synchronize_irq(irq)` is descriptor-specific and explicitly waits for in-flight hardirq work and associated threaded handlers. The fact that NetBSD's targeted `intr_disestablish_xcall` synchronously removes a handler **does not prove** `xc_barrier(0)` alone has identical IRQ quiescence guarantees. Conversely, this static code review does not demonstrate a failure on the actual HP system.

## Concrete acceptance matrix (do not mark runtime PASS)

| Contract | Pinned source finding | Remaining requirement |
|---|---|---|
| Default MSI route | MSI via `intr_establish_xname(IST_EDGE)` | Verify HP selected MSI and chipset hook at runtime |
| Default PCI INTx route | INTx via `intr_establish_xname(IST_LEVEL)` | Verify actual fallback, interrupt sharing and routing |
| Disestablish lifetime | `xc_unicast` to assigned CPU, remove handler under disabled local IRQs | **Do not call in runtime suspend** without re-establishment design; target state NOT_VERIFIED |
| `intr_mask` effects | Masks source (not isolated handler), records mask count, unmask replays pending non-level events | Need shared IRQ correctness before proposing any mask-based 0047 |
| NetBSD IRQ synchronization | `xc_barrier(0)` crosses CPUs; no explicit PCI IRQ descriptor argument | Independently establish quiescence under CPU affinity, active IRQ, and suspend ordering |
| AUX 0013 | Checks `!cold && drm.irq_enabled && runtime_pm.irqs_enabled` for interrupt-backed wait | Disabling IRQ after branch choice may force up to 10ms condition-variable timeout; MMIO availability NOT_VERIFIED |
| IRQ failure 0046 | Separate candidate clears stale runtime IRQ flag in failed install unwind | Native compile / real failure injection NOT_RUN |
| 0045 eDP | Separate 16-mutant source regression remains AUTHORED | NOT_RUN per prior provider denial; no reroute |
| Full project | 300 Linux→NetBSD semantic rows still OPEN | G01–G09 independent early console and stock-kernel recovery before HP build/boot, full DRM/TTM+RTL and real KMS/WPA2 |

## Next narrow engineering route

No new 0047 C patch is justified from the current evidence. The next safe source questions are:

- Verify with pin-consistent NetBSD/amd64 interrupt-vector dispatch that **after i915 IRQ reset and `runtime_pm.irqs_enabled=false`**, a low-priority xcall on each CPU cannot overtake still-active hardirq processing, including pending delayed or non-maskable paths. Keep any “drained” conclusion open until proven.
- Determine the exact HP PCI MSI vs INTx/override branch and the interrupt allocation cookie on the physical HP via authorized read-only diagnostic methods when genuinely available. Do **not** infer it from common Cherryview configuration or a generic laptop label.
- Design bounded source/runtime regression: IRQ still registered and active, AUX 0013 condition wait in-flight when suspend disables interrupts, resume completes postinstall, no 10ms timeout misdiagnosed as permanent lock; separately MSI fault and INTx shared-handler behavior. Actual execution **NOT_RUN**.
- Consider a NetBSD-native per-handler quiescence API only if its *own* implementation and documented lifetime/locking semantics have been verified. Do not import Linux's `synchronize_irq()`, OpenBSD's `intr_barrier()`, or use `pci_intr_disestablish()` in place of a passive wait.

**No kernel, bootloader or active i915 C changed in this task.** Candidates 0013, 0014, 0043, 0044, 0045, 0046 remain independent and unintegrated. Source analysis itself is not proof of an executable kernel, physical KMS, WLAN, or IRQ safety. Governance material PRE/POST: `Agent-Governance/state/events/hp-i915-amd64-pci-msi-intx-irq-lifecycle-20261019.jsonl`.
