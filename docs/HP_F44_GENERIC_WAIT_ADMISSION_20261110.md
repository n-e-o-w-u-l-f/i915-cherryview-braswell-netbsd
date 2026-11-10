# HP-I915 F44: exact generic Wait provider admission

F44 is **PASS for source and admission verification**. The sixth fixed contract admits the exact recovered generic Wait owner from F43. All 245 tests passed. Actual native Wait preprocessing and compilation remain a separate F45 gate.

## Selection and provenance

The only new fixed selection is `compat/native-runtime/wait-contracts/provider-inputs-f44-wait.json`, SHA256 `5561d9005df2e8018262fb81437ae5abc88e2cb13a6f7306f604a3d4e728309c`. All 15 regular inputs bind their real path, Git blob and SHA256 to published F43 commit `610c66b412672ca96b0048179d07035929443402`.

Eight inputs must be consumed in both the independent dependency scan and the compiler dependency proof: `linux_wait.c`, its recovered `linux/wait.h`, three Task mapping headers and their three actual owners. Seven generation-proof owners are frozen but explicitly forbidden as compiler dependencies: two raw Linux files, input/output provenance, the historical recipe, its ledger and the guarded recovery producer. The existing API-definition-owner rejection remains in place.

The sole translation unit is `wait-f43/linux_wait.c`. Include order is recovered Wait headers, existing runtime mappings, then the unchanged native common/drm2 roots. Only this fixed digest and full shape allow zero required patched FILE headers. The complete F32 core proof and original patched-header rejection still apply.

The generation verifier hashes and parses the same regular-file payloads, rejects duplicate JSON keys and cross-links the exact upstream pins, raw identities/URLs, historical output sizes/hashes, recipe/ledger/producer witnesses, 49-operation audit and source-only scope. It runs before output creation and again in final verification. It does not import or execute either generator.

A review correction explicitly binds the output provenance payload hash to its separate top-level contract pin. A rebound-whitespace negative checks that invariant. Four additional public-builder integration tests cover initial rejection before output/commands, both complete dependency proofs, missing recovered-header rejection before compilation, and final provenance drift overriding a simulated success.

## Actual validation

The single final batch ran on `hp-tpnw121.lan`, NetBSD 11 amd64/F77, as andreas uid1000: **45 new tests plus all 200 existing tests**, 16 suite commands, every exit code zero. Runner PID23293 completed normally. All 64 recorded source/test/input hashes were identical before and after; all 427 recorded native/protected states were preserved.

Root independently verified all 15 actual working/Git identities and their generation chain, all five previous contracts and policies, and the complete actual F32 core before and after. An actual public CLI invocation with an overly broad include root returned exit2 before any output directory or native command.

A separate final preservation check verified all 466 previous frozen states except the two explicitly authorized shared controller edits, all ten published F43 files and all eight F42 private output artifacts. It also checked all six final F44 code/test hashes. Independent full source and test reviews found no remaining issue.

The existing 37 recovery tests used private fixtures. There was no production recovery, old recipe execution, actual native -M/CC, archive-member scan, link, kernel build, installation, boot or hosted CI in F44. The four public-builder tests use a private mock compiler and prove control flow, not native ABI behavior.

## Evidence and synchronization

Machine-readable evidence is [HP_F44_GENERIC_WAIT_ADMISSION_20261110.json](evidence/HP_F44_GENERIC_WAIT_ADMISSION_20261110.json). Principal private receipts below the HP project base are:

- `f44-wait-tests-20261110-a01/status.json`: `f639c20def1e4cbe551f4a08adb06be947fd3e946e86f217d23dd44ef0183215`
- `f44-wait-tests-20261110-a01/exit.json`: `4c6fe821dd791a5756c1d5047c7cc79c5c506909215a5c0e9c89bcddea8602dc`
- `f44-root-readonly-admission-20261110-a02.json`: `461719e6f56baf77d2b86f1d1bf2bf256acb823521ad70e6af995e7a2cdd298a`
- `f44-root-preservation-final-20261110-a01.json`: `fa128a2bfd401ef7b2b61ec2aea88f2d7976e1451d660956e7e5bd0f26177a15`

The HP work branch is `work/hp-f28-modern-provider-integration-20261109`. Source/evidence and scoped Governance are published with GitHub readback before closing the step. Canonical Git remains the synchronization source; no Mongo projection is modified. The expected SteamDeck project path was absent on the fresh local check, so SteamDeck synchronization is not verified. Other hosts are not newly claimed synchronized.

F77, /netbsd, /boot.cfg, EFI/radio and previous native proofs remain intact. The original F27 checkout is clean at `5c7ac64c8c740701365dfbf3bf9159cc13fcf344`.

## Next gate

F45 may run one actual native generic Wait object proof only after its separate published PRE. It must retain all 15 identities, require the eight inputs in both dependency proofs, exclude the seven generation proofs and preserve all prior artifacts. Success would verify the 25 source-defined public owner functions and parsed header/types. It would not establish every wait macro, static initialization, bit/variable waits, callback lifetime, scheduler hints, Poll/Worker linking, full kernel or runtime acceptance. The parent project remains PARTIAL.
