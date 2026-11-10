# F38: native FILE lifecycle owner object — 2026-11-10

The actual HP NetBSD 11 amd64 one-owner proof passes on published F37 source
`bcc8ba6f3d8a5521a2af38bcf86d89a028941860`. The configured native compiler
produces one private relocatable `linux_file.o`; both the independent
dependency scan and compilation exit 0 with empty diagnostic logs.
This is object acceptance only. Task API linking, complete FILE lifetime,
the full provider graph, kernel linking and physical runtime remain open.

## Actual inputs and header routing

The public builder uses the fixed F37 FILE contract, SHA256
`a79eaf94d6f0c9b0ee0b64ed998f7e158b6ad0cb5b305878c79ef1c49a4f2e09`,
with provider inputs bound to real source-fix commit
`4858b14bdb6d94fa27ce1e9d5b966dd98c0637bb`.
All 18 versioned inputs and 16 controller files are frozen before execution.
The F32 core receipt remains
`d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794`.

Actual preprocessing and compilation consume the corrected neighboring
`task_entry_preallocated.h`, all three regular runtime forwarding headers,
and the real scheduler, task and raw-spinlock owners. Raw `.pre.d` and `.d`,
the precompile proof and the object proof agree on all 256 resolved paths
and current hashes:

| Input kind | Actual count |
|---|---:|
| Versioned repository inputs | 17 |
| Pinned native archive files | 212 |
| Generated configuration headers | 26 |
| Patched native header, `sys/sys/file.h` | 1 |

The eighteenth versioned input, `compat/native-entry/task_entry.inc`, is the
separate API definition owner. It stays frozen and is absent from both actual
dependency sets. Its definition is not compiled or linked by this probe.
Neither patched `filedesc.h` nor declared generated lockstat is consumed by
this owner; the entire F32 core proof and lockstat remain independently frozen.
The combined core/provider archive proof binds 350 selected members.

The original F33/F35 contracts, tests, header requirements and all existing
toolchain/configuration/core/private-output/dependency/original-header controls
are preserved. No include override, preparer, replacement type or source
modification is used for F38.

## Artifact and independent verification

Private object: 138048 bytes, ELF64 little-endian ET_REL / AMD64.
SHA256:
`c5853c8d6c5d26958a556a4f568b9f01d08b068165b8a4ec4287b1e381fc14bf`.

All 17 minimum acceptance APIs are defined. The complete global T set also
contains the existing source wrappers `fput_close`, `fput_close_sync` and
the configured compiler's `__x86_indirect_thunk_rax`: 19 FILE definitions
and one compiler thunk. Their origins are accounted for.

Root's first read-only observer incorrectly required exactly the 17 minimum
APIs and stopped on these three additional definitions. The failure receipt
is retained. Inspection of the actual FILE definitions, declarations and
configured indirect-branch flags established the cause. Only the observer
expectation was corrected; the compiler was not rerun and source/guards
were unchanged. The corrected complete-symbol check passes.

Root independently reparses both raw dependency files, verifies every consumed
file hash and all 18 exact Git blobs/current bytes, checks actual ELF bytes,
all symbols, command/log hashes, toolchain/archive/core identities, and every
one of the 434 frozen file states. A separate reviewer independently confirms
the dependency/mapping/input/artifact proof. Both report PASS.
The original F27 checkout remains clean; old FILE artifacts remain absent.
F32 core, previous F27/F34/F36 artifacts, installed kernel and boot settings
are preserved.

The original native run has launcher PID 5942 and provider PID 16227; both
ended. Its durable launch/status/log/exit records remain under
`/home/andreas/projects/hp-i915-f26-20261106/f38-native-file-owner-20261110-a01*`.
The [complete evidence](evidence/HP_F38_NATIVE_FILE_OWNER_20261110.json)
contains the native status, launch/exit and root receipts plus their hashes.
The 98 accepted F37 tests remain valid; F38 changes only these result records.

## Governance and next action

PRE: `state/events/hp-i915-f38-native-file-owner-object-20261110.jsonl`.
No full graph, kernel link, install, physical boot, EFI/radio change, cleanup
or hosted CI was performed. F77 and the protected installed system remain
unchanged. Fleet synchronization is not claimed for unverified hosts.

The next bounded step must establish the exact remaining FILE/Task/provider
dependency owners and their admission contracts before another native object
or link proof. Undefined object symbols remain dependencies, not an error-free
kernel link or evidence of runtime lifetime correctness.
