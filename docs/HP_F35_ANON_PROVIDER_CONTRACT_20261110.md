# F35: separately pinned anonymous FILE provider contract — 2026-11-10

Scoped source admission PASS on HP, NetBSD 11 amd64, andreas uid1000.
The native provider builder can select a separate reviewed contract for
`linux_anon.c`. F33's manifest, existing tests and two-header FD requirement
remain unchanged. No native object is claimed at this source step.

## Fixed identities and narrow header policy

The only accepted contracts are the original source-owned F33 path/SHA and
the new `compat/native-file/provider-inputs-f35-anon.json`, SHA256
`c45f3ab9f59602955ec5ebe27974a926316787faa0ff57935e3f1c95ac00214d`.
Copies at other paths, crossed bytes and arbitrary third contracts are rejected.

The new contract pins eight regular Git blobs and raw SHA256 values at
`070f728b6ec617c079a4600c14b3e89867f50b18`: `linux_anon.c`, its
`anon_inodes_netbsd.h` interface and six existing FILE/MM/UIO headers.
All eight identities were independently matched against GitHub. The same
complete F32 core receipt, fixed NetBSD archive and five ordered repository/
native include roots remain required.

The new explicit `required_patched_headers` policy contains only
`sys/sys/file.h`. It must be a nonempty, canonical, duplicate-free list of
actual patched core headers and retain the native FILE header. Validation
occurs before private output creation. Actual dependency scans must prove
the selected header consumption. Without the field, the previous all-patched-
headers default remains, so F33 still requires both `file.h` and `filedesc.h`.

An optional header remains subject to the unchanged dependency binder:
consuming an original unpatched `filedesc.h` is rejected even when that
header is outside Anon's required subset. The selected contract hash and
header policy are recorded in the provider receipt. No artificial source
include was added; actual Anon header consumption is the following native proof.

## Preserved controls

The default public `main` path is byte-equal to the prior version.
HP/nonroot, clean pinned Git default mode, explicit paired archive/contract
selection, compiler/toolchain, strict flags, complete core/patch/header/source/
configuration/object identity, dependency/archive proof, private output and
old-artifact preservation controls remain. F32 `lockstat.h` stays independently
frozen without requiring each provider to consume it.

F33 contract SHA256 remains
`f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3`.
The full F32 receipt remains
`d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794`.
The F34 native FD object remains
`d8d86e0a4448709f57c50fc723871f0ad24849933394c0357d9e128f5c067c6b`.

## Executed verification

All **66 tests** pass on the first attempt: 15 new focused input/policy tests,
9 new builder integration tests, and the unchanged 31 F33 helper plus 11 F33
integration tests. Source hashes before and after each suite agree.
Tests cover fixed/crossed/free contract paths, exact unit/roots, malformed or
empty/duplicate/foreign/file.h-omitting policies, old two-header behavior,
original optional-header rejection, preflight status and dependency drift.
Compiler/preprocessor operations in integration tests are controlled doubles.

A real read-only admission passes for the actual eight Git/working-file
identities, include roles and complete F32 core/configuration proof.
A real public invocation with correct F35 contract bytes copied to a free
path exits2 for the canonical-contract requirement before creating output.
It performs no preprocessing or compilation.

Root independently verified both test receipts and exact five source hashes,
three unchanged F33 hashes, eight remote blob identities, the unchanged default
main body, negative CLI result, F32/F34 identities and protected system hashes.
Independent source/test review found no remaining blocking findings.
No passed suite was repeated for this verification.

[Complete receipts, logs and root proof](evidence/HP_F35_ANON_PROVIDER_CONTRACT_20261110.json)
bind the checked source. Actual native preprocessing, TAR member scanning and
`linux_anon.o` compilation remain NOT_RUN at F35.

## Governance, safe state and next step

PRE: `state/events/hp-i915-f35-anon-provider-contract-20261110.jsonl`.
Only the two tools, separate contract and two new test files changed.
The original F27 checkout, F32/F34 outputs, F77, installed kernel, boot
configuration, EFI and radio remain unchanged. No provider preparer, full graph,
kernel/link/install/boot/cleanup or hosted CI was run. Fleet restrictions remain;
complete fleet synchronization is not claimed.

Next F36 uses this exact contract for one actual `linux_anon.c` native run,
proving real dependency/archive/header composition before compiling a private
object, then independently checking ELF/API symbols and every preserved input.
Full anonymous-file finalization, FILE/Task/RCU lifetimes, MM/UVM, full providers,
Compat32 translation, kernel link and physical runtime acceptance remain open.
