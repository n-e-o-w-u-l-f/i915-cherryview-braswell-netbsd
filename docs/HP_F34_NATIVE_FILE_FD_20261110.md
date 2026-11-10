# F34: first actual native FILE FD provider object — 2026-11-10

Scoped native object PASS on HP, NetBSD 11 amd64, andreas uid1000.
The public F33 provider builder compiled the real `linux_fd.c` after completing
its independent dependency and archive proof. No provider source was repaired
and no admission check or include-root override was added for this run.

## Source identities

Runner source: `1d6381e66cc8faa9d0094476d258262282b3e5f1`.
Seven provider input blobs remain pinned at
`493c85d5ba0e3aabc32a61792f980736a6c1693f`.
The reviewed F33 contract remains SHA256
`f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3`.
The complete F32 native core receipt remains SHA256
`d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794`.

The actual F27 configured compiler and strict kernel flags were used with the
three reviewed repository include roots and two native Linux KPI roots.
The original clean-Git default path and all F33 input controls are unchanged.

## Executed native result

Both real commands exit0 with empty diagnostic logs: an independent `-M`
scan, followed only after provenance acceptance by `-MD -c` compilation.
Actual precompile and postcompile dependency sets and bytes agree.

| Consumed input role | Count |
|---|---:|
| Exact versioned repository files | 7 |
| Archive-backed native files | 204 |
| Generated options headers | 25 |
| Patched native FILE headers | 2 |
| Total dependencies | 238 |

The fixed archive is SHA256-verified through a bound regular descriptor. Its
selected proof covers 344 members in the union of the frozen F32 core and new
provider dependencies. This is used-subset provenance, not a clean Git or full
source-tree claim. Both patched `sys/sys/file.h` and `sys/sys/filedesc.h` are
actually consumed. Core `lockstat.h` remains separately frozen and is not
consumed by this provider, as intended.

`linux_fd.o`: **99,328 bytes**, SHA256
`d8d86e0a4448709f57c50fc723871f0ad24849933394c0357d9e128f5c067c6b`.
It is an ELF64 little-endian x86-64 relocatable object. All ten expected exported
functions have defined T symbols:
`linux_fd_system_init`, `linux_fd_system_fini`, `linux_fd_system_busy`,
`get_unused_fd_flags`, `put_unused_fd`, `fd_install`, `fget_raw`, `fget`,
`fdget` and `fdget_raw`.

Launcher PID7210 and provider PID12018 completed; terminal receipts report PASS,
exit0. Private output:
`/home/andreas/projects/hp-i915-f26-20261106/f34-native-file-fd-20261110-a01`.

## Independent verification and preservation

Root independently rechecked object bytes/hash, ELF class/type/machine,
all ten symbols, every consumed dependency hash, archive identity and all 344
selected native source hashes, the five tested runner/contract/test files,
exact F32 receipt, command logs and terminal receipt hashes.

All **397 frozen inputs** remain unchanged. These include 21 prior artifact
states: nine original F27 objects/dependencies/stack files, nine F32 private
core artifacts, and the continued absence of the three old `linux_fd`
artifacts. Configuration, tools, prior kernel, installed kernel and boot
configuration are preserved. The original F27 checkout remains clean.

The earlier [F33 source/test acceptance](HP_F33_PROVIDER_PROVENANCE_20261110.md)
remains valid; no unchanged unit suite was repeated for this native run.
There were no native preflight or compiler failures.

[Summary, launch, exit and root receipts](evidence/HP_F34_NATIVE_FILE_FD_20261110.json)
and [complete provider status](evidence/HP_F34_PROVIDER_STATUS_20261110.json)
bind the exact checked inputs and artifacts. Object/dependency/stack outputs
remain private artifacts; they are not installed.

## Governance and remaining scope

PRE: `state/events/hp-i915-f34-native-file-fd-object-20261110.jsonl`.
No provider preparer, full graph build, kernel link, installation, physical boot,
EFI/radio action, cleanup or hosted CI was executed. F77 is still running.
Fleet limitations remain unchanged and complete fleet synchronization is not
claimed. This result proves one native object and input composition; full FILE
lifetime, Task/RCU, MM/UVM, provider graph, Compat32 translation, final link and
runtime acceptance remain open.

The next bounded source step is a separately pinned contract for
`linux_anon.c`, which connects reservation, anonymous-file construction and
`fd_install`. It needs one additional repository header and a reviewed
per-contract patched-header requirement. Preserve F33's existing contract and
two-header FD requirement; prove the anonymous unit's actual header consumption
in a separate native run after source admission/tests.
