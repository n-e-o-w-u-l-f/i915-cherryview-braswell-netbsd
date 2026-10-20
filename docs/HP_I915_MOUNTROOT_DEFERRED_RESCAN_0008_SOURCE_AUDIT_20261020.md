# HP-I915 – deferred mountroot reachability, DRM registration candidate 0008 and OpRegion dependency 0009

**2026-10-20. Source-only audit, local Python self-test, no native NetBSD/HP kernel run.** i915 work branch `work/hp-native-drm-stage-replay-20261015` starting HEAD `76e072e52c7bc64f959b9506148b19ac177c9406`. Pinned NetBSD `03d918f6d0e81fa05b8f1160eca0628ad39988a6`; pinned upstream Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## 1. Exact deferred caller route

From NetBSD's pinned [kern_drvctl.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/kern_drvctl.c) blob `5712a8a762d62219deae80c17698bb92f591d43c`, the rescan operation invokes **`config_deferred(NULL)`** after running the relevant rescan callback.

In pinned [subr_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_autoconf.c) blob `5ee8a7998b07fd570d7b1f67d23cdb814de63039`, `config_deferred(NULL)` calls `config_process_deferred(&mountroot_config_queue, NULL)` as well as the standard queues. Its generic queue executor removes an entry, calls `dc_func`, and does **`config_pending_decr(dc_dev)`**.

In contrast, `config_mountroot(dev, fn)` inserts into `mountroot_config_queue` while root is not mounted **without a matching `config_pending_incr(dev)`**. Normal `config_mountroot_thread` processing calls the callback without decrementing. `config_detach_enter()` only blocks on `dv_pending || dv_detaching`; it does not consult the mountroot queue. The i915 autoconfiguration attaches through `config_mountroot(self, &i915drmkms_attach_real)`, which makes this control flow relevant to the target hardware.

**Two distinct potential defects:** (A) detach can lack a pending-token guard for a still-queued mountroot callback, risking callback-after-detach lifetime violation; (B) generic `config_process_deferred` can decrement a token never acquired **if** it consumes a queued mountroot entry. These are proven source-contract mismatches. A live HP race, or the simultaneous presence of a queued mountroot entry and `drvctl` rescan during startup, has **NOT** been demonstrated. In frozen [init_main.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/init_main.c) blob `ded47067618eef50fe63f0b2bcde0fa3c970fd48`, boot creates and later joins mountroot workers; do not infer a guaranteed kernel crash from the source mismatch alone.

**Correct next implementation gate:** design a single per-entry ownership protocol with explicit detach/cancel transition, queue removal versus already-running callback serialization, device lifetime reference, and exactly-once token release. Account for normal-thread, generic-deferred, and inline-root-mounted paths. A naive `config_pending_incr` in i915 without balanced cleanup, or a C patch inside generic NetBSD autoconf without full cross-driver regressions, is not sufficient.

## 2. Candidate 0008: failure errno and rollback

In pinned NetBSD [drm_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/drm_drv.c) blob `f91332cbebb57ab9a6ee3e1955722663df7e4929`, `create_compat_control_link()` can fail with `-ENOMEM` before `dev->registered = true`. The NetBSD `drm_minor_register` implementation excludes the Linux `device_add` path. In pinned NetBSD [i915_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.c) blob `bf64ff40059fc38188f6f3d7b55bef9793abeb57`, `i915_driver_register` is void and logs without propagating the DRM error, so probe can incorrectly return 0.

Pre-existing [candidate 0008](../candidates/0008-i915-drm-registration-unwind-netbsd11.patch) Git blob `6634a4d122d2e8524a14e60414b5043075caf3a0` returns the error and adds registration cleanup. This matches the broad negative-registration approach of pinned [upstream Linux i915_driver.c](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/gpu/drm/i915/i915_driver.c) blob `ce6d20958320c1f91a50678230eb96f88f0b357b`. It is **still an unintegrated candidate**, not a safe or fully compiled NetBSD implementation. In particular, calling `drm_dev_unregister` on an unsuccessful registration may touch client, connector and mode-registration state that require native negative-path checks.

The candidate 0008 failure branch also calls `intel_opregion_unregister`. Its own generator notes the prerequisite [candidate 0009](../candidates/0009-netbsd-opregion-optional-asle-cleanup.patch) Git blob `b257d451560584a86c6f092dcde6b0b69b0e33c8`: NetBSD's `opregion->asle->rvds` dereference is changed to conditional `opregion->rvda ? opregion->asle->rvds : 0`. This **does not prove full null-pointer or unmap safety**; require native ASLE/RVDA state matrix, original 0008 generator/test, and validated 0009 before integrating 0008. No duplicate candidate was created.

## 3. Executed and unexecuted evidence

- **15/15 independent real pinned source predicates PASS** using GitHub's file-read API: `config_deferred` rescan caller; generic queue pending decrement; mountroot no increment; detach pending gate; boot worker lifecycle; DRM pre-registration allocation failure; native Linux/NetBSD i915 propagation difference; existing candidate 0008/0009 dependencies. These predicates verify source structure, **not** real C execution.
- New [read-only pinned source oracle](../tests/test_i915_mountroot_deferred_0008_source.py) ran its isolated local `--self-test`: **3/3 PASS**. Python bytecode compile: PASS. A local `git blob` SHA was computed; the published GitHub script read back as **exactly the same blob `c66da9a5c6e8d19e1e45d7a7a748e590f302b8f4`**. This supports that the published test is the tested one.
- Full `--netbsd-tree --linux-tree --i915-repo` run **NOT_RUN** (full pinned local source trees unverified). The pre-existing [candidate 0008 source test](../tests/test_drm_registration_source_contract.py) **NOT_RUN**. Native NetBSD compilation, DRM `-ENOMEM` fault injection, actual i915 detach/HP boot/KMS and WLAN WPA2 **NOT_RUN**.
- SentinelX reported **only Legion online**, not HP, on the accessible plan. A subsequent remote `sentinel_exec` batch was **explicitly blocked by platform safety checks** (exact blocked subcommand undetermined). No retry, alternate path, or host write; do not claim current HP runtime or reclassify this refusal as missing credentials without evidence.

## 4. Next independent atomic step

1. On a **permitted** NetBSD runner and only with actual working checked-out pins, execute published source oracle and existing 0008 test. Preserve all missing native runtime gates explicitly.
2. Examine pinned NetBSD `drvctl` rescan timing versus configroot worker state and mountroot callback after-detach by controlled source-level fault scheduling, with real device lifetime/cancellation analysis. Candidate fix must not change global autoconf without proving cross-driver safety.
3. Reconcile dependent 0008+0009 lifecycle ordering, validate failed-register connector/client/minor state and OpRegion ASLE/RVDA null conditions. Do not install until G01–G09 and independent stock kernel rollback on HP pass.

Provider refusals for composed 0047+0048 artifact and earlier 0045 16-mutant suite remain in force; do not reroute. Seven earlier candidates UNINTEGRATED; 300 semantic mappings and full joint i915/DRM/TTM+RTL KMS/WPA2 remain OPEN.

Governance ledger: `Agent-Governance/state/events/hp-i915-mountroot-deferred-reachability-0008-20261020.jsonl`.
