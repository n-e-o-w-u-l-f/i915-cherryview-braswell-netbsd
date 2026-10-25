# F06 — DRM ioctl encoded-size high-bit guard (2026-10-25)

**Current isolated candidate:** `patches/candidates/netbsd-11-drm-fileops-bridge-copyout-owned-highbit-guard-20261025.patch`, Git blob `2fca0c1dc147e595fe2e83c3f7e57f0306773199`. This is a **candidate**, not an accepted kernel patch.

## Why F06 is needed

Pinned `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6` `sys/sys/ioccom.h` has `IOCPARM_LEN` at 13 bits and defines `IOC_VOID=0x20000000`. Pinned `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab` `asm-generic/ioctl.h` uses a 14-bit `_IOC_SIZE` in the same shift position. Thus a DRM command encoding size 8192 makes NetBSD `IOCPARM_LEN(cmd)==0` but sets `IOC_VOID`; the F04 `fo_ioctl_user` code dispatched the unrepresentable size without an explicit guard. The fixed F06 `sys_ioctl` default branch rejects `IOCGROUP(cmd)=='d' && (cmd & IOC_VOID)!=0` for **opt-in `fo_ioctl_user` only** with `ENOTTY`, before the callback. Legacy `fo_ioctl` and regular Linux DRM commands remain unchanged.

**Bounded scope:** This guards the bit-13 alias (Linux encoded sizes 8192–16383 for DRM type 'd'); it does **not** solve short but representable sizes such as `DRM_IOCTL_GET_CAP` with 8 bytes user-encoded versus 16 bytes driver struct. The actual private `drm_ioctl_kernel_data` provider still requires a real buffer-capacity/allocation/zero-extension audit. The guard deliberately has DRM group scope; if more native fileops opt in, verify their native IOC_VOID commands separately.

## Evidence and acceptance gates

- `tests/test_f06_drm_ioctl_highbit_guard.py` reads the exact candidate patch blob, extracts the full modified `sys_ioctl` default C body, compiles it with strict C11/`-Werror`/UBSan and small synthetic FD/ioctl stubs. Original: normal DRM 8-byte encoded ioctl, malformed 8192-byte DRM with and without direction flags rejected before driver/copy, non-DRM callback scope preserved, legacy error/success copyout semantics preserved. **Six separately compiled mutation variants** are expected to abort, detecting missing/overbroad/wrong guard, duplicate copyout, missing callback, and legacy error copyout. Generic Linux host only, not NetBSD kernel headers.
- `tools/check_f06_fileops_highbit_patch.py` is a read-only clean-original-checkout gate: enforces exact pinned NetBSD HEAD/source Git blobs, clean worktree, F06 candidate Git blob and four-file/six-hunk whitelist, then invokes `git apply --check --whitespace=error` without applying the patch. **Not yet run on full original NetBSD checkout.**
- Current local host `git apply --check` on four **synthetic** patch-hunk preimages passed; one damaged patch context was rejected. Independent **in-memory** context/offset matching against all four fully fetched original pinned NetBSD source files passed (6/6 hunks). These are not a real pinned full-tree Git apply or kernel build.

**Patch priority:** F03 original contains a double-copyout contract bug and is superseded; F04 fixes single-owner copyout but lacks this 8192-size rejection; F06 adds the guard. **Do not apply F03, F04, or F06 as a boot-ready kernel change** until clean NetBSD source Git apply, native `kern_descrip.o`/`sys_generic.o`, actual FILE/task Linux strong owner/fput, UVM/GEM, configured 410-object link and KMS/WPA2 safe recovery acceptance.
