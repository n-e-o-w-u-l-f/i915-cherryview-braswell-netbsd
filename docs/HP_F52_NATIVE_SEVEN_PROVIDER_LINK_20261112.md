# HP F52 — native seven-provider relocatable link

**Date:** 2026-11-12. **Status:** PASS for one exact private `ld -r` link on the physical HP TPN-W121 running NetBSD 11.0/amd64 as `andreas`. The **whole i915 + WLAN kernel remains PARTIAL**.

## Actual native operation

A published, read-back F52 PRE committed to governance at `9720d96cf995c6a182b05f733a512adb93231450` froze seven real previously compiled and hashed objects: FD, Anon, FILE, Task, Wait, Poll and Worker, in that order. The original Worker's F51 object is 144576 bytes with SHA-256 `7d90f9bbb270c3d922de228967ef2b7efde0e1f522a7f4b4882bc7b0a632b7fe`.

One native `/usr/bin/ld -r` invocation ran with exit code **0**, an empty stderr/stdout log, and **no retry**. The new private artifact `seven_providers.o` is an ELF64 little-endian AMD64 ET_REL file of **838952 bytes** with SHA-256 `711322a068fbf3ada63bde09f7e1f5b036ccbca99845f7c68eb53a31ae542497`. The exact input order and original object hashes are in [the machine evidence](evidence/HP_F52_NATIVE_SEVEN_PROVIDER_LINK_20261112.json).

## Native relocation and symbol closure

- All **eight** F51 Worker Linux undefined symbols resolve to text definitions in the actual F42 native Task object when the seven objects are linked.
- All **24** F51 native kernel undefined symbols have matching definitions in the existing F26 kernel image.
- The `__x86_indirect_thunk_rax` text export appears in four separate input objects, but each is a COMDAT group; the actual partial linker successfully coalesces the group. The output retains exactly one `rax` and one `r15` indirect thunk. The compiler uses `-mindirect-branch=thunk` / `-mindirect-branch-register`.
- **80 external references remain** in the seven-object output: eight named `linux_*` and 72 other names. These were not silently treated as resolved by a successful `ld -r`.

## The 80 remaining symbol owners

The independent symbol-owner review, performed against the actual F26 linked image, F32 `kern_descrip.o` and selected project source, accounts for all 80 without guessing implementation:

| Class | Count | Verified location / limitation |
| --- | ---: | --- |
| Actual F26 kernel text/data | 71 | Includes `linux_call_rcu` and `linux_rcu_barrier` from pinned NetBSD `linux_rcu.c` |
| Separate F32 native object | 1 | `fd_get_linux_file` defined in previously compiled `kern_descrip.o`; **not** included in F52 |
| Source implementation present but not natively compiled for this closure | 8 | `linux_inode.c`, `linux_native_fileops.c`, `linux_page.c`, `linux_shmem_commit.c` |

The 8 source-only names are `ihold`, `iput`, `linux_inode_alloc_system`, `linux_file_native_ops`, `linux_page_system_init`, `linux_page_system_fini`, `linux_shmem_commit_init` and `linux_shmem_commit_fini`. Having a source definition **does not** prove valid NetBSD ABI, error unwinding or runtime behavior. All 80 symbol-by-symbol matches and input hashes are preserved in the machine evidence. The private owner review SHA-256 is `07f188fa8cafbc497e26703f0bfc58db2ec598c886932ec91bda3fa77323140e`.

## Security, preservation and actual limits

All seven original native provider objects, the pinned kernel and the F32 evidence remain untouched. Protected `/netbsd` SHA-256 `9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde`, and `/boot.cfg` SHA-256 `f7e0ccc00308172d5787f47c2c66b33921c53341f896e2339079a66980b6a4df` remain unchanged. No full kernel compile/link, install, reboot, firmware, WLAN radio action, PCI/KMS exercise, DRM userspace acceptance or WPA2 session occurred in F52.

**Next:** a separate F53 PRE/native admission and compile of the four identified additional FILE/INODE/PAGE/SHMEM provider units, followed by a correctly scoped provider graph link incorporating the exact original F32 kern_descrip owner. Additional FILE/MM/UVM lifetimes, compat32 translation, modern 410 configured graph and physical HP KMS/WPA2 gates remain independently open. No source files were modified as part of this F52 evidence-only change.
