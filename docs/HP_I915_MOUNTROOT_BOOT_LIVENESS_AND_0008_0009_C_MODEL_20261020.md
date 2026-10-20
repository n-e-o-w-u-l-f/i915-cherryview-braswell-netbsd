# HP-I915 — mountroot boot liveness correction and 0008/0009 C negative-path model

Date: 2026-10-20 Europe/Berlin. **SOURCE-PROVEN TEMPORAL CORRECTION + COMPILED ISOLATED C MODEL. NOT A KERNEL BUILD.**

## Evidence and pins

- Work branch `work/hp-native-drm-stage-replay-20261015`, source HEAD at PRE `95cbebda5d8eb7a1e421de1b46cef643a7b2adf0`. New C harness first publication `a29a595f6a5d5a19fcf191d59dd55f3449ec9cc9`.
- Pinned NetBSD/source commit `03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
  - [`sys/kern/init_main.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/init_main.c) Git blob `ded47067618eef50fe63f0b2bcde0fa3c970fd48`.
  - [`sys/kern/kern_drvctl.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/kern_drvctl.c) `5712a8a762d62219deae80c17698bb92f591d43c`.
  - [`sys/kern/subr_autoconf.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_autoconf.c) `5ee8a7998b07fd570d7b1f67d23cdb814de63039`.
  - [`intel_opregion.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c) `2cbe50d346b20bb9a23382993c361e7db94b6e9d`.
  - [`i915_drv.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/i915_drv.c) `bf64ff40059fc38188f6f3d7b55bef9793abeb57`; [`drm_drv.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/drm_drv.c) `f91332cbebb57ab9a6ee3e1955722663df7e4929`; [`drm_mode_config.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/drm_mode_config.c) `311ab0a1e56f1324d47f7320acdc03608557a220`; [`drm_client.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/drm/drm_client.c) `1819d7357697df21fddaa32cbba6946deea218df`.

## 1. Reachability correction: ordinary drvctl rescan cannot race unprocessed boot mountroot queue

Last [source audit](HP_I915_MOUNTROOT_DEFERRED_RESCAN_0008_SOURCE_AUDIT_20261020.md) established that `kern_drvctl::rescanbus` runs `config_deferred(NULL)` and that generic deferred queue processing decrements a pending token not acquired by `config_mountroot`. **Its direct application to still-queued initial boot mountroot entries was not demonstrated.**

The pinned `init_main.c` establishes the sequence:

1. `vfs_mountroot()` succeeds, then `configure3()` calls `config_create_mountrootthreads()`.
2. `config_create_mountrootthreads` sets `root_is_mounted = true`; queued mountroot callbacks are processed by kernel threads.
3. `init_main` calls `config_finalize_mountroot()`, which joins the mountroot worker threads.
4. Only **after** that join does the kernel set `start_init_exec = 1` to release the initial `init(8)` exec path.

Since `drvctl` `DRVRESCANBUS` is a userspace ioctl, an ordinary `init(8)`-started userspace rescan cannot overlap those pending **initial boot** mountroot callbacks. Do **not** claim the generic `config_pending_decr` underflow as an observed normal boot fault merely because a static generic path exists. This revises the previous suspicion to: **static counter-path mismatch, ordinary boot userland rescan reachability NOT_PROVEN and on the pinned boot order excluded.**

Remaining relevant **separate** questions: whether a kernel-side direct `config_deferred()` call can process a queued mountroot entry in another context; and whether physical/dynamic kernel detach can remove a device before its mountroot callback executes. Mountroot pending does not itself increment `dv_pending`, while detach waits on `dv_pending || dv_detaching`. Neither a real HP failure nor an unconditional use-after-free has been demonstrated.

## 2. OpRegion error-unwind dependency: candidate 0009

Frozen `intel_opregion_unregister` unconditionally reads `opregion->asle->rvds` after checking only `opregion->header`; if `header != NULL, asle == NULL, rvda == NULL`, this expression dereferences a null ASLE pointer. [Candidate 0009](../candidates/0009-netbsd-opregion-optional-asle-cleanup.patch) changes that one line to `size_t rvds = opregion->rvda ? opregion->asle->rvds : 0;`.

In the pinned `intel_opregion_setup`, `rvda` is mapped only under `opregion->asle && opregion->asle->rvda && opregion->asle->rvds`. Thus `rvda != NULL` implies `asle != NULL` **on that observed setup path**, and `rvds` is read **before** the OpRegion header containing ASLE is unmapped. The correction handles the plausible `header, no ASLE, no RVDA` case, subject to other initializers preserving this invariant. No full kernel or foreign-driver call graph was verified.

## 3. DRM registration / candidate 0008

Frozen `drm_dev_register` can return `-ENOMEM` from `create_compat_control_link` before `dev->registered=true`. It already runs `err_minors` rollback. Frozen i915 ignores this error; [candidate 0008](../candidates/0008-i915-drm-registration-unwind-netbsd11.patch) captures and propagates it, including `drm_dev_unregister` and PMU/GEM cleanup, with an `intel_opregion_unregister` in its later probe rollback. The candidate's own generator names 0009 as its prerequisite.

**Precise native negative-path question still open:** calling `drm_dev_unregister` *after failed `drm_dev_register`* also invokes `drm_modeset_unregister_all`, including early-unregister hooks on encoder/CRTC/plane even though normal `drm_modeset_register_all` was never reached. The pinned NetBSD connector unregister checks connector registration state; the generic encoder/CRTC/plane loops must be audited for exactly-once callbacks. NetBSD `drm_client_dev_unregister` is currently an empty stub. Existing pre-registered DRM minor cleanup may happen twice; success semantics or harmlessness must be proven in the complete native tree, not inferred from a simple C model.

A separate integration prerequisite is the i915 native attach-real error path's stale `sc_task_thread` on *any* negative probe (previous [contract](HP_I915_PROBE_INTELFB_PENDING_SOURCE_ORACLE_20261020.md)). Introducing additional negative propagation via 0008 without dealing with that native owner state is **not yet integration-safe**.

## 4. Executed local C evidence

New [`tests/test_i915_opregion_0008_0009_model.c`](../tests/test_i915_opregion_0008_0009_model.c), Git blob **`42f0a4e7a0234d5a6875cab23a6d16efdf696aa4`**, 3881 bytes. Local Linux toolchain:
```sh
cc -std=c11 -Wall -Wextra -Werror -pedantic -O2 -o /tmp/t0008_0009 tests/test_i915_opregion_0008_0009_model.c
/tmp/t0008_0009
clang -std=c11 -Wall -Wextra -Werror -pedantic -O1 -fsanitize=undefined -fno-sanitize-recover=all -o /tmp/t0008_0009_ubsan tests/test_i915_opregion_0008_0009_model.c
/tmp/t0008_0009_ubsan
```
**ACTUALLY EXECUTED:** GCC model `PASS 6/6`; Clang + UBSan model `PASS 6/6`; `git hash-object` local equals published GitHub blob, readback matched byte-for-byte. Cases: absent header, present header/no ASLE/no RVDA, present header/ASLE/no RVDA, present header/ASLE/RVDA and correct RVDS size, negative DRM register failure stops late registration, successful register does not unwind. The program uses simplified **mocked structs/callbacks**, not actual NetBSD drivers. It cannot establish native ABI/KMS, IRQ, DMA or device teardown safety.

**NOT_RUN:** full pinned NetBSD/Linux/i915 checkout source oracle, existing 0008 full source test, actual NetBSD kernel compilation, HP detached-queue fault injection, combined RTL kernel, G01–G09 rollback, physical HP KMS/WPA2. Previous denied combined 0047+0048, 0045 sixteen mutant suite and Legion remote command were not retried/rerouted.

## Next authorized independent action

1. Resolve which actual kernel callbacks (if any) invoke `config_deferred` before `config_finalize_mountroot`, plus physical detach reachability before callback; limit a fix to proven lifetime conditions rather than unnecessarily changing global autoconf.
2. Analyze DRM native encoder/CRTC/plane early-unregister behavior on an unsuccessful `drm_dev_register`; verify 0008's double-minor/rollback sequence and 0009 setup `rvda -> asle` invariant in a NetBSD native fault test.
3. Validate i915 parent `sc_task_thread` on all new negative returns before integrating 0008/0009 into **one** coordinated i915+RTL kernel build. Require independently verified boot console/standard kernel restore (G01–G09) before HP tests.

Governance PRE/POST: `Agent-Governance/state/events/hp-i915-mountroot-liveness-0008-0009-20261020.jsonl`.
