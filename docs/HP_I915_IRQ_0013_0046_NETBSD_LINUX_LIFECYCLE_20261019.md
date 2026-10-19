# HP-I915 — 0013 IRQ-aware AUX wait: NetBSD/Linux lifecycle and IRQ-install error rollback 0046

Date: 2026-10-19  
State: **SOURCE-VERIFIED DIFFERENCE / UNINTEGRATED 0046 CANDIDATE / EXECUTION NOT_RUN**  
i915 source branch before work: `1a28106ebd732b824175e24cecab12fd76d87199`  
NetBSD pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`  
Linux pin: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Frozen source identities / precise functions

- NetBSD [`i915_irq.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_irq.c), Git blob `73f8deec8404481c4e457bb72631456b3b11ff69`, `intel_irq_install():4059–4139`, `intel_irq_uninstall():4148–4184`, `intel_runtime_pm_disable_interrupts():4193–4198`, `intel_runtime_pm_enable_interrupts():4207–4212`, `intel_irqs_enabled():4215–4221`, `intel_synchronize_irq():4223–4231`.
- NetBSD [`i915_drv.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.c) blob `bf64ff40059fc38188f6f3d7b55bef9793abeb57`, system suspend `i915_drm_suspend():1757–1810`, system resume `i915_drm_resume():1908–1970` and runtime suspend/resume `~2600–2710`.
- NetBSD [`display/intel_dp.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c) blob `1dd8858b2d331906190258c8602af55966ff986c`, `intel_dp_aux_wait_done():1183–1221`.
- Linux [`display/intel_dp_aux.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/display/intel_dp_aux.c) blob `3cb07b0a901cff7291eca9479f24128989d6c0e7`, `intel_dp_aux_wait_done():59–89`.
- Linux [`display/intel_parent.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/display/intel_parent.c) blob `a5e41ea66921398ee0f38911ac6266ed07f4bed7`; `intel_parent_irq_enabled(display)` calls `display->parent->irq->enabled(display->drm)`.
- Linux [`i915_driver.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/i915_driver.c) blob `ce6d20958320c1f91a50678230eb96f88f0b357b`, `i915_display_parent_interface.irq=&i915_display_irq_interface` at ~754.
- Linux [`i915_irq.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/i915_irq.c) blob `932409b943ad252c2ad63b91384385fba0936a99`, `i915_display_irq_interface.enabled = _intel_irq_enabled`, which calls `intel_irqs_enabled(to_i915(drm))`, returning `dev_priv->irqs_enabled`. Linux `intel_irq_suspend` resets hardware IRQ and this one flag to false before synchronization; `intel_irq_resume` sets it true then reinstalls IRQ. The Linux parent wrapper is therefore **not** a second independent hardware confirmation.

## NetBSD IRQ state transitions — source facts, not runtime proof

| Transition | `drm.irq_enabled` | `runtime_pm.irqs_enabled` | Source-proven behavior |
|---|---|---|---|
| `intel_irq_install()` begins | `true` | `true` | Both marked active **before** reset / PCI IRQ allocate/establish; transient optimistic state is part of inherited install ordering |
| `intel_irq_install()` PCI MSI/INTx allocate/establish **fails** (frozen NetBSD) | **`false`** | **remains `true`** | **Confirmed mismatch:** `if (ret<0)` only resets `drm.irq_enabled` in frozen `i915_irq.c:4132–4135` |
| Install succeeds and executes `intel_irq_postinstall()` | `true` | `true` | Successful return after postinstall |
| `i915_drm_suspend()`: `intel_runtime_pm_disable_interrupts()` | no change (`true` after valid install) | `false` | Hardware IRQ reset, flag false, then `intel_synchronize_irq()`; `intel_hpd_cancel_work()` follows |
| `i915_drm_resume()`: `intel_runtime_pm_enable_interrupts()` | no change (`true` after valid install) | `true` | Sets flag before reset and postinstall; AUX needed by modeset resume |
| `intel_irq_uninstall()` | `false` | `false` after cleanup | Resets main flag, releases PCI IRQ and HPD work, then clears runtime flag; early return occurs when main flag already false |

