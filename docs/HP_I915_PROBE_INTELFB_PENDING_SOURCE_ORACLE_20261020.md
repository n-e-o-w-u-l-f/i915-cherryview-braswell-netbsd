# HP-I915 — pinned probe/register → synchronous fbdev → intelfb task/counter contract

Date 2026-10-20 Europe/Berlin. **SOURCE-ONLY; earlier late-probe intelfb cancellation hypothesis RESTRICTED; a real NetBSD probe-failure detach assertion mismatch persists.**

## Source identity

- Work branch at this audit start: `55a114170997f129aaf6e8c44f9e359d927988ea`. Earlier callback audit at `30160f7f374e503cd367e11b7d8c664f85644e51`.
- NetBSD/src: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`, exact frozen files and Git blob SHAs:
  - [i915_drv.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.c) `bf64ff40059fc38188f6f3d7b55bef9793abeb57`
  - [intel_fbdev.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_fbdev.c) `381b63df5d1f57337057d541827a7726e602f477`
  - [NetBSD linux/async.h](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/linux/async.h) `a761ff7606b4ddce958af193833b995b2e313b09`
  - [i915_pci_autoconf.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c) `9798385b02f247c08db9b16624d5ddc9d11a8ca5`
  - [intelfb.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/intelfb.c) `482f05fb6879cae8bebaf9aa6e3bd054dc6118b4`

## Verified normal control-flow order

1. `i915drmkms_attach` initializes the native SIMPLEQ and workqueue, then defers `i915drmkms_attach_real` with `config_mountroot`. The real callback sets `sc_task_thread = curlwp`.
2. `i915_driver_probe` returns on failing early, MMIO, HW or `i915_driver_modeset_probe` stages. **Only after those pass**, it invokes `i915_driver_register`.
3. Registration is `static void` and calls `intel_fbdev_initial_config_async` near the end. In the frozen NetBSD `linux/async.h`, `async_schedule` invokes `(*fn)(arg,1)` **inline and synchronously**; `async_synchronize_cookie` is an empty stub. Do not infer a background task here just from the Linux function name.
4. `intel_fbdev_initial_config` reaches `drm_fb_helper_initial_config`; the `intelfb_create` NetBSD branch calls `config_found(..., iattr="intelfbbus")` and may create an `intelfb` child. `intelfb_attach` calls `i915drmkms_task_schedule(parent,...)` **before** `config_pending_incr(self)`. With the native `sc_task_thread == curlwp` synchronous path, it queues into `sc_tasks`, not the worker; `intelfb_attach_task` later performs `config_pending_decr` and avoids an early decrement. The normal success path drains the queue before resetting `sc_task_thread` to NULL.
5. In this bounded frozen call graph, **an ordinary negative return from `i915_driver_probe` after successfully enqueuing this specific initial `intelfb` task was not demonstrated**. The previous report's conditional queue-leak/counter-imbalance scenario must remain a **hypothesis for other entry/callback/re-entry paths**, not a proven ordinary late-failure mechanism.
6. Separately, `i915drmkms_attach_real` still returns directly on **any** negative `i915_driver_probe` result with `sc_task_thread` left equal to `curlwp`. `i915drmkms_detach` unconditionally asserts NULL. This narrow **source-proven inconsistent error state** survives the revised child/counter reachability analysis. Actual detach/panic and module unloading behavior are NOT_RUN/UNKNOWN.
7. `i915_driver_register` logs an error when `drm_dev_register` fails but returns `void`; probe will still report success after registration. Investigate this **separate unpropagated userspace-registration failure** and its cleanup semantics in a later, independently scoped task; do not mislabel it as `i915_driver_probe < 0` after registration.

## Independent source-only regression evidence

Published standalone [pinned source contract oracle](../tests/test_i915_netbsd_probe_async_lifetime_source.py), with NetBSD Git blob pin checks and isolated `--self-test` / `--netbsd-src` CLI. Source publication and exact GitHub readback verified. A separate live GitHub-fetched-source check evaluated **10/10** bounded reachability/invariant predicates PASS. A separate source-text mutation classifier detected **5/5** deliberate synthetic changes (error owner-clear, async shim, registration callback, detach assertion, pending increment). They are source-level guard checks only, **NOT native regression tests** and **NOT** the previously provider-denied 0045 16-mutant suite.

The script itself was **NOT_RUN** on a local native runner. An attempt to obtain its public raw file through the local download helper failed its URL-view prerequisite; web preview subsequently returned `DisabledError`. Neither tool result proves code execution or a security-policy violation. Do not claim the script's `--self-test` passed. A supported authorized checkout can later execute:
```sh
python3 -B tests/test_i915_netbsd_probe_async_lifetime_source.py --self-test
python3 -B tests/test_i915_netbsd_probe_async_lifetime_source.py --netbsd-src /path/to/pinned/netbsd-src
```
The second command detects the **existing source bug** and is not proof of a production repair; the source pins are required. Separately validate that test code compiles and its expected classifier remains accurate.

## NEXT / non-bypass safety

1. Review deferred mountroot detach ordering, lifetime after early failure, source-owner cleanup of the stale task-thread identity and child lock boundary. Minimal patch must preserve task ownership; merely zeroing stale identity may not be sufficient if other callbacks still run.
2. Review separate `drm_dev_register` failure propagation and real registration rollback. Use test-first and bounded, independent C candidate only after verifying correct native API contracts; no speculative production i915 rewrite.
3. Only native NetBSD -Werror, SMP/LOCKDEBUG failure injection, subsequent detach and actual HP KMS/boot/recovery can close the runtime gates.

Prior `0047+0048` composition provider-refused, **NOT_CREATED**; prior `0045` 16-mutant attempts provider-refused/**NOT_RUN**. Do not repeat/reroute. Seven candidates unintegrated; 300 semantic rows and combined i915/DRM/TTM+RTL, G01–G09, verified stock-kernel rollback, HP boot, KMS/WPA2 remain **OPEN**. No driver C, HP kernel, bootloader, filesystem or hardware mutation in this source-only step.

Governance PRE/POST: `Agent-Governance/state/events/hp-i915-probe-intelfb-pending-oracle-20261020.jsonl`.
