# HP F49 — exact Worker source recovery

F49/A01 is **PASS for source recovery and provenance** on the HP, NetBSD 11 amd64 F77, user andreas. The actual source/test controller completed with exit zero. This step ran **zero native preprocessor/compiler commands**. Parent driver completeness remains **PARTIAL**.

## Why a complete Worker owner is required

The F42 Task object still refers to `linux_kthread_wake_locked`. Its existing Worker fragment requires both private `struct linux_kthread` state and the static `linux_kthread_spawn` helper, so assigning that fragment to Task or compiling it alone cannot establish the actual translation-unit owner. The complete adapted Worker owners were absent. F49 restores those two owners in the isolated `compat/native-runtime/worker-f49` source layout.

## Exact derivation

The new `tools/recover_native_worker.py` authenticates seven existing source/witness inputs against Git commit `e7d7100c44322d3209d8f43d1d3a3842b52b340b`: two pinned NetBSD bases, the complete patch0032, the implementation/declaration fragments, the historical generator and the integration record. These inputs are unchanged in execution HEAD `53b793b1cce6ec1b77440ff217bd263a0416c3eb`. Git replacement/directory selectors and lazy fetching cannot replace those local identities.

Only the two exact Worker-owned sections of the fourteen-owner patch are replayed in memory. Every original line/context, old/new position and count is checked across **25 C hunks + 2 header hunks**. No complete patch application occurs and the other twelve owners remain unchanged. The historical generator is authenticated as a read-only witness and is never executed.

Recovered outputs:

| File under worker-f49 | Bytes | SHA256 |
|---|---:|---|
| linux_kthread.c | 19566 | 31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274 |
| include/linux/kthread.h | 4700 | 97c094ab5fbc3688334875500c23d5053186d35e6342d2668ce63659335b8814 |

The C retains the complete original Worker fragment; the header retains the complete declaration fragment. The private structure is at C line55, static spawn helper at183, locked-wake definition at415 and declaration at header132. The final selected `linux_kthread_fini` at C86–87 checks `linux_task_system_fini()` and asserts its result. The older generator discards that result; it was not used as the recovery recipe. Earlier integration build claims remain historical and do not substitute for a current native Worker object.

`provenance.json` binds all seven input paths/blobs/hashes, both selected section hashes, all 27 hunk operations and the producer hash; derivation also enforces committed Git mode100644. Canonical validation checks every field, including types, ownership, open gates and execution flags, before any output creation. Output files are created exclusively; provenance is written last and read back. Failed publication retains partial new output for inspection and does not report success. No atomic directory transaction is claimed.

## Actual HP verification and preservation

Published/read-back PRE is `31d151efb7398f439e855ab944c272a8dfebdba9`. The actual HP run performed one source derivation check, **32 passing focused tests**, then one source recovery publication. All three commands exited zero. Tests exercise real private Git fixtures, selected/unselected tampering, exact hunk replay, canonical provenance, input/output aliases, output collisions and retained partial-write failures. Fixtures were restricted to the newly owned bounded test directory, which is empty and retained after testing.

The source controller verifies all original Poll26/Wait15 provenance and the full F32 native-core proof before and after source recovery. All old seven provider contracts, helpers, tests, original sources/fragments/recipe/patch, native successes/failures, archive/tools/configuration, durable F48 backup and protected kernel/boot files remain unchanged. The frozen baseline contains1984 old states; including the new immutable plan/baseline/controller, the final preserved set contains1987 states. The unchanged **287 earlier passing tests** are reused with actual Git/content identity evidence; the 32 F49 tests were executed on the HP.

The original execution receipt truthfully leaves external review pending. A later independent source/provenance/replay/preservation receipt completes that review without editing the original result. The [machine evidence](evidence/HP_F49_NATIVE_WORKER_RECOVERY_20261111.json) contains the baseline, raw command/test results, recovery provenance, independent receipt, source/artifact hashes and controller code.

## Remaining gates

The next gate is a separate exact Worker provider input contract and its protection tests. Native preprocessing/compilation, Task/Wait/Worker link closure, worker stop/park/drain/lifetime behavior, full kernel and physical hardware acceptance remain open. No existing admission was broadened, no native Worker build was claimed, and no link/install/boot/EFI/radio change or old-artifact cleanup occurred. HP and the published GitHub branch are verified here; other hosts were not revalidated.

## Final publication check

The first staged whitespace check found one extra final LF in the new test file (initial25378B/d10cb0f5335cfa53b11e8e3bb1dd5821dd013e4b2aa029d740b7903ed87ee6a3). Exactly that LF was removed; Python AST equality was independently confirmed. The final25377B test file is b0ecd5e2bcc74d731e76fb5e830a75c53c9b87eade715082db6b8f0b91a2caa1. The same32 tests passed again on the HP (exit0), using only the existing owned fixture directory. Thus there were four source commands in total, including the final validation; there were zero native compiler commands. Original plan/controller/test-log/independent receipts remain unchanged and retain the executed initial test bytes by hash; machine evidence also preserves their complete original test source and the final validation output. Producer and generated C/header/provenance identities are unchanged.
