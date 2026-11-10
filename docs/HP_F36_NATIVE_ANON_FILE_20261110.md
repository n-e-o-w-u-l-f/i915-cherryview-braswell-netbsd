# F36: actual anonymous FILE provider object — 2026-11-10

Scoped native object PASS on HP, NetBSD 11 amd64, andreas uid1000.
The public F35 builder compiled `linux_anon.c` through its separate fixed
contract. No provider source, include override or guard change was needed.

## Exact admitted inputs

Runner: `0b40ca4aac08fd3c5367b8dc8676304588c4e6ac`.
Eight provider Git inputs remain pinned at
`070f728b6ec617c079a4600c14b3e89867f50b18`.
Selected contract SHA256:
`c45f3ab9f59602955ec5ebe27974a926316787faa0ff57935e3f1c95ac00214d`.
The same full F32 core receipt, fixed archive and actual F27 configured
compiler/strict kernel flags were used.

The real scan and postcompile proof consume exactly `sys/sys/file.h` from
the patched header set. `filedesc.h` is not consumed by this unit. The original
F33 FD contract and its two-header requirement remain unchanged. Core
`lockstat.h` remains independently frozen without provider consumption.

## Actual result

The real independent `-M` scan and subsequent `-MD -c` command both exit0
with empty diagnostic logs. The archive proof passes before compilation.
Actual scan and compilation dependency sets and bytes match.

| Consumed role | Count |
|---|---:|
| Exact versioned repository files | 8 |
| Archive-backed native files | 204 |
| Generated options headers | 25 |
| Patched FILE header | 1 |
| Total | 238 |

The fixed archive is verified through a bound regular descriptor; the selected
core/provider union contains 344 archive members. This is used-subset
provenance, not a clean Git or full source-tree claim.

`linux_anon.o`: **100,944 bytes**, SHA256
`48e69c1b7cf3b73af35becf1c8202769ceecc5b175c6f02d65e50ff687305422`.
It is an ELF64 little-endian x86-64 relocatable object. All seven required
defined public T symbols are present:
`linux_anon_inode_init`, `linux_anon_inode_fini`, `linux_anon_inode_busy`,
`linux_file_alloc_named`, `anon_inode_getfile`,
`anon_inode_getfile_fmode` and `anon_inode_getfd`.

Launcher PID11870 and provider PID4588 completed PASS/exit0. Private output:
`/home/andreas/projects/hp-i915-f26-20261106/f36-native-anon-file-20261110-a01`.

## Independent readback and preservation

Root independently rechecked object bytes/hash/ELF/API symbols, all consumed
hashes, both raw dependency files, archive identity and every selected archive
source hash, the five F35 files and three preserved F33 files. All **411 frozen
inputs** remain unchanged, including 29 prior artifact states: F27 old9, F32
core9, F34 five private object/dependency/stack/status files and the continued
absence of six old FD/Anon artifacts.

F32 core receipt and configuration, prior kernel, tools, installed kernel and
boot configuration remain unchanged. F34 `linux_fd.o` remains SHA256
`d8d86e0a4448709f57c50fc723871f0ad24849933394c0357d9e128f5c067c6b`.
The original F27 checkout remains clean.

The first root readback assertion expected only five code entries; the launcher
also binds three preserved F33 entries. Exact inspection confirmed all eight.
The verifier was corrected to compare that complete union and the read-only
checks passed. Its initial failure record is preserved. The native provider
run and source were not repeated or changed. A temporary remote-tool connection
timeout delayed retrieval; the saved successful result was observed before
continuing. No native preflight or compiler failure occurred.

[Summary, launch, exit and root records](evidence/HP_F36_NATIVE_ANON_FILE_20261110.json)
and [complete native provider status](evidence/HP_F36_PROVIDER_STATUS_20261110.json)
bind the exact artifacts. The [66 F35 source tests](HP_F35_ANON_PROVIDER_CONTRACT_20261110.md)
remain valid; no unchanged suite was repeated for this native run.

## Boundaries and next action

PRE: `state/events/hp-i915-f36-native-anon-provider-object-20261110.jsonl`.
No preparer, full graph, kernel link, installation, physical boot, EFI/radio
change, cleanup or hosted CI was executed. F77 remains running. Fleet
restrictions remain and complete fleet synchronization is not claimed.

This is one native relocatable object. Full anonymous-file finalization,
FILE/Task/RCU lifetimes, MM/UVM, providers, Compat32 translation, kernel link
and physical runtime acceptance remain open.

The next direct owner is `linux_file.c`, which supplies reservation,
allocation and final reference release. Its current local task-entry header
include does not match the tracked FILE header location. Its additional
pagemap/task/scheduler/MM header closure needs exact reviewed ownership before
a separate contract or object run. Resolve that small source/header-admission
boundary while preserving both existing contracts and all header/provenance
guards; the Anon contract alone does not admit this owner.
