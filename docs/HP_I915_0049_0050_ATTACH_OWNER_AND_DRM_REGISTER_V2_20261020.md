# HP-I915 — staged 0049 attach-owner and 0050 DRM registration v2, with 0009 dependency

Date: 2026-10-20. PROJECT: HP-I915. **Work branch `work/hp-native-drm-stage-replay-20261015`; no production NetBSD C integration, HP boot/install, or native kernel build.**

Source HEAD before this step: `e4a3595663998de9e3363031dcf39f834e386157`. Pinned target **NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`**, Linux reference `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`. Existing 0008 and 0009 stayed unchanged. This step implements **new, separate candidate patches** from the completed Deep Research rather than claiming the old 0008 is integration safe.

## Concrete source defects and fixes

### 0049: NetBSD i915 attach task-owner cleanup

Source: [pinned NetBSD i915_pci_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c), blob `9798385b02f247c08db9b16624d5ddc9d11a8ca5`.

On the original path, `i915drmkms_attach_real` assigns `sc->sc_task_thread = curlwp` and calls `error = -i915_driver_probe(...)`. A negative return logs and returns immediately, without clearing that field. Detach later asserts `sc->sc_task_thread == NULL`. A valid negative probe plus subsequent detach can reach that stale-owner assertion; **the behavior was not reproduced on HP**.

**New [0049 candidate](../candidates/0049-netbsd-i915-attach-probe-error-owner-reset.patch), Git blob `126334e9da25a2398e99530aa4cbaa7eaa20a455`:**
```c
if (error) {
        /* A failed probe must not leave the attach LWP as task owner. */
        KASSERT(SIMPLEQ_EMPTY(&sc->sc_tasks));
        atomic_store_relaxed(&sc->sc_task_thread, NULL);
        aprint_error_dev(self, "unable to register drm: %d\n", error);
        return;
}
```
The guard intentionally detects, **rather than silently discards**, any pending tasks. The audited NetBSD `linux/async.h` implements `async_schedule` synchronously; the 0050 registration failure occurs before fbdev task scheduling. Other future failure paths with queued work require an explicit owner-safe task completion/cancellation protocol. The candidate does **not** prove this is universally safe for every partial-probe path.

### 0050: propagate DRM registration failure without unpaired core teardown

Sources: [pinned i915_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.c), blob `bf64ff40059fc38188f6f3d7b55bef9793abeb57`, and [pinned drm_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/drm_drv.c), blob `f91332cbebb57ab9a6ee3e1955722663df7e4929`.

Original `i915_driver_register` is void and does not propagate a failed `drm_dev_register`. The old pre-existing [0008](../candidates/0008-i915-drm-registration-unwind-netbsd11.patch), blob `6634a4d122d2e8524a14e60414b5043075caf3a0`, adds return propagation **but also calls `drm_dev_unregister`** after a failed `drm_dev_register`.

For the pinned `create_compat_control_link` `-ENOMEM` case, the DRM core itself already jumps to `err_minors` and releases primary/render minors **before** `dev->registered = true`. Calling `drm_dev_unregister` again would invoke `drm_modeset_unregister_all` before modeset registration. Unlike connectors, pinned encoder/CRTC/plane early-unregister loops lack a registration-state guard; a double or unpaired cleanup is not justified by the frozen call contract. Separately, `drm_dev_register` still ignores the return of `drm_modeset_register_all`; **0050 does not address that additional error class**.

**New [0050 candidate](../candidates/0050-netbsd-i915-drm-register-rollback-v2.patch), Git blob `d8cf75f69bccc078bc457dcfdfc1d90e79e6caa6`** introduces `int i915_driver_register`, error propagation and PMU/GEM unregister. On a failed core registration it intentionally does **not** invoke `drm_dev_unregister`. An independently anchored deep-probe rollback begins at `out_cleanup_registration`, including OpRegion release, GEM/GVT/modeset/power-domain/HW release and transfer to memory/MMIO unwind. **Still not native verified**: ordering across all possible partially constructed GEM/atomic modeset objects, and whether `drm_atomic_helper_shutdown` must be present in this failed-probe branch. That call was not added without native proof.

### 0009: keep explicit prerequisite

[Existing 0009](../candidates/0009-netbsd-opregion-optional-asle-cleanup.patch), blob `b257d451560584a86c6f092dcde6b0b69b0e33c8`, remains unmodified. Pinned [intel_opregion.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c) blob `2cbe50d346b20bb9a23382993c361e7db94b6e9d` can have a valid header without an ASLE mailbox; 0009 reads `asle->rvds` conditionally on an actually mapped RVDA before header unmap. For the observed setup path `rvda != NULL => asle != NULL`. Independent 0010 remains optional RVDA-map-null guard, not included automatically.

## Executed evidence and limitations

- **Real pinned GitHub-source patch application in an independent JS unified-diff checker**: 0049, 0050 and 0009 each matched the exact target source, all hunks consumed with verified old/new counts, offsets and context: **3/3 PASS**. For 0050 specifically **four hunks**; resulting transformed source met **8/8 relevant contract checks**: error-owner release, queue assertion, registration error propagation, no unmatched DRM core unregister, PMU/GEM once, deep rollback and 0009 guard. A first independent parser run rejected 0009 because the script omitted legal function text after the `@@` hunk delimiter; parsing was corrected, source readback repeated and **3/3 PASS**. This was a local test-parser issue, not a failed NetBSD build.
- [New pinned read-only validator](../tests/test_i915_0049_0050_pinned_apply.py), Git blob `5189c395ba41e830ee1efb40f09a839ff2383d9e`: local Python **`--self-test` 2/2 PASS**, `py_compile` PASS, local `git hash-object` **exactly equal** to published GitHub blob. The full validator checks a clean pinned `NetBSD/src` revision and file blobs, the three patch blob SHAs, and calls `git apply --check` separately for each patch (read-only) with a full checkout. The **full NetBSD checkout CLI was NOT_RUN**, because none was verified in the local sandbox.
- Native NetBSD i915/DRM C object/kernel compilation, negative DRM-core registration fault injection, actual device detach, HP physical KMS, RTL8723BE WPA2, independent stock-kernel recovery and G01–G09 gates: **NOT_RUN/NOT_VERIFIED**. No production driver, kernel, bootloader or HP machine was changed.
- Previously provider-blocked 0047+0048 composed candidate creation, 0045 16-mutant suite and Legion remote exec remain **NOT_RETRIED**. Do not treat these source-only 0049 and 0050 as authorization to bypass those refusals.

### Repeatable native gate once a permitted pinned checkout exists
```sh
python3 -B tests/test_i915_0049_0050_pinned_apply.py --self-test
python3 -B tests/test_i915_0049_0050_pinned_apply.py \
  --netbsd-tree /path/to/clean-pinned-netbsd-src \
  --candidates /path/to/i915-work-branch/candidates
```
This is a patch apply/source fingerprint gate, **not** a kernel compile or a signal to boot HP. The next acceptance sequence is native source patch application in a dedicated worktree, NetBSD amd64 C compilation and fault-injected registered-minor+probe rollback, `sc_task_thread` detach invariant, then one coordinated i915+RTL candidate kernel. Before a physical test independently establish G01–G09, early console/logging and verified stock-kernel boot fallback.

Governance: `Agent-Governance/state/events/hp-i915-register-0008-v2-owner-20261020.jsonl`, owner `state/projects/HP-I915.md`, pointer `handoffs/HP-I915-CURRENT.md`.
