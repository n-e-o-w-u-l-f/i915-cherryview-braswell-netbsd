# F37: FILE Task-header mapping and provenance — 2026-11-10

Scoped source/header-admission PASS on HP, NetBSD 11 amd64, andreas uid1000.
The FILE lifecycle owner now resolves its intended Task headers and has the
public leave declaration derived from the actual tracked native API owner.
A third fixed input contract binds the repaired Git commit and exact owners.
No native object or Task runtime is claimed at F37.

## Narrow source correction

`linux_file.c` changes one include:
`<linux/task_entry_preallocated.h>` becomes `"task_entry_preallocated.h"`,
the actual tracked neighboring FILE header.

That local header adds only the provenance comment and
`void linux_task_entry_leave(struct task_struct **);`.
The actual definition is in `compat/native-entry/task_entry.inc`,
SHA256 `8ea9c5916936e90ec5957f32c10fda2f0e92ec5a7a891d2d322b33d73f0cc026`.
Its signature, existing FILE `&entry` call and the public declaration
documented by native integration patch0037 agree. No Task implementation or
replacement type was invented.

Three regular public forwarding headers map the Linux include namespace to
the unchanged tracked native owners:

| Forwarder under native-runtime/include/linux | Actual owner |
|---|---|
| sched.h | native-runtime/task/sched.h |
| task_netbsd.h | native-runtime/task/task_netbsd.h |
| raw_spinlock.h | compat/linux/raw_spinlock.h |

Each has its own guard and exact relative include. Owner guards and bodies
are preserved. The real raw spinlock owner uses native kmutex primitives.
The extra runtime include root is explicit only in the new FILE contract,
before native KPI roots; no broad compat include or alias exception was added.

## Real versioned binding and nonconsumed API evidence

The six-file source correction passed eight focused tests and independent
review before Root created real local commit
`4858b14bdb6d94fa27ce1e9d5b966dd98c0637bb`.
Its LOCAL_ONLY checkpoint is retained as historical evidence. Final source
publication includes that ancestor and the subsequent admission change.

The third canonical contract,
`compat/native-file/provider-inputs-f37-file.json`, SHA256
`a79eaf94d6f0c9b0ee0b64ed998f7e158b6ad0cb5b305878c79ef1c49a4f2e09`,
pins the real repaired commit, not uncommitted bytes.
Its 18 individually bound Git inputs comprise 17 potential provider inputs
and the separate `api_definition_owner`. All wrappers, actual Task/raw-spin/
MM owners and local API header have exact path/blob/SHA256 identities.

The definition owner is checked before and after execution with the complete
repository input set. It is explicitly rejected if it appears in either actual
preprocessor or compilation dependencies. It supplies API provenance and is
not silently compiled or treated as a provider header. The public declaration
does not prove that Task hooks are compiled, linked or operational.

The contract retains the fixed F32 core receipt and archive, requires patched
`sys/sys/file.h`, and names four repository plus two native include roots.
Every actual dependency still needs its own reviewed provenance.

## Preserved controls and verification

The existing builder is byte-unchanged. F33 and F35 manifests, tests and header
requirements remain unchanged, including the original-patched-header rejection,
clean-Git default, strict compiler/toolchain/configuration/core proof, private
output, independent dependency scan and input/artifact preservation controls.
The helper adds only the third fixed path/SHA and API-definition-consumption
rejection.

All **98 final tests** pass: 17 mapping/integration, 15 focused FILE provenance,
and the unchanged 31/11 F33 plus 15/9 F35 suites. These include the eight
earlier source mapping cases; they are not counted twice.
Before/after source hashes agree; all attempts pass. Integration PP/CC calls
are controlled test doubles.

Actual read-only admission passes for all 18 repaired-commit Git/working-byte
inputs and the complete F32 core/configuration proof. A real public invocation
rejects correct FILE contract bytes at a free path with exit2 before output.
Root independently verifies the exact local fix tree, all current source hashes,
preserved files, 18 Git entries, 13 unchanged original owners against GitHub,
the unchanged builder and protected system/previous object hashes.
Independent code/test review reports no blocking findings.

[Complete receipts, logs and root verification](evidence/HP_F37_FILE_TASK_PROVENANCE_20261110.json)
bind both phases. No actual provider preprocessing, archive-member scan or
compilation was performed at F37.

## Governance, safe state and next action

PRE: `state/events/hp-i915-f37-file-owner-header-provenance-20261110.jsonl`.
F77, installed kernel, boot configuration, EFI/radio, original F27 checkout,
F32 core and prior FD/Anon objects are preserved. No preparer, full graph,
kernel/link/install/boot/cleanup or hosted CI was run. Fleet restrictions remain;
complete fleet synchronization is not claimed.

Next F38 performs one actual `linux_file.c` native proof with this exact
contract. Actual dependency/archive/header checks and API-owner exclusion
must pass before compilation; actual ELF/API symbols and all preserved inputs
must be verified afterward. Retain and classify native prerequisites rather
than broadening guards. Full FILE/Task/RCU/MM/UVM lifetime, API linking, complete
providers/kernel and physical runtime acceptance remain open.
