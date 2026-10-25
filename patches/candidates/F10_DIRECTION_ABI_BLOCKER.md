# F10: Linux DRM ioctl direction mismatch — DO NOT PROMOTE F06 (2026-10-25)

**Status:** source-proven native ABI integration blocker. F06/F09 remain test-only; **not suitable for native kernel integration or boot**.

The original NetBSD `sys_ioctl()` at pinned `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, `sys/kern/sys_generic.c` blob `0894053933da09868b6ff80d34e00ddfca7cf96b`, lines 623–651, performs copyin when `IOC_IN=0x80000000` and zero initialization when `IOC_OUT=0x40000000` **before** any `fo_ioctl_user` callback. Linux's pinned `_IOC_WRITE` uses 0x40000000 and `_IOC_READ` uses 0x80000000; the meaning is reversed.

- Real Linux `DRM_IOCTL_SET_CLIENT_CAP` and `DRM_IOCTL_GEM_CLOSE` use `DRM_IOW` (write user to kernel), yet NetBSD treats bit30 as IOC_OUT and passes a zero-initialized kernel data buffer to the proposed native DRM callback.
- `DRM_IOCTL_GET_MAGIC` uses `DRM_IOR` (write from kernel to user), yet NetBSD tries user `copyin` before the callback, which may fail for an unreadable output buffer.
- `DRM_IOWR` has both bits and may appear to work, explaining why existing F03–F06 model cases did not detect this.

Original i915 `compat/native-drm/drm_cdevsw.c` (canonical commit `9bd2679`, blob `121e5a64b8f765e3ae9362a0c50735da5b616af1`) passes the NetBSD-marshalled `data` to `drm_ioctl_kernel_data(file,cmd,data,&out_size)` in its ordinary modern ioctl branch. F06 appends an opt-in callback after the original preparation and adds only a late high-size-bit guard, **so F06 does not solve direction marshalling**. The private HP-only helper's own buffer capacity remains uninspected; no memory corruption claim is made.

**Exact regression evidence:** `tests/fixtures/f10_netbsd_sys_ioctl_prep_03d918f6.inc` contains the verbatim pinned original lines 623–651; `tests/test_f10_ioctl_direction_model.c` compiles that unchanged C excerpt under synthetic usercopy/file stubs, then compares a toy corrected direction policy. `tests/test_f10_ioctl_direction_abi.py` pins both Git blob hashes and compiles original C11/`-Werror`/UBSan plus three mutant variants. **5/5 local tests PASS**; all three GitHub files were read back byte-identical to tested copies.

The toy corrected branch is an oracle, **not** an approved production fix: a safe patch must decide Linux-style marshalling **before** native copyin/zero, preserve legacy NetBSD ioctl semantics and DRM-specific copyout, handle invalid sizes and short DRM user structs, and verify the actual `drm_ioctl_kernel_data` memory contract. Only then may a clean full pinned NetBSD `git apply --check`, native object build and eventual physical validation proceed. The original F08/F09 local-Git-on-originals blocker remains OPEN. No HP access or kernel/EFI/boot/radio changes.