A `true` value during install or resume is **not atomic proof** that IRQ handlers are already registered and all workqueues fully ready. Flags are needed for the decision to use an IRQ-driven wait, but this review does **not** establish synchronization against concurrent bringup/shutdown.

## Candidate 0013 remains unchanged and independently staged

[0013](../candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch), exact blob `b38ebdeba42e6512371a2a22c2f1ea0a6c9ac876`, changes NetBSD `intel_dp_aux_wait_done()` from `if (!cold)` to:

```c
if (!cold && i915->drm.irq_enabled &&
    i915->runtime_pm.irqs_enabled) {
    /* Original interrupt-backed wait path. */
} else {
    /* Existing polling fallback: wait_for_atomic(C, timeout_ms). */
}
```

That fails **closed** when either IRQ flag is false. In the frozen install-failure state, checking only `runtime_pm.irqs_enabled` would misclassify failed IRQ registration. During system/runtime suspend, `drm.irq_enabled` by itself could misclassify disabled hardware IRQ. Both conditions are hence supported by the older NetBSD lifecycle, whereas pinned Linux `intel_parent_irq_enabled` follows a single parent-owned `irqs_enabled` boolean.

**Still open:** whether a concurrently changing status flag at the exact register wait point is sufficient; whether 10 ms atomic polling and `status` tracing are always valid after display power wells suspend; NetBSD `intel_synchronize_irq()` uses `xc_barrier(0)`, Linux `synchronize_irq()`; exact OS-level equivalence and physical AUX completion are **NOT_VERIFIED**.

## New isolated repair 0046 (not applied to any kernel)

[Candidate 0046](../candidates/0046-netbsd11-i915-irq-install-failure-clear-runtime-irq-flag.patch), Git blob `e3772cfcfb7299b01edc25f4914a75aa30091841`, targets **only** `sys/external/bsd/drm2/dist/drm/i915/i915_irq.c` at old `4131–4140`. It augments the existing `ret < 0` rollback with:

```c
dev_priv->drm.irq_enabled = false;
/* A failed IRQ install must also disable the AUX wait IRQ gate. */
dev_priv->runtime_pm.irqs_enabled = false;
return ret;
```

Effect **in code**: after an unsuccessful PCI IRQ establish/allocation, both exposed flags end false rather than diverging. It preserves the successful installation path, suspend/resume ordering and 0013's conservative two-flag check. Source check used uniquely matching frozen branch snippet, verified inserted text, byte-identical static inverse. No source was applied or rebuilt; **real git apply, unit tests, NetBSD C compiler and HP IRQ-fault injection NOT_RUN**.

This repair addresses an install **error-path state bug**, not the full transient IRQ registration race. It is a separate, staged candidate, and its source semantics must be validated with actual authorized compilation and failure injection before integration.

## Acceptance and release gates

1. **Source-only now:** candidate 0013 + 0046 affect **different source paths** (`display/intel_dp.c` vs `i915_irq.c`); thus no same-file hunk overlap. No guarantee that all seven candidates in the complete tree compose textually or semantically without actual checking.
2. **Executable scratch acceptance (not authorized via prior denied equivalent source tests):** if scope genuinely changes, run pinned `git apply --check`/apply/reverse and 0013/0046 error-path negative mutation tests on scratch input. Record actual exit codes and exact restoration. Do not reroute denied testing merely by changing host/connector.
3. **Native NetBSD:** compile `i915_irq.c` in full DRM/i915 ABI/TTM environment and inspect real PCI/MSI/INTx failure behavior with legal test harness; no claims yet.
4. **Hardware/boot:** preserve G01–G09 independently established early console and working standard-kernel rollback before any HP i915/RTL kernel install/boot; then separately validate AUX polling, display KMS, RTL attach/WPA2 and absence of panic/black screen.

**Do not mark any of the 300 Linux→NetBSD semantic rows accepted based solely on this static analysis.** Historical 323 i915-unit source coverage is not proof of linked or running driver. Evidence and PRE/POST: `Agent-Governance/state/events/hp-i915-irq-0013-install-failure-source-repair-20261019.jsonl`.
