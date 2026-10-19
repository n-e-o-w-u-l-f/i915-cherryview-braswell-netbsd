# HP-I915 — NetBSD xc_barrier(0) vs Linux synchronize_irq(): AUX 0013 IRQ suspend contract

Date: 2026-10-19  
Outcome: **PINNED SOURCE COMPARISON VERIFIED; IRQ QUIESCENCE EQUIVALENCE UNPROVEN**  
No operative C change, no additional candidate, no application or execution of prior test suite.  
i915 branch before this review: `9ebe541a18b1ea50708e1806a09df30ae8f5fdd8`  
Frozen NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`  
Frozen Linux: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Exact source inventory

| Pin | Source / function | SHA blob / key behavior |
|---|---|---|
| NetBSD | [`i915_irq.c:4190–4230`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.c) | `73f8deec8404481c4e457bb72631456b3b11ff69` — `intel_runtime_pm_disable_interrupts()`: reset IRQ hardware, `runtime_pm.irqs_enabled=false`, `intel_synchronize_irq()`; latter is `xc_barrier(0)` on NetBSD |
| NetBSD | [`sys/kern/subr_xcall.c:289–310, 346–389`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_xcall.c) | `4541f0887c578bee46f51b8f4fd3c7b845170c11` — `xc_barrier(flags)` broadcasts `xc_nop` to all CPUs, waits for returned ticket via `xc_wait`; zero flags selects low-priority xcall |
| NetBSD | [`share/man/man9/xcall.9:74–142`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/share/man/man9/xcall.9) | `aae828b1b50a3b825a35837f02e4d7cfffb82ca7` — low-priority calls execute in remote CPU **thread context**, not interrupt context; high-priority xcalls via software interrupt are a separate flag |
| NetBSD | [`display/intel_dp.c:1183–1221`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c) | `1dd8858b2d331906190258c8602af55966ff986c` — NetBSD `intel_dp_aux_wait_done()` selects interrupt-backed condition-variable timeout whenever `!cold`, otherwise 10 ms `wait_for_atomic(C, timeout_ms)` |
| NetBSD | [`drm_wait_netbsd.h:304–349`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/drm/drm_wait_netbsd.h) | `411793f557dd2e45c44ccf9b83302d3e06bd3511` — `DRM_SPIN_TIMED_WAIT_NOINTR_UNTIL` checks held spinlock and process context, then waits for condition or finite timeout with `cv_timedwait` |
| Linux | [`drivers/gpu/drm/i915/i915_irq.c:1160–1210`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/i915_irq.c) | `932409b943ad252c2ad63b91384385fba0936a99` — IRQ suspend flag false and `intel_synchronize_irq(i915)` -> `synchronize_irq(to_pci_dev(i915->drm.dev)->irq)` |
| Linux | [`kernel/irq/manage.c:~118–157`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/kernel/irq/manage.c) | `57eff26fa646a4c818a60ed85fe12950eaee0d77` — `__synchronize_irq(desc)` synchronizes pending work, hardirq activity and associated interrupt threads for the **selected IRQ descriptor** |
| Linux | [`display/intel_dp_aux.c:59–89`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/display/intel_dp_aux.c) | `3cb07b0a901cff7291eca9479f24128989d6c0e7` — uses `intel_parent_irq_enabled(display)` for wait versus polling |

### Claim classification

**SOURCE VERIFIED:** `xc_barrier(0)` is a **CPU cross-call completion barrier**, implemented as a broadcast and wait for a no-op; it does not accept an i915 interrupt handle/descriptor. In the Linux comparison, `synchronize_irq(irq)` is **explicitly descriptor-specific**, with pending hardirq/interrupt-thread semantics. This is a significant difference in *specified guarantees*, not a proof that i915 on NetBSD crashes or that the cross-call cannot quiesce particular handlers in practice.

**SOURCE VERIFIED:** the NetBSD `xc_wait` API expects a sleepable, non-IRQ context and `xc_barrier(0)` uses the default low-priority task context. The same cross-call idiom appears in other NetBSD drivers (e.g., `sys/dev/pci/if_ixl.c` and `sys/dev/pci/if_vioif.c`) under functions named `*_intr_barrier`. Treat that as **usage evidence only**; it does not extend the public xcall API's stated guarantee to a Linux `synchronize_irq()` equivalent.

**SOURCE VERIFIED:** the NetBSD PCI `pci_intr_establish_xname` returns a cookie stored as `dev_priv->pci_intrcookie`; this cookie is used for `pci_intr_disestablish` on teardown. [NetBSD 11 PCI IRQ manual](https://man.netbsd.org/NetBSD-11.0/pci_intr_establish.9) documents establishment and disabling an associated IRQ handler, **not** a direct replacement for Linux's `synchronize_irq` while the device is still live. In particular, **do not use OpenBSD's `intr_barrier` as an assumed NetBSD API**.

## Patch 0013 interleaving analysis (bounded)

[0013](../candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch), Git blob `b38ebdeba42e6512371a2a22c2f1ea0a6c9ac876`, adds the two-flag gate `!cold && i915->drm.irq_enabled && i915->runtime_pm.irqs_enabled`. [0046](../candidates/0046-netbsd11-i915-irq-install-failure-clear-runtime-irq-flag.patch) separately fixes a frozen `intel_irq_install` failure-path flag mismatch; both are **UNINTEGRATED**.

| Interleaving | Source-derived effect | Verification gap |
|---|---|---|
| 0013 reads both flags **false** after IRQ suspend | Selects `wait_for_atomic(C, 10 ms)` polling rather than sleeping for IRQ wakeup | The register/uncore/power-domain must still be accessible; a false IRQ flag alone **does not guarantee** MMIO accessibility |
| 0013 reads both flags **true** and then another thread disables IRQs | Already selected a `DRM_SPIN_TIMED_WAIT_NOINTR_UNTIL` condition-variable wait. **No branch reselection** occurs in that invocation. It has a finite timeout, and final `status` is returned, so source review cannot label it an infinite sleep | Cross-CPU ordering, late wakeup vs reset, polling-retry behavior across transactions and whether timeout is tolerable |
| Runtime/system suspend executes `intel_runtime_pm_disable_interrupts` | Hardware IRQ reset → runtime IRQ flag false → `xc_barrier(0)`; code then cancels HPD workers | Cross-call barrier may be helpful, but **no pinned contract proves** it drains exactly all in-flight i915 hardirq and any threaded handler before suspend progresses |
| Runtime/system resume executes `intel_runtime_pm_enable_interrupts` | Runtime IRQ flag true **before** IRQ reset/postinstall; a transient optimistic IRQ state is deliberate inherited ordering | No simultaneous AUX waiter / IRQ postinstall test or proof of no premature sleeps |
| IRQ installation fails in frozen NetBSD | `drm.irq_enabled=false` while runtime flag remains true | 0013 fails closed via both-flag AND; isolated 0046 corrects unwound runtime state, but real failure injection NOT_RUN |

**Acceptance boundary:** Neither patch 0013 nor 0046 is sufficient to prove the full cross-CPU IRQ synchronization contract. We have *not* shown that NetBSD's `xc_barrier(0)` is defective on the actual HP, nor found a verified drop-in kernel API satisfying Linux `synchronize_irq` on a still-established NetBSD PCI IRQ. **Therefore do not stage an invented 0047 replacement**, guess an OpenBSD-only function, or edit the running i915 kernel based on this difference.

## Unblocked next work / release gates

1. With NetBSD kernel source for the exact target architecture, independently inspect interrupt dispatch/de-establish internals for the installed PCI MSI/INTx backend, including the actual ordering and whether `xc_barrier(0)` after reset+flag=0 provides enough *i915-specific* quiescence.
2. If a **verified NetBSD-native** per-handler IRQ-drain primitive is found, first document its lifetime/locking rules, process-context constraints and relation to `dev_priv->pci_intrcookie`; only then draft a narrowly scoped candidate patch.
3. Propose (do not claim executed) a sleep-vs-poll regression with IRQ disabled **before** AUX request, disable **while** condition-variable wait is already armed, and re-enable while a request is pending. Require meaningful timing/result logging, finite timeout, and lock-order invariants.
4. Separate sources, native NetBSD build, IRQ fault injection, real HP KMS and WLAN. **0045's 16 negative source mutations remain AUTHORED NOT_RUN** under prior denied execution scope. Do not reroute them through another host/tool.
5. No HP kernel install/reboot until the independent G01–G09 early console and standard-kernel rollback, plus full DRM/i915/TTM+RTL native readiness, are verified. **300 semantic rows remain OPEN.**

Governance PRE/POST: `Agent-Governance/state/events/hp-i915-irq-xc-barrier-aux-0013-contract-20261019.jsonl`. Read-only pinned source comparison is a bounded acceptance step; driver operation is **not** validated.
