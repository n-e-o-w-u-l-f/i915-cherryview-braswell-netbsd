# HP-I915 — NetBSD/amd64 vector pending state, low-priority xcalls and Cherryview IRQ quiescence

Date: 2026-10-19.  
Status: **PINNED SOURCE-ONLY ANALYSIS; NO DRIVER C CHANGE; RUNTIME IRQ QUIESCENCE OPEN**.  
i915 branch before this document: `3a1359b45a7a77e7f620cd253305751ae3d67167`.  
NetBSD pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Linux reference pin: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Verified frozen source contracts

| Kernel source | Exact Git blob | Relevant behavior |
|---|---|---|
| [NetBSD amd64 `vector.S:354–438`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/amd64/amd64/vector.S) | `99d18e153bfe8754b402848a9b411b3814f9692a` | Generic `INTRSTUB` captures `ISOURCES`, compares IRQ priority (`ILEVEL`), executes `IH_FUN` from `IS_HANDLERS`; deferred branches set per-CPU `IPENDING` or `IMASKED`. |
| [NetBSD amd64 `spl.S:282–370`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/amd64/amd64/spl.S) | `0d6a246005304bb028290e15900f78993ee02dcc` | `Xspllower` and `Xdoreti` select `IPENDING & IUNMASK[current IPL]`, clear bit and jump to `IS_RECURSE`/`IS_RESUME`. Pending interrupt delivery is a **separate** phase. |
| [NetBSD x86 `intr.c:1050–1115`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/intr.c) | `7fe7a1813dbe82dbf76b5bddc32d84bc15bff580` | `intr_mask_xcall` changes the **source** mask count; on unmask, for a deferred `IMASKED` event of non-`IST_LEVEL` type, it can restore `IPENDING` and explicitly trigger processing. |
| [NetBSD `subr_xcall.c:255–311,390–479`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_xcall.c) | `4541f0887c578bee46f51b8f4fd3c7b845170c11` | `xc_barrier(0)` broadcasts `xc_nop`; `xc_lowpri` wakes a **per-CPU kernel thread** via condition variable and waits for completion count. No `IPENDING`/`IMASKED` inspection is part of this implementation. |
| [NetBSD i915 `i915_irq.c:1610–1685`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.c) | `73f8deec8404481c4e457bb72631456b3b11ff69` | `cherryview_irq_handler` first tests `intel_irqs_enabled(dev_priv)`, returning `IRQ_NONE` before i915 MMIO if false. Otherwise it reads `GEN8_MASTER_IRQ`/`VLV_IIR`, processes GT/display/HPD and re-enables controls. |
| [NetBSD i915 `i915_irq.c:3998–4053,4190–4231`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.c) | Same blob | Cherryview chooses the `cherryview_irq_reset` and `cherryview_irq_handler` branches. Suspend runs `intel_irq_reset` → `runtime_pm.irqs_enabled=false` → `xc_barrier(0)`; resume sets the flag true before reset/postinstall. |
| [NetBSD i915 `intel_dp.c:1183–1222`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c) | `1dd8858b2d331906190258c8602af55966ff986c` | In the frozen source, AUX waits use a condvar unless `cold`; candidate 0013 adds fail-closed combined IRQ state and selects 10 ms `wait_for_atomic` fallback when either IRQ flag is false. |
| [Pinned Linux `kernel/irq/manage.c:~118–157`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/kernel/irq/manage.c) | `57eff26fa646a4c818a60ed85fe12950eaee0d77` | `synchronize_irq(irq)` refers to a specific IRQ descriptor and checks hardirq/pending and threaded completion. Not the same *specified interface* as NetBSD CPU cross-call completion. |

## Device IRQ vector behavior: precise cases

1. **Handler executes now:** `INTRSTUB` enters the actual ISR chain (`call *IH_FUN`), then restores the prior CPU interrupt level via `Xdoreti`. This is **hard-IRQ execution on that CPU**, not a user-space or low-priority xcall thread.
2. **Blocked by current IPL:** the assembly's `10:` branch sets `CPUVAR(IPENDING)` and returns using `INTRFASTEXIT`. `Xspllower`/`Xdoreti` can process pending bits when lower IPL permits. The xcall completion counter does not directly represent this queue.
3. **Source is masked:** if `IS_MASK_COUNT != 0`, branch `12:` sets `CPUVAR(IMASKED)` and clears the corresponding `IPENDING` bit. The unmask path may restore `IPENDING` **for non-level-sensitive IRQ sources**, then request processing; for `IST_LEVEL`, the comment explicitly relies on hardware reassertion instead. Thus MSI edge and shared INTx level deferred cases are not interchangeable.
4. **CPU cross-call:** `xc_barrier(0)` signals every running CPU's `xcall/N` **kernel thread** and waits for the delivered `xc_nop` call to complete. This establishes cross-call completion and has useful CPU scheduling-order implications, but it **does not explicitly inspect or clear** either `IPENDING` or `IMASKED`. No pinned source contract equates its completion to a *device-specific pending MSI/INTx flush*.

