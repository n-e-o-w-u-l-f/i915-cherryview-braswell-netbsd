# F43: exact generic callback Wait source recovery — 2026-11-10

Source recovery PASS on the actual HP workspace. The recovered generic Wait
header and C owner match both historical SHA256 identities exactly.
All 200 tests pass; an independent fresh CLI replay reproduces all three
output files byte-for-byte and an existing-output invocation is rejected.
Native Wait preprocessing, compilation, linking and runtime are NOT_RUN.

## Exact primary inputs and recipe witnesses

The producer consumes only two fixed raw snapshots at Linux commit
`fd179f8a05be3ccae366b9b96e176b51fbe54aab`:

| Logical upstream path | Bytes | Git blob | SHA256 |
|---|---:|---|---|
| include/linux/wait.h | 45202 | 7e215330199cfea27008f718e0336d0f48bfe17d | f9f53a02fd25a1a1fefdc41310285975d5c1fdce1a1b62282cc05e737ae96417 |
| kernel/sched/wait.c | 14840 | d033f600f48c6fc3a0a088ea5d9f6ed95ec4c86e | 05a9c8d9b1b4cb3a63e1dd59744adf24c8912d108307f46d7e3a6b1f26013e5f |

These exact two already-returned pinned dependency payloads were used, with
no additional repository search, clone or upstream fetch. The named local
Linux-tree variable is unset and no documented local checkout was found;
a clean Linux Git tree is not claimed. Raw snapshots and their provenance
are tracked under `compat/native-runtime/wait-inputs-f43`.

The old `task/generate_wait.py` is retained unchanged as a recipe witness:
blob `384872c7c87595d62497227d7c2c8aaff31e2dd0`,
SHA256 `598d3de2afdf1e6c02ff8aecdde0f4a83c7f32341adbfc791b367a007df378d6`.
The historical `task/SOURCE_SHA256.json` witness is unchanged:
blob `0b1cf16eb8cd424c2c87c4d7e6d19513edc6771f`,
SHA256 `99b37dca5385fa243e3bad9867a36405caab52804423010690c5427193c82662`.
Neither the original top-level generator nor a model/preparer was executed.

## Guarded producer and actual outputs

New `tools/recover_native_wait.py` validates regular canonical same-read
input bytes, fixed sizes/SHA256/Git blobs, duplicate-key-safe provenance and
both recipe/ledger witnesses. It uses no Git, inherited source selectors,
environment-selected paths or network calls.

Checked pure transforms record 49 audit operations. They validate literal
and region anchors, 23 export removals, 15 timeout-predicate call adaptations,
and the exact 23 shadow-wrapper names/order/token counts. Both historical
output hashes must match before any output directory is created.
The original notices are preserved.

The producer admits only a fresh target, forbids input overlap and aliases,
holds/rechecks the parent directory descriptor, and creates directories/files
relative to held descriptors with exclusive/no-follow flags. It prepares
all three payloads before creation and verifies each after writing.
Returned metadata is copied to preserve repeat-call determinism.

The isolated `compat/native-runtime/wait-f43` tree contains exactly:

| Recovered file | Bytes | SHA256 |
|---|---:|---|
| include/linux/wait.h | 49625 | 61ef59279676174b3394e88451ff828a83bff7c50d679b4a946d3daee45dfa86 |
| linux_wait.c | 14091 | 4a933c0bb0cbf5c2483c22d8fb7a36b7166d0b52b2e30bf9223d69d9a8cd0c69 |
| provenance.json | 8037 | a84ac39db9642f7a935a25a6ac3b0721b568be6132a8221cab42b454f7972078 |

Producer SHA256:
`daa986375fe841baf5cf85f80dadbf675c9030695a221a065dbd8ea70b45b521`.
The deterministic provenance records exact sources/witnesses, all operations,
historical outputs and still-open native/lifetime gates.

## Tests, independent checks and preservation

One combined batch passes all **200 tests**: 37 new recovery cases and
163 unchanged existing cases. Tests cover raw/pin/blob/size/provenance drift,
recipe/ledger identity, positive and missing/duplicate transformation anchors,
historical-output mismatch, fresh-output/no-clobber, input/output aliases,
directory-parent substitution, corrupted output/provenance, copied return
metadata and invalid input/count behavior under Python `-O`.

Pre-production review identified stale parent admission, missing provenance
readback and returned metadata aliases. Those narrow guards and their
independent negative controls were completed before the single final test
batch and tracked recovery. No failed production output was accepted.

After the tests, one actual tracked recovery exits0. Root independently
verifies raw snapshot bytes/Git blobs, performs the exact 49-operation
in-memory transform, and executes a separate fresh CLI replay. Header, C and
deterministic provenance all match the tracked files byte-for-byte.
A real second invocation against the replay target exits1 without changing it.

All 50 preserved old source/input/contract/test files remain unchanged.
Root and an independent reviewer rehash all 468 prior frozen states and the
F42 private artifact set with no drift. All five contracts, their input sets,
the original three runtime mappings, old recipe and historical ledger remain
unchanged. F40 failure evidence is preserved. No shared controller changed.

The [complete receipts and source identities](evidence/HP_F43_GENERIC_WAIT_RECOVERY_20261110.json)
bind the 200-test batch, actual tracked recovery, input proof, pure transform,
fresh replay/no-clobber and final source aggregate. Independent producer,
test and actual-output reviews report no outstanding findings.

## Governance and next action

PRE: `state/events/hp-i915-f43-generic-wait-owner-provenance-20261110.jsonl`.
The prior 15680-byte owner record is archived byte-exact:
[pre-F43 owner](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/c14c222f2b5c0b5d0ffa432daa50b677a9aa52b8/archive/2026-11-10-HP-I915-before-f43.md),
blob `56cf1132b34b15605b0d28eb62ee2376381e6172`,
SHA256 `dc1ce9657d9d74a7f357bce23e50025ebad840ffe8c75af24add85587ed0ad57`.
The bounded owner retains all current scalar bindings, full-kernel history,
parent boundaries and prior report links.

Next F44 establishes a separate fixed Wait source/admission contract, outside
the exact three-file recovered tree. It should require the Wait C/header and
six actual Task mapping/owner headers, freeze seven generation-provenance
owners as nonconsumed, cross-check the generation chain and retain all five
existing selections. Actual transitive dependencies need a later governed
native scan; no native Wait object is claimed here.

Static waitqueue initialization, fatal-only sleeps, scheduler hints,
boundary/owner draining, Poll/RCU/free lifetime and variable/bit waits remain
open. F77, installed kernel, boot configuration and EFI/radio remain unchanged.
No native PP/CC/archive scan, kernel/Worker link, full graph, boot, install,
cleanup, hosted CI or Mongo mutation was performed. Parent driver acceptance
remains PARTIAL.
