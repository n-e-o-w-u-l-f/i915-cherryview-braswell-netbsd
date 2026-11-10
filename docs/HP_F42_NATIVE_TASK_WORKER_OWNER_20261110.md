# F42: native Task owner with locked worker API — 2026-11-10

Actual HP native object acceptance PASS. The fixed F41 wrapper compiles the
unchanged Task implementation with the real locked-worker declaration visible.
Both the independent native dependency scan and strict compiler exit0 with
empty diagnostic logs. The F40 failure and its original evidence remain intact.

## Real artifact and source identities

Runner source: `65ed55574dff00ade7d2783e6499c86a263a66c6`.
Provider correction commit: `7cab7efa8d9ba6edf6d8c2fa6cc47545f6da007e`.
Fixed fifth contract SHA256:
`0741fbe18dfd9600edad6cc490e4f9609fcf706c461e21c067cb1a132adeb0a4`.

Private `linux_task_worker_owner.o` is 153680 bytes, ELF64 little-endian
ET_REL / AMD64. SHA256:
`b867436f6175a4c0e42fd45a90d3833e3cb5aa4489cd8fda67536ad9762499db`.

It defines exactly 25 public T symbols: 21 from unchanged `linux_task.c`
and four from its real entry/preallocated/retained-quiesce fragments.
No expected symbol is missing and no additional T symbol is observed.
The object retains the expected undefined external
`linux_kthread_wake_locked` reference. Its real declaration is visible;
Worker implementation composition and linking remain separate.

Launcher PID12670 and provider PID9455 have both ended. Durable original
launch/status/log/exit records remain under
`/home/andreas/projects/hp-i915-f26-20261106/f42-native-task-worker-owner-20261110-a01*`.
Exactly one public native invocation ran, with one `-M` and one `-MD/-c`
command. No source repair, rerun or compiler/include override was used.

## Actual dependency and provenance proof

Raw `.pre.d`, compiler `.d`, precompile proof and object proof agree on
all 233 canonical paths and hashes:

| Actual kind | Count |
|---|---:|
| Versioned repository dependencies | 13 |
| Pinned native archive files | 195 |
| Generated configuration headers | 25 |
| Patched native provider headers | 0 |

All 15 declared repository inputs are bound before and after execution.
Thirteen are actually consumed, including the selected wrapper, unchanged
original C, new API companion, Task mappings/owners and all three fragments.
The two real Worker provenance owners stay frozen and are absent from both
dependency sets. Required implementation/API/fragment checks pass at both
native boundaries.

The Task selection requires no artificial FILE include. The entire F32 core
receipt/configuration/declared lockstat remains independently revalidated and
preserved; lockstat and patched FILE headers are not consumed by this provider.
The combined core/provider archive proof binds 348 members.

Root independently reparses both raw files, rehashes every consumed path,
verifies all 15 exact Git bindings, actual ELF bytes and all symbols,
checks command/log/receipt hashes and process completion, rehashes the pinned
archive and all 468 frozen states. A separate reviewer independently confirms
the same proof, including a fresh archive hash. Both report PASS.

All 28 controller hashes and 468 frozen states remain unchanged.
The original configured Task and wrapper artifact stems remain absent;
only the new private object and sidecars were produced. Original F40 failed
status/logs/dependencies/stack sidecar/absent object, previous F27/F32/F34/F36/
F38 artifacts and protected kernel/boot state remain exact.

The [complete evidence](evidence/HP_F42_NATIVE_TASK_WORKER_OWNER_20261110.json)
contains native status, launch/exit, root proof and all artifact/receipt hashes.
The accepted F41 163-test result remains valid; F42 changes only result records.

## Governance and next action

PRE: `state/events/hp-i915-f42-native-task-worker-owner-object-20261110.jsonl`.
F77, installed kernel, boot configuration, EFI/radio and original F27 checkout
are preserved. No preparer, full graph, Worker/kernel link, install, physical
boot, cleanup or hosted CI was run. This is one relocatable Task-owner proof;
full Task/FILE/RCU/MM/UVM/provider/kernel and runtime acceptance remain OPEN.

Next F43 establishes the missing generic callback Wait source/header owner.
The current native `linux/wait.h` is an empty guard; the tracked generator
and source manifest refer to exact frozen Linux `include/linux/wait.h` and
`kernel/sched/wait.c` and historical generated output hashes.
The existing generator requires reviewed raw-input/provenance/transform-count
and fresh-output safeguards before isolated recovery. Preserve notices and
all five current contracts/input/test bytes; diagnose any historical output
hash mismatch instead of accepting new identities silently. Variable/bit waits,
Poll/Worker admission and native Wait compilation remain later separate gates.