### Bounded i915 consequence: avoid both overclaim and overpatch

- An i915 IRQ handler that is **already executing continuously** on a CPU normally prevents a low-priority thread on the same CPU from running simultaneously. Therefore xcall completion can be meaningful evidence about *previously executing* CPU handlers. Yet this observation alone does not cover an interrupt held in `IMASKED`, hardware pending state or an IRQ newly delivered after xcall completion. It is **not** a certified `synchronize_irq()` replacement.
- On Cherryview, the handler begins with `if (!intel_irqs_enabled(dev_priv)) return IRQ_NONE`. A *new* handler entry after the runtime flag becomes false should therefore avoid subsequent i915 register accesses **provided the flag state is observed correctly**. This does not prove that a handler which read the old `true` value just before suspend has completed, or that the MMIO reset/flag publication is CPU-synchronized.
- `intel_runtime_pm_disable_interrupts()` currently performs **reset → flag=false → xcall barrier**. Hardware IRQ reset is expected to suppress new device requests, but source alone cannot certify that all already queued APIC/MSI or shared-level events are absent when the barrier returns. The ordering and architecture matter.
- Patch [0013](../candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch) makes an **entry-time** decision: either timed condvar or polling. If IRQs are disabled *after* condvar selection, the ongoing wait does not automatically reselect polling. It has a finite approximately 10 ms timeout; calling this a permanent deadlock without a hardware reproduction would be incorrect.
- Patch [0046](../candidates/0046-netbsd11-i915-irq-install-failure-clear-runtime-irq-flag.patch) addresses a **separate confirmed install-error unwind** of `runtime_pm.irqs_enabled`; it cannot establish global IRQ synchronization. Both 0013 and 0046 remain **unintegrated**.

## Source-anchored acceptance scenarios (all NOT_RUN)

| Scenario | Requested observations | Unsafe inference to reject |
|---|---|---|
| CHV IRQ executing when suspend begins | Handler-entry/exit count; reset and flag switch; `xc_barrier` return; no stale MMIO after actual power loss | CPU xcall completion **guarantees** Linux-equivalent device IRQ drain |
| MSI edge deferred due IPL | `IPENDING` before/after priority lowering; correct IRQ gating and drain before MMIO off | One xcall NOP necessarily clears pending bits |
| MSI while source masked | `IMASKED` → unmask → possible `IPENDING` restoration; no late unsafe MMIO | Masked state is equivalent to dropped event |
| Shared INTx level during suspend | Other handlers' delivery and hardware level reassertion; i915 early guard | `intr_mask` is a private i915-only operation |
| AUX 0013 IRQ disabled midwait | Timed wakeup/expiry and return status; power-well access, no false success | Finite timeout implies physical correctness |
| Resume after late pending IRQ | Observe flag=true/reset/postinstall ordering; HPD work and KMS stability | No race because all IRQs were previously synchronized |

## Next engineering action

No new C candidate `0047` is justified yet. A source-justified next review should identify CHV hardware IRQ mask/reset posting semantics and exactly what x86 APIC can deliver after the GPU reset, then design a minimal scope-preserving lifetime guard **only if** a real gap remains after the ISR early flag and existing xcall synchronization are considered. On hardware, record CPU IRQ affinity, actual MSI versus INTx, pending counts and callback timing via authorized read-only tooling; **do not** substitute `intr_disestablish` or shared-source `intr_mask` in runtime suspend.

**Hard limits:** source-only document and its GitHub readback do not prove a NetBSD kernel compiled, linked, booted, or rendered KMS; `0045` 16-mutant regression remains **AUTHORED NOT_RUN** after provider denial and cannot be rerouted. Combined i915+DRM/TTM+RTL, physical HP KMS, RTL WPA2 and independent G01–G09 early console/working standard-kernel rollback **NOT VERIFIED**. 300 Linux→NetBSD semantic rows remain OPEN; no HP kernel/bootloader mutation allowed from this review.

Canonical governance PRE/POST: `Agent-Governance/state/events/hp-i915-amd64-vector-pending-xcall-quiescence-20261019.jsonl`.
