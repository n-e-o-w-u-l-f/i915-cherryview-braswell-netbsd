# F41: locked worker API declaration and provenance — 2026-11-10

Source/admission PASS on HP NetBSD 11 amd64. The real declaration
`int linux_kthread_wake_locked(struct task_struct *)` is exposed through
a narrow source-owned companion. The original Task implementation, all four
previous contracts and all 129 previous test cases remain unchanged.
Native Task compilation follows separately at F42; F40 remains a failed
historical attempt.

## Actual declaration and same-owner composition

The declaration is derived from
`compat/native-runtime/worker/worker_header.inc:66` and checked against
the definition in `worker/worker.inc:44`. Their exact Git blobs and SHA256
identities are bound in the new contract. The implementation asserts ownership
of `task->lt_lock`; the existing Task caller holds that lock across the call.
The unlocked wake function takes the lock itself and is not a substitute.

New `task_worker_wake_netbsd.h` contains only the existing struct-tag forward
declaration, the exact public prototype and its caller-held-lock precondition.

New `linux_task_worker_owner.c` contains two quote-local includes, in order:
the API companion followed by unchanged `linux_task.c`.
Only this new unit is selected by the new contract. The real private Task
key, reservation/allocation/attachment resources and three existing fragments
remain in one translation unit. The original C body and resource layouts
are unchanged.

The source phase, including corrected source guards, was committed before
manifest generation as real Git commit
`7cab7efa8d9ba6edf6d8c2fa6cc47545f6da007e`.
The retained LOCAL_ONLY receipt describes that intermediate checkpoint.
Final publication includes this commit and the admission/report commit.

## Fifth fixed contract and preserved checks

`compat/native-runtime/task/provider-inputs-f41-task-worker.json`, SHA256
`0741fbe18dfd9600edad6cc490e4f9609fcf706c461e21c067cb1a132adeb0a4`,
binds 15 exact regular Git inputs at the actual correction commit.

The original eleven inputs remain bound; the original C has the contextual
`task_implementation_owner` role. The additional inputs are the selected
wrapper, new consumed API header and both real Worker provenance owners.
The Worker files retain the nonconsumed `api_definition_owner` role and
are forbidden in both preprocessing and compiler dependency proofs.

The builder requires exact binding rows for the original C and API header
before compilation and after `-MD`, alongside all three exact Task fragments.
Wrapper-only selection excludes compiling both original and wrapper units
together. Include roots/order are unchanged.

A separate fixed-digest/full-15-role-shape branch admits the fifth selection.
The original F39 digest/11-role validation tail remains exact. Both Task
profiles have zero required patched FILE headers; original-patched-header
rejection and the whole F32 core proof remain enforced. F33 still requires
both FILE headers; F35/F37 still require patched `file.h`.
The four previous manifest bytes, input bytes and tests remain unchanged.
Legacy Git builder, dependency binder, full-core verifier and existing FILE
header-policy bodies are byte-identical. No compiler/include override was added.

## Verification and retained corrections

All **163 final tests** pass: 12 source/API/locking cases, 9 new provenance,
13 new admission and 129 unchanged previous cases. Source negatives include
20 deliberate signature, include/selection, lock, layout and body mutations.
Final counts include the corrected source cases once.

Independent review found that the first new source-test parser could count a
prototype hidden inside a comment. Its actual false acceptance is retained
with the A01 receipt. The test now extracts declarations from comment/string-
stripped code and rejects an explicit commented-prototype control; source A02
and the final complete run pass. Wrapper and header bytes remain unchanged.
This was a test-guard correction, not a native compiler retry.

The first PRE-publication whitespace check also rejected one extra final
newline in the shortened LAST pointer. That failure is retained; exactly one
newline was removed and validation passed before publication. The previous
26754-byte LAST is preserved byte-exact in
[the published archive](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/5bc638057db0fd25ebd58db1a76e845543705478/archive/2026-11-10-HP-I915-LAST-before-f41.md),
Git blob `0a67d5aa3d9b4553ffb960d8193c49eda7755a26`,
SHA256 `727ea9f553f0267eff78fb357957532dfe6b0ccc8aa99ec6d61dc792e088a9e7`.
The current LAST retains the current route and archive pointer.

Actual read-only admission passes for all 15 Git/current-byte inputs and the
whole F32 core/configuration proof. Root independently checks all five
contracts and their policies, all selected inputs, old native artifacts and
required implementation/API rows. A real public invocation rejects correct
fifth-contract bytes copied to an unreviewed path with exit2 before output,
preprocessing or compilation.

Of the prior F40 445 frozen states, 443 remain exact; the only intentional
changes are the two controller extensions. All original F40 failure artifacts
and absent Task objects remain preserved. Independent source and final
admission reviews report no blocking findings.

[Complete receipts, failure witnesses and hashes](evidence/HP_F41_TASK_WORKER_WAKE_API_20261110.json)
bind the source attempts, real source-fix commit, final tests, actual input/core
admission, root verification, real CLI negative and final source identities.
No real native wrapper preprocessing, archive-member scan or compilation
occurred in F41.

## Governance and next action

PRE: `state/events/hp-i915-f41-task-worker-wake-api-provenance-20261110.jsonl`.
F77, installed kernel, boot configuration, EFI/radio, original F27 checkout
and previous native proofs remain preserved. No preparer, full graph, kernel
link/build, install, physical boot, cleanup or hosted CI was run.
Canonical Git remains authoritative; no Mongo mutation or complete fleet
synchronization is claimed.

F42 executes one actual `linux_task_worker_owner.c` proof with this exact
contract. Original C, new header and all three fragments must be observed
before compilation and after MD, both Worker provenance files must remain
unconsumed, and actual ELF/API/byte/preservation proof must pass.
Any real compiler failure is retained and classified before a new source step.
Worker implementation composition/link and full Task/FILE/RCU/MM/UVM/Poll/Wait,
provider graph, kernel and physical runtime acceptance remain open.
