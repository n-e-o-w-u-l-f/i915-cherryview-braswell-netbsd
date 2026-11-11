# HP-I915 F46: Poll owner API and input provenance

F46 is **PASS for its complete original source/admission criterion** after A02 revalidation. The Poll wrapper exposes the existing real Task API, the seventh fixed input contract preserves the previous protections, and all 287 source tests passed. Actual native Poll preprocessing and compilation remain the separate F48 gate.

## Source ownership and fixed inputs

Unchanged linux_poll.c calls linux_task_entry_enter and linux_task_entry_leave at lines 308 and 314. Their declaration companion remains compat/native-runtime/task/task_entry_netbsd.h; the real definitions remain in compat/native-entry/task_entry.inc. New linux_poll_owner.c includes that companion before the original Poll C. It copies no declaration, implementation or Task layout.

The wrapper inputs were published and fetched back at d828f558b16806130c9a044e9795ca89e3c1f022 before the new contract bound them. Implementation/tests were published at c55836ef62fae1b3f5d314ecc383a6c713160755. Original Poll C, API companion, Task fragments and mapping headers remain unchanged.

compat/native-file/provider-inputs-f46-poll.json has SHA256 9f477521b790e036aaa0dbfddccee1c1ebb06bf62c6034c3d5b4d8b4e5e0db60. It binds 26 actual paths, Git blobs and SHA256 values. Seventeen must be consumed in both independent and compiler dependency proofs; eight generation-proof owners and one API definition owner are frozen and forbidden as compiler dependencies.

The sole unit is linux_poll_owner.c. Include order is narrow FILE, MM, UIO, recovered Wait and runtime mappings, then the two native common/drm2 roots. Patched sys/sys/file.h remains required.

Poll has its own exact selection. It separately loads the unchanged sixth fixed Wait contract and its 15 Git-bound rows, verifies the same-read generation chain and cross-checks every shared path/blob/SHA identity. Recovered linux_wait.c is proof-only for Poll. The proof runs before output creation and again during final verification. Existing Wait, Git, archive, full core, original-patched-header, private-output and proof-owner guards remain intact; all six previous contract files are unchanged.

## Tests and actual revalidation

The original HP batch ran 19 suites: all 245 prior tests plus 42 new tests, every exit zero. New tests cover all 17 omissions and nine proof-owner dependency rejections in both stages, binding/selection/include order, real API ownership, shared Wait provenance, duplicate/cross-linked JSON and final generation/core drift. Public-builder tests use private fixtures and simulated compiler results.

A02 rechecked all 799 working Git blobs from the implementation/test baseline, including 180 tracked test files. All match c558 exactly; later source changes were only F47 evidence. The 287 recorded results were reused on that verified identity. No implementation or test change justified another identical suite run.

Actual read-only A02 checks verified all 26 Poll Git identities, the independent 15-input Wait contract, both generation proofs and unchanged full F32 core before and after. The original core status remains SHA256 d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794.

Three actual public CLI negative cases exited 2 with the exact expected selector error and no output: a broad compatibility root, original linux_poll.c instead of its wrapper, and replacement of the recovered Wait include root. Rejection occurs before any native dependency scan or compiler command. All 1921 frozen states checked by A02 remain unchanged.

Independent implementation and actual-receipt review confirmed the original criterion. Full receipts, hashes and the exact CLI commands/errors are in [the evidence](evidence/HP_F46_POLL_OWNER_API_PROVENANCE_20261111.json).

## Historical blocker and its recovery

F46 A01 preserved a real re-entry finding: 49 old native build paths under /tmp were absent. Its source/tests passed, but the full core prerequisite remained blocked. That original event and [immutable source evidence](https://github.com/n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd/blob/c55836ef62fae1b3f5d314ecc383a6c713160755/docs/evidence/HP_F46_POLL_OWNER_API_PROVENANCE_20261111.json) are retained.

Separate F47 A02 restored every one of the 49 original path/size/hash identities, ran the unchanged core proof and preserved 1364 states. Configuration and three stock owners required ten successful configuration/dependency/GCC/CTF commands. F47's earlier network-guard failure, causal fix and five focused local regressions remain separately recorded. [F47 recovery](HP_F47_NATIVE_PREREQUISITE_RECOVERY_20261111.md) provides its exact scope and evidence.

F46 A02 reopened the same original acceptance after F47 closed successfully. No old contract, receipt, hash, declaration, body or acceptance condition was weakened to close it.

## Synchronization and next gate

Implementation, updated source evidence and scoped Governance are published on the selected work branch and Governance main, then fetched and compared byte-for-byte. Only HP and canonical Git publication are verified; the expected SteamDeck source folder is absent and other hosts remain unverified.

F77, /netbsd, /boot.cfg, EFI/radio and existing native artifacts remain unchanged. F46 itself ran no actual -M/CC, production generator, full graph, kernel/link, installation, boot, cleanup or hosted CI. The parent project remains PARTIAL.

F48 may perform one separately governed native linux_poll_owner object proof using this exact contract, recovered core and preserved artifacts. Object success will still leave linking, runtime lifetimes, complete providers/kernel and physical acceptance open.
