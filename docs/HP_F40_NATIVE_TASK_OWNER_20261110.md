# F40: native Task owner attempt — 2026-11-10

**Native Task object acceptance: FAIL.** The actual HP configured compiler
stops in `linux_task.c:366` because `linux_kthread_wake_locked` has no
visible declaration. The strict `-Werror=implicit-function-declaration`
check is retained. No `linux_task.o` is produced; ELF/API-object verification
is NOT_RUN. F39's separately verified source/admission result remains PASS.

## Actual execution and successful precompile checks

Runner source: `03b32d5bf82e06a9f983facbbc051be18e4c9495`.
Provider inputs: real correction commit
`5298bf8cfe5268787ea759ba3df54d5bc1d50ddc`.
Fixed F39 Task contract:
`5709061e886f4334c32b2485b98a38c8854ab3929e27ff41ce23192535c273df`.

One public invocation ran on HP NetBSD 11 amd64, andreas uid1000.
Launcher PID 24256 and provider PID 10565 have both ended.
Actual independent `-M` exits0; actual strict `-MD/-c` exits1.
There was no second native invocation or source/guard change.

The native precompile proof and archive admission pass:

| Actual input kind | Count |
|---|---:|
| Exact repository inputs | 11 |
| Pinned native archive files | 195 |
| Generated configuration headers | 25 |
| Patched native headers | 0 |
| Total consumed dependencies | 231 |

All three real Task fragments are present with their required role/blob/SHA.
The combined core/provider archive proof binds 348 members.
Task correctly requires no artificial FILE header; no patched FILE or lockstat
provider consumption is observed. The full F32 core/configuration/lockstat
proof remains independently bound and preserved.

The failed compiler leaves `.d` and `.su` sidecars, retained with the
original `.pre.d`, logs and status. Root and independent review reparse the
raw files: the failed compiler's dependency set equals the successful
precompile set, and all 231 current dependency hashes still match.
That is partial failure evidence, not a compiled-object proof.

## Exact failure and real API provenance

The complete six-line native diagnostic is retained in the evidence.
Its owning error is:

`implicit declaration of function 'linux_kthread_wake_locked'`

The actually consumed archive-native `linux/kthread.h`, SHA256
`4384d635d5049d38bd322009007b04808afeb30e4c99c0e484ba95bfbd10933b`,
equals the tracked base header and lacks this newer worker API.

The real declaration already exists in
`compat/native-runtime/worker/worker_header.inc:66`, and the definition is in
`compat/native-runtime/worker/worker.inc:44`:
`int linux_kthread_wake_locked(struct task_struct *)`.

| Diagnostic owner | Git blob | SHA256 |
|---|---|---|
| worker/worker_header.inc | 70aa0ef127e2b4c8f242f5868d6efda2fdd13c6f | 9f3887613605b06fad70f45bd69f92cd7015de7775a859082bbedb991a2dc1a2 |
| worker/worker.inc | 54576a3a96d24f51788c40ae38fbb1f9b2f5d4e4 | 2ad653da9cb181aa9966e4e0e98b12c3fa0c197574f9d4f0021b9e744359001d |

Neither owner was consumed in the Task attempt. Both identities were checked
locally and independently against published GitHub source.

The caller holds `task->lt_lock`, and the real locked hook explicitly
requires that lock to pin the worker backend lifetime. Its unlocked companion
takes that lock itself and is not a substitute. The existing worker generator
composes the newer header/body fragments; those generated owners are not part
of the selected F39 Task admission.

Classification: source API/declaration admission gap.
Failure fingerprint: `F40_TASK_MISSING_KTHREAD_WAKE_LOCKED_PROTOTYPE`.
Governance review: `CONTROL_SUFFICIENT_AND_FOLLOWED`.
The native strict compiler exposed the missing declaration as intended;
no global rule or compiler guard is weakened.

## Preservation, evidence and next action

All 445 frozen states and 22 controller files remain unchanged. The original
F27 Task object/dependency/stack files remain absent. Previous F27/F32/F34/F36/
F38 artifacts and protected kernel/boot state remain exact. The completed F39
129-test result is not relabelled as native Task acceptance.

[Complete original native status, launch/exit, diagnostic and root verification](evidence/HP_F40_NATIVE_TASK_OWNER_20261110.json)
preserve the failed attempt and hashes. PRE:
`state/events/hp-i915-f40-native-task-owner-object-20261110.jsonl`.

F41 must establish a distinct source-owned declaration from both real API
owners and a new fixed superseding Task selection. Pin declaration/definition
owners as nonconsumed provenance, require the new declaration as an actual
Task dependency, retain all four existing manifest bytes and FILE owners,
and add missing/wrong-signature/locked-owner/provenance rejection tests.
Changed Task source/API bytes require new identities; the old exact F39
selection and failed F40 record remain historical rather than being weakened.
A new native Task object proof follows only after that source/admission gate.
Worker implementation composition/link remains separate.

F77, installed kernel, boot configuration and EFI/radio are unchanged.
No full graph, source preparer, link, kernel build, install, physical boot,
cleanup or hosted CI was performed. Complete Task/FILE/RCU/MM/UVM/providers,
kernel link, physical KMS and runtime acceptance remain OPEN.
