# F33: native FILE provider input provenance — 2026-11-10

Scoped source admission PASS on HP, NetBSD 11 amd64, andreas uid1000.
The provider builder now supports the verified archive-only NetBSD source
without inventing a Git identity. Its original default clean-Git build path
and native protection checks remain.

## Explicit bounded selection

`--source-archive` and `--provider-contract` must be supplied together.
The selected contract must be the canonical source-owned
`compat/native-file/provider-inputs-f33.json`, SHA256
`f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3`.
It binds the fixed NetBSD pin/archive, the exact complete F32 core receipt
SHA256 `d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794`,
and repository commit `493c85d5ba0e3aabc32a61792f980736a6c1693f`.

The first admitted unit is only `compat/native-file/linux_fd.c`, with six
necessary FILE/MM/UIO headers. Each of the seven files has an exact
commit/path/regular-file Git blob/SHA256 identity. Inherited Git selectors and
replacement objects cannot redirect these reads. Root independently matched
all seven blob identities against the GitHub tree at the pinned commit.

Three repository include roots and two native Linux KPI include roots have
explicit roles and ordering. Directory membership never admits an undeclared
repository header. Native headers remain individual archive-proven files.

## Preserved and additional checks

The default branch retains its source PIN/clean, HP/OS/nonroot, explicit
toolchain/compiler, core overlay/patch/header, configuration/prior-kernel,
strict native flags, private output and input-preservation checks.

The archive branch hashes and parses the same complete F32 receipt payload.
It revalidates all three core objects, patched inputs, patch contracts, native
source/header dependencies, generated configuration, tools and prior artifacts.
Core `lockstat.h` stays independently frozen without requiring unrelated
provider code to consume it.

An independent actual `-M` scan is required before object compilation.
Dependencies are separately classified as exact versioned repository inputs,
patched native headers, archive members or generated configuration. Selected
archive members must match the immutable pinned archive; patched FILE headers
must actually be consumed. Actual `-MD` results must match the earlier set and
bytes, and all inputs and old artifacts are rechecked.

`--preflight-only` uses this admission path but never invokes object compilation.
It reports `PREFLIGHT_PASS / ADMITTED_NO_OBJECTS`, rather than a compile success.

## Executed verification

60 targeted Python tests pass:

- 31 new helper tests for contract/Git/content/role/core/configuration/tool/
  artifact/dependency identities, aliasing and drift.
- 11 new integration tests for paired flags, default dirty-Git rejection,
  preflight no-object behavior, independent dependency scans, unknown headers,
  missing patched headers, command failures, old-artifact creation, explicit
  selection and output preservation.
- 18 existing native preflight/toolchain regressions.

Compiler/preprocessor operations in these tests are controlled test doubles.
No actual preprocessing, TAR member scan or provider object compilation is
claimed at F33.

A bounded real read-only admission additionally passes for the actual seven
repository inputs, include roots and complete F32 core/configuration/object/
dependency proof. A real public CLI call with an archive but no contract exits2
for the precise paired-selection reason, with its requested output still absent.

The initial integration attempt retained 10 passing cases and one test with an
incorrect expected error fragment for an existing F31 protection. Only the test
assertion was corrected. A02 passed all 11 cases plus 18 regressions. Root bound
the final five source hashes and reran only the 11 affected integration cases
because A02 had not recorded that test file's bytes. All prior receipts/logs
remain preserved. No implementation guard was removed.

Independent source and test review found no remaining blocking findings.
[Complete evidence](evidence/HP_F33_PROVIDER_PROVENANCE_20261110.json) binds all
five checked files, test receipts/logs, real-input proof, remote Git anchors and
root verification.

## Governance, safe state and next step

PRE: `state/events/hp-i915-f33-native-file-provider-admission-20261110.jsonl`.
The source acceptance is separate from the following actual native object proof.
No provider preparer, full graph build, kernel link, installation, physical boot,
EFI/radio action, cleanup or hosted CI was executed. F77, installed kernel and
boot configuration are unchanged. Fleet limitations from F28 remain; complete
fleet synchronization is not claimed.

Next F34 invokes the reviewed builder for one actual native `linux_fd.o` with
the fixed provider contract, F32 core receipt, archive and configured toolchain.
It must pass actual dependency/archive proof before compiling, then preserve all
inputs and independently verify object ELF/symbols/hash. A real prerequisite
failure must be retained and classified. Full FILE lifetime, provider graph,
MM/UVM, Compat32 translation, full kernel and physical recovery acceptance
remain open.
