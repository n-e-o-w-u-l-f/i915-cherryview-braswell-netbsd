# F21 – Deferred i915 probe error: task-owner state repair

**Date:** 2026-10-28
**Status:** kernel C patch candidate, source-applied and host-compiled; **NOT NetBSD kernel-compiled / NOT HP-booted**.

## Source-proven behavior

Pinned NetBSD/src: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
Original `sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c` Git blob
`9798385b02f247c08db9b16624d5ddc9d11a8ca5`.

The `i915drmkms_attach_real()` callback sets `sc_task_thread = curlwp`
before `i915_driver_probe()`. If probe returns an error, the original
implementation logs and immediately returns. The normal successful
branch sets `sc_task_thread = NULL` only **after draining** its
`sc_tasks` queue. The detach code later asserts that the task-owner
pointer is NULL and the queue empty.

The F21 candidate changes exactly the existing probe-error branch:
when `SIMPLEQ_EMPTY(&sc->sc_tasks)` is true, it clears the owner with
`atomic_store_relaxed(&sc->sc_task_thread, NULL)` before returning.
**If there are queued tasks, it does not clear the pointer, execute
unknown callbacks, unbalance pending counters, or discard the queue.**
That unresolved branch requires an independent callback-lifetime fix
after verifying precise error-edge reachability.

Source patch:
`patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch`

## Executed evidence

- Exact original Git blob verified on the Legion host.
- Real `git apply --whitespace=error --check` and `git apply`
  against a complete original NetBSD source file: PASS.
- Exact modified C error block extracted, compiled and executed under
  GCC and Clang, including both zero and nonzero queue lengths: PASS.
- The rest of the original C source is byte-identical.
- Automated regression:
  `tests/test_f21_i915_probe_error_task_owner.py`
- Result:
  `F21_PINNED_GIT_APPLY_TWO_COMPILERS_EMPTY_ONLY_STATE_REPAIR_PASS`

## Critical limitations: HP boot-menu 5

F19's `drmfb_attach()` preflight is **downstream** of this path;
an early i915 probe error can bypass it. F20's GOP return-zero fix
addresses a **different, earlier x86 console initialization** problem.

On EFI, `wsdisplay_preattach()` may leave `wsdisplay_cons.cn_dev`
as `NODEV` until a later `wsdisplay_emul_attach()` completes.
The PCI matching priority of i915 is 6 versus at most 5 for genfb;
a failed deferred i915 probe can therefore leave no complete
framebuffer console. **F21 does not restore that console.**
Blindly calling `wsdisplay_predetach()` could remove the only
console; blindly suppressing `cnopen` is not an acceptable fix.

No exact menu-5 panic text, non-vpanic stack frames, or image hash
have been received. Do not present F19/F20/F21 as physical fixes.
The real HP, recovery F77, boot menu and on-disk kernels were not
accessed or modified.

Next evidence required: menu option 5's exact kernel pathname plus
the actual `panic: ...` line and first significant DDB frames.
No further failed boot should be induced solely for diagnostics.
