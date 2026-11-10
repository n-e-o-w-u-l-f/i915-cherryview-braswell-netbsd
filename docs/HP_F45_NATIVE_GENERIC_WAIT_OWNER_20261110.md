# HP-I915 F45: actual native generic Wait owner object

F45 is **PASS**. One actual native provider process compiled the exact recovered generic Wait owner into a private AMD64 ELF64 relocatable object. Independent reviewers verified all 25 source-defined public APIs, the actual dependency proofs, compiler mitigation output and preservation of all 602 protected states.

## Actual native attempt

Runner source: published F44 commit `e55d3805380346bd717eed779728fb7b7f88b57e`. The fixed sixth contract is `compat/native-runtime/wait-contracts/provider-inputs-f44-wait.json`, SHA256 `5561d9005df2e8018262fb81437ae5abc88e2cb13a6f7306f604a3d4e728309c`; its 15 exact working/Git/blob inputs bind to F43 commit `610c66b412672ca96b0048179d07035929443402`.

The reviewed launcher ran once on `hp-tpnw121.lan`, NetBSD 11 amd64/F77, andreas uid1000. Launcher PID16984 started at 16:33:29 UTC; actual provider PID2301 started at 16:33:39 UTC and completed at 16:35:11 UTC on 2026-11-10. Both processes ended with exit0. The sole unit was `compat/native-runtime/wait-f43/linux_wait.c`; there was no preflight-only run, compiler override, retry or source change.

The actual commands used the saved strict F27 kernel flags, including `-Werror -D_KERNEL -nostdinc`, the patched core overlay, recovered Wait include root, current runtime mappings and the two unchanged native roots. Independent `-M` completed first; the current archive-member comparison passed before `-MD/-c`. Both command logs are empty and both exit codes zero.

The private artifact is `/home/andreas/projects/hp-i915-f26-20261106/f45-native-generic-wait-owner-20261110-a01/linux_wait.o`: **126264 bytes**, SHA256 `c1eb7e67bc1b522c21536dc33977b8887d1624dd6957283bc5ab4f9f542993d6`, ELF64 little-endian AMD64 ET_REL.

## Dependencies and generation proof

Raw independent-M and compiler-MD files resolve to exactly the same **226 identities**: 8 repository inputs, 193 archive-backed native files and 25 actual generated configuration files. All eight selected Wait/Task inputs were consumed with their exact SHA/blob rows. All seven generation-proof owners were excluded. No patched FILE header or declared lockstat override was consumed; original patched-header rejection and the complete F32 core verification remained active.

The provider freshly verified the union of 346 required source members against the pinned NetBSD archive. Independent cold verification found every path/hash pair identical to a member already verified in the F42 union348, then freshly hashed the whole 680758467-byte archive to `3645aca2c1ac9716558075b7747a98583a8e87435f00ff30c786b4b438dbe15b`. No additional independent TAR scan was needed for unchanged members.

The same-read generation chain was reverified before and after the attempt: fixed raw snapshots, recipe/ledger/producer witnesses, historical output hashes and all 49 audited operations. The nested F43 generation receipt remains historical `VERIFIED_SOURCE_GENERATION_ONLY` with native work `NOT_RUN`; this separate F45 native object result is `COMPLETE`.

## Symbols and acceptance boundary

All 25 actual public C definitions match the recovered header's namespace aliases. The declaration-only bit-wait alias and three static helpers are excluded from that API count.

The actual symbol table has one additional public T symbol, `__x86_indirect_thunk_rax`. Its original launcher receipt deliberately retains `PENDING_INDEPENDENT_REVIEW`. Independent review resolves it as **CLASSIFIED_GCC_INDIRECT_BRANCH_THUNK**: the actual commands use `-mindirect-branch=thunk` and `-mindirect-branch-register`; the real ELF section contains 17 bytes `e807000000f3900faee8ebf948890424c3`, implementing the retpoline sequence. A real PLT32 relocation at `__wake_up_common+0x46` connects it to the source's indirect `curr->func` callback. It is compiler mitigation output rather than another provider API.

Undefined references are the expected nine shared Linux functions (seven Task/scheduler/signal/wake owners and two kthread stop/park owners) and eight native mutex/IPL/barrier primitives. No other Linux undefined reference appeared. These references remain a separate linking gate.

One compiled C owner validates its source functions and parsed header/types. It does not instantiate every wait-event/timeout macro or establish static initialization, keyed/bit/variable waits, callback draining/lifetime, scheduler-hint parity, Poll/Worker linking, a complete kernel or runtime behavior. The parent acceptance remains PARTIAL.

## Preservation and independent verification

The immutable native baseline covers 594 concrete states. Root independently added eight already pinned F43/F44 report/proof files before execution; their sets are disjoint and form an explicit union of **602 unchanged states**. All 64 F44 source/test/input hashes, earlier successful objects and the original F40 failed evidence remain intact. Old configured `linux_wait.o/.d/.su` were absent before and after. The object exists only in its fresh private directory.

Full source/contract/core/generation and prior artifact checks passed after the actual attempt. Root independently read the raw ELF symbol table/sections and raw dependency files, checked all 602 current states, current working/Git inputs, the complete F32 core and fresh whole-archive hash. Separate reviewers reconstructed both actual compiler command arrays and verified dependency/archive membership, process termination and the compiler thunk. No native command was repeated.

Preparation observers were corrected before execution: source comments were removed before deriving function definitions; extra symbols were retained for causal review; terminal metadata read errors were made reportable. Read-only review observers later corrected BSD process-output formatting and used section extent because the compiler thunk's ELF symbol has size0. Original receipts remain unchanged; the targeted section receipt records the actual 17-byte body. None of these observations was a failed or retried native attempt.

Machine-readable evidence: [HP_F45_NATIVE_GENERIC_WAIT_OWNER_20261110.json](evidence/HP_F45_NATIVE_GENERIC_WAIT_OWNER_20261110.json).

Principal receipts under the HP project base:

- Native status: `4bd582c2d71ca5d9566acbc6d73877df434f09b48b20ce69b596f65bc23c0caf`
- Launcher result: `2ea6636dcfde32844013f1701e897f860d8139a9ba759ce1ed0c87cdfc39ef13`
- Exit: `f2038a8dc25db57075a09c0f3ea1f1ff83c0c05693994562513828c0c5b44c83`
- Root cold verification: `17eab82c6a2d82fdab8f2395206bd93bcdb55b7466765f04af780d243e5f7fdb`
- Root targeted thunk section: `1b39efc42c185929ea0eed9ca65dfd09ac7c01a1ecb23d6d0276d77d80c423db`

F44's 245 source tests remain valid on the unchanged implementation; this step adds the actual native proof. F77, /netbsd, /boot.cfg, EFI/radio and previous configured/private kernel artifacts remain unchanged. There was no production recovery, old recipe execution, link, fullgraph/preparer/model route, kernel build, install, boot, cleanup or hosted CI.

The HP source branch and scoped canonical Git Governance are published and independently read back before step closure. No Mongo projection is modified. The expected SteamDeck project path remains absent/unverified; no other host synchronization is newly claimed.

## Next atomic source gate

F46 is the bounded source/API provenance work for the existing Poll owner and its real Task-entry dependency, preserving the now-proved Wait selection and all older guards. Any later native Poll proof requires its own separately published PRE.
