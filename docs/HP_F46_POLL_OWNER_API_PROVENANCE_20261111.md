# HP-I915 F46: Poll owner API and input provenance

F46 source and tests are verified. The separate Poll wrapper and seventh fixed contract preserve the previous protections. All 287 tests passed on the HP. The complete original F46 acceptance remains **BLOCKED** because 49 historical native build inputs under /tmp are absent; the full F32 core recheck cannot run.

## Source ownership

The unchanged linux_poll.c calls linux_task_entry_enter and linux_task_entry_leave at lines 308 and 314. Their existing declaration companion is compat/native-runtime/task/task_entry_netbsd.h; their actual definitions remain in compat/native-entry/task_entry.inc. New linux_poll_owner.c includes that declaration header before the original Poll C. It copies no declaration, implementation or Task layout.

The wrapper inputs were published and fetched back at d828f558b16806130c9a044e9795ca89e3c1f022 before the new contract bound them. The original Poll C, declaration companion, Task fragments and existing mapping headers remain byte-identical.

## Exact seventh selection

compat/native-file/provider-inputs-f46-poll.json has SHA256 9f477521b790e036aaa0dbfddccee1c1ebb06bf62c6034c3d5b4d8b4e5e0db60. It binds 26 real paths, Git blobs and SHA256 values to the published input commit. Seventeen inputs must appear in both the independent dependency scan and the compiler dependency proof. Eight generation-proof owners and the Task-entry API definition owner remain frozen and forbidden as compiler dependencies.

The sole unit is linux_poll_owner.c. Include order is the narrow FILE, MM, UIO, recovered Wait and runtime mappings, followed by the two existing native common/drm2 roots. The patched sys/sys/file.h remains required. No broad compatibility include root is admitted.

Poll has its own exact dispatch and never supplies a Poll-shaped contract to the existing Wait verifier. It separately loads the unchanged sixth fixed Wait contract, verifies its 15 Git-bound rows and generation chain, and cross-checks all 15 shared path/blob/SHA identities. Recovered linux_wait.c is proof-only for Poll. The referenced Wait proof is checked before output creation and again during final verification.

The previous six contract files, Wait checks, core proof, default Git mode, archive checks, original-patched-header rejection, private-output checks and proof-owner dependency prohibitions remain intact.

## Validation

The HP ran 19 suites: all 245 previous tests plus 42 new tests, every command exit zero. New tests cover all 17 consumed-input omissions and all nine proof-owner dependency rejections in both dependency stages, full binding identities, exact selection and include order, original API ownership, shared Wait provenance, duplicate/cross-linked JSON and final generation/core drift. Builder integration tests use private fixtures and simulated compiler results.

Actual read-only checks verified all 26 Poll Git identities, the separate 15-input Wait contract, its generation evidence and the old six policies. Two actual CLI negative checks exited 2 without creating output: preflight without archive selection and the unavailable historical native toolchain. An actual broad-include admission check and full native core verification remain blocked by those missing prerequisites; passing fixture tests do not replace them.

All 1,327 states frozen at the start of this run remain unchanged, including all 177 previously tracked test files, six old manifests, protected kernel/boot state and durable prior private artifacts. Of the old 602-state F45 baseline, 551 states still match, two controller files were authorized for this change, and 49 historical temporary states were already absent at re-entry. Those absences are recorded explicitly and are not claimed as preserved native proof. The original checkout remains clean at 5c7ac64c8c740701365dfbf3bf9159cc13fcf344.

Independent source/AST review found no actionable issue. No actual native preprocessing, compilation, production recovery, link, full kernel build, installation, boot, EFI/radio change, cleanup or hosted CI ran in F46.

## Recovery dependency and synchronization

The missing paths include the configured Makefile, generated headers, prior three-owner object/dependency/stack-use files and original toolchain paths. The durable F26 artifact set does not contain all of their original bytes. Reconstructing or restoring them requires a separate scoped PRE and exact provenance checks. No guard, old contract or core receipt was relaxed to accept the missing state.

Detailed receipts and the exact missing-state list are in [the evidence](evidence/HP_F46_POLL_OWNER_API_PROVENANCE_20261111.json). Source and evidence are published on work/hp-f28-modern-provider-integration-20261109, followed by scoped Governance POST and independent remote readback. Only the HP and canonical Git publication are verified; other hosts remain unverified. The expected SteamDeck source folder is absent.

The next safe action is to establish the exact native recovery inputs and publish a separate recovery PRE, then re-run the original full core acceptance before any native Poll attempt. F77 and the protected boot files remain unchanged; the parent project remains PARTIAL.
