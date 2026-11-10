# F39: actual Task owner composition and provenance — 2026-11-10

Source/admission PASS on the actual HP NetBSD 11 amd64 workspace.
The existing Task entry fragments now belong to the real `linux_task.c`
translation unit and share its existing resources. A separate fixed Task
contract binds their exact consumed-source identities. Native Task compilation,
linking and runtime are separate acceptance steps.

## Same-owner composition

The C change adds only six lines: the quote-local `task_entry_netbsd.h`
include and a commented block including the three unchanged fragments after
`linux_task_attach_current` and before `linux_task_enter_current`.

| Consumed fragment | Actual definitions |
|---|---|
| `compat/native-entry/task_entry.inc` | `linux_task_entry_enter`, `linux_task_entry_leave` |
| `compat/native-file/task_entry_preallocated.inc` | `linux_task_entry_enter_preallocated` |
| `compat/native-file/task_quiesce_retained.inc` | `linux_task_system_quiesce_retained` |

At this position the original private key, count, state/lock, reservation,
allocation and attachment functions are already defined. Existing get/put
declarations remain available from the unchanged Task header. All three
fragment bodies and all original C bodies remain byte-identical.
No second Task/specificdata runtime, copied type or replacement owner was added.

The new neighboring declaration header forward-declares the existing
`struct task_struct` and declares the four actual fragment APIs with their
existing signatures. Previously bound FILE/Task headers and all F33/F35/F37
manifest inputs remain unchanged.

The native archive's `linux/kthread.h` is byte-identical to the tracked
`compat/native-runtime/worker/base/kthread.h`, SHA256
`4384d635d5049d38bd322009007b04808afeb30e4c99c0e484ba95bfbd10933b`.
Its real native dependency is present. No extra wrapper or include root is needed.

## Fixed consumed-input contract

The tested three-file source phase was committed as real correction commit
`5298bf8cfe5268787ea759ba3df54d5bc1d50ddc` before deriving the final contract.
The retained LOCAL_ONLY receipt describes that historical intermediate state;
final publication includes both commits.

`compat/native-runtime/task/provider-inputs-f39-task.json`, SHA256
`5709061e886f4334c32b2485b98a38c8854ab3929e27ff41ce23192535c273df`,
binds 11 exact regular Git inputs: the C owner, declaration header, three
fragments and six existing Task/scheduler/raw-spin mapping/owner headers.
It selects only `linux_task.c`, the runtime mapping include root and the
two existing native KPI roots, in fixed order.

Every fragment has the distinct consumed `task_fragment` role.
The builder requires all three exact role/blob/SHA rows in the independent
precompile dependency proof and again in the compiler dependency proof.
Unknown repository inputs and FILE's nonconsumed `api_definition_owner`
remain rejected. The same entry snippet is legitimate consumed implementation
under this Task contract and remains nonconsumable provenance under FILE's
separate contract; no general fragment or API-owner exception was introduced.

An empty patched-header requirement is allowed only for the exact reviewed
Task digest plus its complete root/unit/include/input-role shape. Task code
does not acquire an artificial FILE include. F33 still requires both patched
FILE headers; F35/F37 require patched `file.h`; their manifest bytes and
input/test bytes are unchanged. Original versions of any patched header remain
forbidden even when that header is not required by the selected contract.
The whole F32 core receipt, configuration, tools, source and object proof is
still verified independently.

The legacy Git builder body, repository/native dependency binder and full-core
verifier are byte-identical to the previous source. The changes add the fourth
fixed contract, its narrow policy and required-fragment checks.

## Verification and preservation

All **129 final tests** pass: 10 composition, 9 Task-input, 12 Task-admission,
and the unchanged 98 F33/F35/F37 cases. The earlier ten-case phase is included
once in that total. Its 12 targeted negative mutations are all rejected.
All test commands pass on their first attempt; source hashes remain stable.
Admission integration compiler/archive calls are explicitly controlled doubles.

Actual read-only admission verifies all 11 Task Git/current-byte inputs,
all prior contract inputs and the complete F32 core/configuration proof.
Root independently confirms the contract selection/header policies, actual
Git bindings and native kthread equality. A real public CLI invocation rejects
correct Task contract bytes copied to an unreviewed path with exit2 before
output, preprocessing or compilation.

Of F38's 434 frozen prior states, 432 remain exact; only the two intentionally
extended controller files change. All eight F38 private artifact records,
previous native core/FD/Anon/kernel artifacts, original clean F27 checkout,
installed kernel and boot configuration remain preserved.
Independent source and final admission reviews report no blocking findings.

[Complete receipts and hashes](evidence/HP_F39_TASK_OWNER_PROVENANCE_20261110.json)
include source baseline, tests/mutants, actual source-fix commit, admission,
root proof, real CLI negative and final source identities.
No real Task preprocessing, archive-member scan or object compilation occurred
in F39.

## Governance and next action

PRE: `state/events/hp-i915-f39-task-owner-composition-provenance-20261110.jsonl`.
F77, EFI/radio and protected system remain unchanged. No preparer, full graph,
link, kernel build, install, physical boot, cleanup or hosted CI was run.
Canonical Git remains the authority; no Mongo database mutation or complete
fleet synchronization is claimed.

F40 performs one actual native Task object proof through this exact contract.
It must observe all three fragment dependencies before compilation, retain
real native diagnostics, verify ELF/API symbols and preserve all prior objects
and protected inputs. No source repair or guard weakening belongs inside that
native proof. FILE poll/provider completion, Task/FILE/RCU/MM/UVM lifetimes,
full graph/kernel linking and physical runtime remain open.
