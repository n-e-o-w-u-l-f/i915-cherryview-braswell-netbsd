# i915 IOSF QoS early-probe unwind — 2026-10-19

**Status:** source-confirmed bug and separate candidate `0042`, **regression execution blocked**, not native-accepted, not installed on HP.

**Source-ABI correction (2026-10-19):** The original description of an actual **QoS resource leak** was inaccurate for the pinned NetBSD implementation: `sys/external/bsd/drm2/include/linux/pm_qos.h` defines a dummy request object and no-op add/update/remove functions. Patch `0042` restores *structural* early-resource unwinding (including real mutex/uncore cleanup) and upstream Valleyview-only conditions; it cannot restore CPU-latency enforcement or leak a live QoS request in this shim. `sys/external/bsd/drm2/include/asm/iosf_mbi.h` also makes PUNIT acquire/release no-ops. The complete [runtime ABI blocker audit](HP_I915_NETBSD_IOSF_PUNIT_QOS_SHIM_GAP_20261019.md) supersedes any implication of real QoS/MBI parity. Patch/test execution remains blocked and acceptance OPEN.

## Frozen source evidence

Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab` `drivers/gpu/drm/i915/vlv_iosf_sb.c` (`1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758`) initializes the IOSF mutex for VLV/CHV but calls `cpu_latency_qos_add_request`/`remove_request` **only on `IS_VALLEYVIEW`**. Frozen NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6` `sys/external/bsd/drm2/dist/drm/i915/i915_drv.c` (Git blob `bf64ff40059fc38188f6f3d7b55bef9793abeb57`, SHA256 `88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8`) registers `pm_qos_add_request` unconditionally in `i915_driver_early_probe`, and removes it only in the normal `i915_driver_late_release`.

The original error path in `i915_driver_early_probe`:
- On `i915_workqueues_init` failure, **returns directly**, bypassing previously initialized mutex/uncore and QoS cleanup.
- On subsequent S0IX allocation or power-domain failure, jumps through `err_workqueues` and destroys resources, but **does not remove `sb_qos`**.
- `i915_workqueues_init` already invokes `destroy_workqueue(dev_priv->wq)` internally if allocating its *second* queue fails. The outer error handler **must not** call `i915_workqueues_cleanup` again after a failed initial workqueue setup, because that can double-destroy the first queue.
- `intel_sideband.c` applies the PUNIT QoS *update* only for `IS_VALLEYVIEW`. Thus the unconditional QoS registration for Cherryview has no matching PUNIT use in this frozen implementation.

## Candidate 0042

`candidates/0042-netbsd11-i915-iosf-qos-failed-probe-unwind.patch` makes four minimal changes **only to NetBSD i915_drv.c**:
1. Scope QoS registration to `IS_VALLEYVIEW`, preserving mutex initialization for all existing platforms.
2. Direct a failed `i915_workqueues_init` to a new `err_early_resources` label **after** the existing workqueue cleanup label, avoiding double destroy.
3. Add platform-gated QoS removal at this shared early-resource cleanup label, reached after both failure paths.
4. Scope normal `i915_driver_late_release` QoS removal to Valleyview, matching Linux.

All other lifetime ordering, GEM, display, IRQ and device structures remain unchanged. **No production code was installed or compiled.**

## Test and execution limitation

`tests/test_chv_iosf_qos_early_probe_unwind.py` is a persistent regression fixture which pins frozen Linux and NetBSD source identity, applies the candidate into a **temporary scratch tree**, validates the actual C function/control-flow labels and early/normal error cleanup, rejects a duplicate patch, performs byte-exact reverse, includes 18 platform/error-stage source-derived model scenarios and eight negative source mutations.

The first attempt to run it on Legion through the established connected execution channel was **blocked by platform safety checks** before output. The test is **not PASS** and no code execution, compiler result, patch-application result or negative-case result is claimed. The blocked operation was not retried through alternate tools, hosts or users.

## Remaining mandatory gates

A successful legitimate test run is required before accepting the candidate. Then verify the actual NetBSD QoS shim, mutex lifetime and failure edges natively; check CHV PCI attach and any runtime probe-to-teardown race; integrate with independent rollback. Entire `vlv_iosf_sb.c` and `i915_drv.c` semantics are not accepted by this patch. **All 300 outstanding Linux i915 units remain incomplete**; no native HP compile/link, boot menu or test kernel change has occurred.
