# NetBSD VBlank CRTC reference bounds and scheduler — 2026-10-18

**Source-only candidate — no native HP kernel build or hardware acceptance.**

## Real pinned source contract

- Frozen NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6` at `sys/external/bsd/drm2/dist/drm/drm_vblank.c`, SHA256 `06434bfc9f6693a1b61069c5c0e839b24671a5ba4d826fb001b0a897ceac206e`. The same byte identity was verified in the real separate Legion NetBSD source tree with Git blob `a2fc6c741d1962f6a04f3dcb136b0228d7bf22f3` — no source edit.
- `drm_vblank_get_locked` and `drm_vblank_put_locked` originally compute `&dev->vblank[pipe]` before checking `!dev->num_crtcs` and `pipe >= dev->num_crtcs`. Invalid or uninitialized inputs can therefore cause out-of-bounds/null pointer arithmetic *before* the early return. Even if the compiler elides a never-dereferenced pointer calculation, the source order is invalid. **Do not report a UBSan failure for the original:** the isolated runtime test did not instrument that optimized-away expression.
- New separate candidate `candidates/0018-netbsd11-drm-vblank-ref-guard-pipe-bounds.patch` (SHA256 `2a4cc2546abd9e9e7be38a7e972d619a49991a1f02cff8333cacc35db9a1dd0f`) defers both pointers until after pipe validity checks. It does not alter reference counts, interrupt enables, timer sequencing, event-lock operations, valid CRTC lookup or return codes.

## Executed pinned NetBSD integration evidence

Permanent `tests/test_i915_netbsd_vblank_ref_bounds.py` validates three immutable pinned files (`drm_vblank.c`, `drm_vblank.h`, `files.drmkms`), the exact producer patch hash and the previously published `compat/native-runtime/drm-vblank/patches/netbsd-drm-vblank-core-hooks.patch`.

- **Both patch orders PASS:** original → `0018` → core hooks; original → core hooks → `0018`. All original files restored *byte-for-byte* after reversing both patches. The hook's `nb_i915_vblank_ref_get_locked` remains present.
- **Seven strict host-C tests PASS** using the real extracted NetBSD `get_locked`/`put_locked` C functions: uninitialized core/invalid pipe, two balanced gets/puts, underflow refusal, failed enable rollback with immediate disable, zero-offdelay no disable, immediate-disable timer policy, and disabled already-held reference rejection.
- Compiled with `cc -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=undefined,pointer-overflow -fno-sanitize-recover=all`; four exact source mutants placing pointers above the bounds check or deleting the bounds check were refused.
- The pinned compiler and tests were run on **Legion**, not HP NetBSD. Patch files contain required unified-diff context lines beginning with spaces; `git diff --check` may misleadingly report these context lines as whitespace in the **patch text**. Real `git apply --check` and byte-exact reversal validate the patch. Independent Python syntax and code-only diff checks passed.

## Scheduler-class parity remains a separate blocking gate

The Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab` `drivers/gpu/drm/drm_vblank_work.c` calls `sched_set_fifo(worker->task)` after `kthread_run_worker`. NetBSD `sys/kern/kern_kthread.c` at frozen `03d918f6` uses `SCHED_RR` by default for a kernel thread without `KTHREAD_TS`, and `PRI_NONE` resolves to `PRI_KTHREAD`; `KTHREAD_TS` instead selects `SCHED_OTHER`. This is **not** source-proven FIFO deadline parity. No speculative priority/scheduler mutation has been made. Actual NetBSD class/latency verification remains required.

## Release and physical-boot gates

This candidate fixes only two *DRM-core* reference guards; **none of the 300 semantically unreviewed Linux i915 C units has been declared closed** and 23 Cherryview UC/PXP reference exemptions remain individually recorded. The i915 WIP and RTL consumer are not production release artifacts. No native HP object/kernel link, driver installation, physical console/rollback validation, reboot, KMS or WPA2 test. The user-requested order remains: complete 323 semantic i915/DRM/TTM source integration → authorized **HP native** kernel compile/link → recovery-safe independent test-kernel installation → **user tests installed kernel** → physical KMS acceptance.
