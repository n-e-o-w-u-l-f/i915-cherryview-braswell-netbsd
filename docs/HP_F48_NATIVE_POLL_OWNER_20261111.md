# HP F48 — native Poll owner object

F48/A01 is **PASS** for the actual native relocatable Poll object on `hp-tpnw121.lan`, NetBSD 11 amd64 F77, user `andreas` (uid1000/gid100). The source is the published F46 implementation at `e7d7100c44322d3209d8f43d1d3a3842b52b340b`; no implementation, contract or test was changed for F48. Parent driver completeness remains **PARTIAL**.

## Actual native result

The existing public builder ran exactly two successful commands with the original kernel flags: independent `-M`, then conditional `-MD/-c`. Both exit codes are zero and both compiler logs are empty. There was one attempt, with no compiler retry. Launcher PID17348 and builder PID19182 are resolved; the terminal exit receipt records zero at `2026-11-11T05:51:54.427908+00:00`.

`linux_poll_owner.o` is an ELF64 little-endian AMD64 ET_REL object, **114232 bytes**, SHA256 `079c884e139eb0940b587a81d90d6d81f946b88dfe3828b3d7d2a23d26a22995`.

The actual independent and compiler dependency sets are equal: **251 inputs = 17 repository + 208 pinned archive + 25 generated configuration + 1 patched header**. Every required repository input is consumed in both sets; all nine provenance/API-definition proof owners are excluded. The actual patched `sys/sys/file.h` is consumed. The archive verification covers 345 distinct pinned NetBSD source members required by the combined core/Poll proofs; generated configuration identities are verified separately. No system header or broad provider root is substituted.

## APIs and symbols

All six public source definitions are present: `linux_file_poll_init`, `linux_file_fd_attach`, `linux_file_fd_detach`, `linux_file_poll_fini`, `linux_file_native_poll`, and `linux_file_native_kqfilter`.

The five shared undefined symbols have verified source owners: `fput` and `linux_file_sync_flags` in `compat/native-file/linux_file.c`; `linux_add_wait_queue` in the recovered native Wait owner; and `linux_task_entry_enter`/`linux_task_entry_leave` in `compat/native-entry/task_entry.inc`, declared by the Task companion header. Their actual relocation call sites are recorded. The 18 remaining undefined symbols are native kernel primitives; this is not a final-link acceptance claim.

The sole extra text symbol, `__x86_indirect_thunk_rax`, is independently classified using its exact `.text.__x86_indirect_thunk_rax` section, hidden visibility and 17 bytes `e807000000f3900faee8ebf948890424c3`. The two actual R_X86_64_PLT32 relocations with addend -4 originate at `linux_poll_query+0x5c` and `linux_poll_kqevent+0x115`; source/header callback causality and the actual `-mindirect-branch=thunk` / `-mindirect-branch-register` flags are recorded. No prefix-based exemption was added. There are no unexpected Linux undefined symbols or unresolved extra text symbols.

## Provenance and preservation

Published/read-back Governance PRE is `246e937be05cde036b3fb01f91df41c6437a0573`. Before effects, the controllers checked the exact public builder/helper and all seven contracts, 26 Poll Git inputs at `d828f558b16806130c9a044e9795ca89e3c1f022`, the separate unchanged 15-input Wait generation proof, the original F32 core receipt, pinned source archive, configured flags, tools and generated headers. Final checks and both independent reviews confirm those identities. All **1961** frozen states are preserved, including the 49 restored native prerequisites and the protected `/netbsd` and `/boot.cfg`.

Before compilation, an exclusive durable local prerequisite archive was created and verified: **341780480 bytes**, SHA256 `7d13562136a56928c6a7cc295efefd109d79536806840b24f280951fce557d06`, containing 2906 entries (1978 regular files,236 directories,692 symlinks). Every member type/mode/payload hash/link target and the exact set were checked against the unchanged source tree. Symlinks were not dereferenced and no archive extraction was performed. The full manifest SHA256 is `e070236c45b9a801aa83711c19fe9d4d42e9cf81ed7bb48957fff75418733cd5`. Archive and object remain local; Git contains their identities and textual evidence.

The immutable original execution receipt left extra-symbol review pending. The later independent object/symbol receipts resolve that review without editing the execution receipt. A separate review observer initially made overly specific source-text and definition-layout assertions; they were corrected against the actual `vfs_poll` inline-header path and the recovered Wait definition before writing its receipt. This caused no product change or additional native compiler command.

## Evidence and remaining scope

The [machine evidence](evidence/HP_F48_NATIVE_POLL_OWNER_20261111.json) contains the raw public status, actual argument vectors, both dependency files, controller sources, durable archive manifest, independent ELF/symbol/review receipts and per-artifact hashes. Private root: `/home/andreas/projects/hp-i915-f26-20261106/f48-native-poll-owner-20261111-a01` (object output; outer evidence uses the same stem).

F46's 287 passing tests remain attributable to the unchanged implementation. F48 adds an actual native object and independent dependency/symbol/preservation checks. Poll registration/callback lifetime, RCU/free ordering, complete provider/link closure, full kernel build and hardware acceptance remain separate. No link, install, boot, EFI/radio change, cleanup or runtime test was performed. Only HP was verified in this step; the registered SteamDeck checkout is absent in this runtime and other systems were not revalidated.
