# HP-I915 — NetBSD mountroot deferred detach and DRM registration failure contracts

Date: 2026-10-20 (Europe/Berlin). Status: **PINNED SOURCE-PROVEN CONTRACT GAPS; MODEL PASS; NATIVE/HARDWARE NOT_RUN**.
Parent objective is a functional Cherryview/Braswell i915 + DRM/TTM + RTL8723BE NetBSD 11 kernel with verified rollback; none of those release gates was closed by this audit.

## Pins / independently fetched primary sources

i915 branch `work/hp-native-drm-stage-replay-20261015`, starting HEAD `cdd25eea374394fde1bba9cc98da715fbe54ae7e`; first model-code publication `15ea7f887fbf9e6fb2003a5f9823f3be0cd8fc50`.
NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
- [subr_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_autoconf.c), Git blob `5ee8a7998b07fd570d7b1f67d23cdb814de63039`.
- [i915_pci_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c), blob `9798385b02f247c08db9b16624d5ddc9d11a8ca5`.
- [i915_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.c), blob `bf64ff40059fc38188f6f3d7b55bef9793abeb57`.
- [drm_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/drm_drv.c), blob `f91332cbebb57ab9a6ee3e1955722663df7e4929`.

## 1. Mountroot queue versus detach lifecycle

In frozen `config_mountroot(dev,func)`, when `root_is_mounted` is false, a `struct deferred_config` is added to `mountroot_config_queue` **without** `config_pending_incr(dev)`. On the normal mountroot thread path, `config_mountroot_thread` removes an entry, runs its callback with `dc->dc_dev`, and frees the entry; **no** `config_pending_decr` occurs there. When the root is already mounted, the callback instead runs inline.

In the same frozen NetBSD source, `config_detach_enter` waits only while `dev->dv_pending || dev->dv_detaching`, then enters `ca_detach`; it does **not** check `mountroot_config_queue`. Thus an as-yet unexecuted mountroot callback does not itself keep that device's detach gate closed. The driver `i915drmkms_attach` uses `config_mountroot(self, &i915drmkms_attach_real)`. **This is a source-demonstrated unguarded owner lifetime**, not evidence a specific physical HP race has occurred. Do not assume queue removal happens on detach; no per-device cancellation/unwind was demonstrated in the pinned code.

An additional path needs a separate source/liveness check: `config_deferred(dev)` calls `config_process_deferred(&mountroot_config_queue,dev)`, whose generic path unconditionally performs `config_pending_decr(dc->dc_dev)` after invoking the callback. Unlike `config_defer` and `config_interrupts`, `config_mountroot` did **not** increment this token. There is a static counter-contract mismatch **if** the queue entry reaches this generic processing path; exact scheduling/reachability and relevant external callers have NOT been established as a runtime bug.

Consequence for safe design: do not add an isolated `config_pending_incr` to mountroot or trivially clear the i915 thread owner. First unify **all** mountroot normal-thread, inline, generic-deferred and cancel/detach completion paths with exactly-once pending accounting and a device reference/lifetime contract; then validate with LOCKDEBUG/SMP and fault injection. Stock kernel boot fallback must be proven before HP trials.

## 2. DRM register error swallowed

Frozen `drm_dev_register(dev,0)` returns an `int`; it can fail when `create_compat_control_link` cannot allocate the control name (`-ENOMEM`). In NetBSD `drm_minor_register`, the Linux `device_add` path is excluded, but this name allocation path remains. On `drm_dev_register` failure, `drm_drv.c` unwinds minors and returns `ret`.

The frozen i915 `i915_driver_register` is `static void`: it logs a failed `drm_dev_register(dev,0)` but then continues initialization, including `intel_fbdev_initial_config_async`, rather than propagating the negative status. `i915_driver_probe` calls it without a return check and proceeds to a successful `return 0`. Hence a specific failed userspace registration can be reported as a successful probe. This is an independently sourced error-propagation defect, but complete, safe unwind of partially established subsystems still requires testing.

**No duplicate register candidate:** The repository already contains [candidate 0008](../candidates/0008-i915-drm-registration-unwind-netbsd11.patch), corresponding [generator](../tools/generate_register_failure_patch.py), and [pinned source-contract test](../tests/test_drm_registration_source_contract.py). The candidate is **UNINTEGRATED**. This review does not imply that calling `drm_dev_unregister` after an unsuccessful registration, or the entire candidate's cleanup order, is safe: inspect `dev->registered`, `DRIVER_LEGACY`, `drm_client`, minor/connector state, pmu/gem and i915 post-registration unwind against the frozen Linux and NetBSD implementations. Existing regression test was not run in this step.

## Test evidence and limits

- Via exact pinned GitHub source reads, **14/14 bounded contract predicates PASS**, covering both queue/worker/deferred paths, detach pending gate, i915 attach/failed probe, `drm_dev_register` negative return and swallowed i915 registration error.
- [Isolated Python failure-flow model](../tests/test_mountroot_register_model.py), Git blob `83363e4b0d53516d7a0f464ee4206369e77069c2`, local `python3 -B` **6/6 unittest PASS**, `py_compile` PASS; the tested local source's `git hash-object` exactly matched GitHub readback. This *models* hazards and counterfactual guard behavior, **not** NetBSD autoconf/DRM execution.
- Local raw GitHub retrieval attempted for the prior pinned-source oracle but DNS resolution of `raw.githubusercontent.com` failed (curl exit 6). No unauthorized bypass; previous script's actual `--self-test`/full checkout **NOT_RUN**. The GitHub connector was able to inspect the four real pinned sources independently.
- Native C compiler, full kernel link, real mountroot/detach, DRM userspace access, physical HP KMS/WPA2, early console and standard-kernel rollback all **NOT_RUN / NOT_VERIFIED**. No active source C, kernel, bootloader or host modified.

## NEXT (do not narrow parent objective)

1. Trace `config_deferred` caller reachability and `config_mountroot` cancellation/ownership with exact NetBSD source and run a targeted native regression on an authorized NetBSD worktree. Establish exactly-once token and device lifetime before any C modification.
2. Independently validate existing candidate 0008's specific `drm_dev_register(-ENOMEM)` failure and rollback: negative-path object model, native compiler, and runtime coverage for partially registered DRM minors. Avoid a second competing patch.
3. Integrate only independently validated source changes in one coordinated NetBSD kernel build with the separate RTL owner. Complete G01–G09 console/stock recovery before any HP install/boot. Retain 300 semantic units OPEN until traced and tested.

Previously provider-refused `0047+0048` composed candidate is NOT_CREATED and remains blocked; earlier denied `0045` sixteen negative mutants are NOT_RUN. Do not retry these via alternate executors or recast as this independent audit.

Governance event: `Agent-Governance/state/events/hp-i915-mountroot-drm-register-20261020.jsonl`.
