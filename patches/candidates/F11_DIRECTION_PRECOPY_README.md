# F11 — Linux DRM ioctl marshalling before NetBSD user copies

**Status: source-level candidate only; NOT a bootable/approved NetBSD kernel patch.**

This new F11 candidate supersedes the F06 candidate for *future review*, because F06's `fo_ioctl_user` callback sits **after** `sys_ioctl` has already interpreted Linux direction bits with NetBSD semantics.

## Patch intent

- `patches/candidates/netbsd-11-drm-fileops-bridge-early-direction-20261025.patch` (Git blob `fc1fa75dcb653d55dd7ff692bbdd7b0e1fd31676`) retains F04's single-owner output copyout policy, the F06 strong-ref FILE interface candidate and all native legacy `fo_ioctl` behavior.
- For opted-in DRM group `'d'` only, set `linux_drm_ioctl` and reject the Linux size-bit13 / NetBSD `IOC_VOID` collision **before** buffer preparation. Other native fileops retain their existing path.
- Translate only the temporary preparation command `prep_com`: Linux `_IOC_WRITE` bit30 becomes NetBSD `IOC_IN` (copyin), and Linux `_IOC_READ` bit31 becomes NetBSD `IOC_OUT` (zero destination). Leave the original `com` unchanged for dispatch to Linux DRM.
- Exclude opted-in DRM commands from the native disklabel group-`d` fixup, which is unrelated to Linux DRM group-`d`.
- Existing NetBSD fileops without `fo_ioctl_user` stay in their original native direction and generic copyout semantics. A different optional callback group is not automatically assigned Linux DRM semantics.

## Proof and limitations

A pinned-source exact-context verifier matched the F11 unified patch against **all four complete** original NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6` file contents: **12/12 hunks PASS**, independently including seven `sys_generic.c` hunks. A true `git apply --check --whitespace=error` on a four-file **synthetic hunk-preimage** staging tree also passed; Git then applied it to that synthetic tree successfully. **No native Git apply check on all four actual NetBSD files** was run (F08 byte-transfer blocker remains).

`tests/test_f11_early_ioctl_direction.py` extracts the **actual early guard and `prep_com` assignment from the exact candidate patch**, pairs them with the inherited F10 fixture containing the verbatim pinned NetBSD copyin/zero branch (three changed condition identifiers verified against F11), and compiles C11/`-Wall -Wextra -Werror`/UBSan with controlled FD stubs. Eight modeled normal behaviors are checked in the original executable: Linux `_IOW`, `_IOR`, `_IOWR`, `_IO`, native `IOC_IN/OUT`, non-DRM callback group, and invalid Linux high-size bit. Five mutated binaries are expected to abort: no swap, no highbit guard, overbroad scope, modified driver command, legacy swap. **6/6 Python tests PASS**. This is a **generic-host source-fragment model**, not NetBSD object compilation or a real concurrent ioctl test.

**Outstanding gates:** Native full original NetBSD clean-tree Git check, exact compiler `sys_generic.o`/`kern_descrip.o` and all `fileops` consumers; private `drm_ioctl_kernel_data` **short-user (8-byte) versus 16-byte official DRM_GET_CAP** buffer-allocation/zero-extend/copyout proof, compat32/PK_32 direct-user-pointer owner, Linux FILE strong-reference final `fput`/task/LWP/module, UVM/GEM, full configured 410-object kernel link, actual Cherryview KMS and RTL8723BE WPA2 with F77/stock recovery. No HP host access, no boot/EFI/radio modification, and no alternate route around the earlier denied HP diagnostic.
