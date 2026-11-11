# F50 — Exact native Worker input admission


F50 adds the eighth reviewed provider profile for the recovered F49 Worker source. The admission result is **PASS** for the exact input contract and read-only generation provenance. Native Worker preprocessing, compilation, linking and runtime remain separate gates.

The actual host is hp-tpnw121.lan (NetBSD 11 amd64, andreas uid1000); the source baseline is 7d9592e01f2efb41bbdd58e15346ffe6d7521136. The new contract is compat/native-runtime/worker-contracts/provider-inputs-f50-worker.json, SHA-256 996f8a34b35e4345c16814f5d72dbd0bdbb1691bdd9a281b3a0bd9fb18560dc3. Its repository input commit is the F49 publication, while the historical F49 generation receipt retains its original input commit e7d7100c44322d3209d8f43d1d3a3842b52b340b.

## Exact input and provenance boundaries

The contract binds 17 repository rows by role, Git blob and SHA-256. Eight rows must be consumed by both the dependency scan and the compilation dependency set:

- The recovered worker-f49/linux_kthread.c translation unit and worker-f49/include/linux/kthread.h.
- The three Task/raw-spin mapping headers in compat/native-runtime/include/linux/.
- The actual Task scheduler and Task owner headers in compat/native-runtime/task/.
- The existing compat/linux/raw_spinlock.h.

Nine further rows provide generation evidence: F49 provenance, the source recovery tool, and the seven original source, patch, fragment and historical witness inputs. All nine are excluded from compiler dependency admission. Proof ownership does not make a file a compilation input.

The ordered repository include roots are exactly compat/native-runtime/worker-f49/include and compat/native-runtime/include, followed by the pinned native sys/external/bsd/common/include and sys/external/bsd/drm2/include roots. The sole unit is linux_kthread.c. The Worker profile requires no patched FILE header; the existing checks against admitting an original header in place of its patched owner remain active. Worker uses the native condition-variable/Task path and has no Wait composition or recovered Wait include root.

The generation verifier reads the 17 bound files as data, checks identities from the same reads, rejects duplicate JSON keys and path aliases, and validates the typed F49 receipt against the pinned seven origins, two recovered outputs, 27-operation audit, two selected patch sections, fragments, definition owners, producer identity and historical witnesses. It verifies the checked linux_task_system_fini() return and assertion in the recovered C source. Admission does not import or execute either the recovery producer or the historical generator.

F49 output identities remain unchanged: C SHA-256 31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274, header 97c094ab5fbc3688334875500c23d5053186d35e6342d2668ce63659335b8814, and provenance 91f22a4fda6bdb0c9e61020acf31ac698c7ee009d65b07d58c7fa55c22a07fa1.

## Changes and retained protections

Six implementation files comprise the change: the two existing shared admission files, the new contract, and three new test modules. The report and machine evidence form the remaining two publication targets, for exactly eight source-repository targets.

In tools/native_provider_inputs.py, the eighth selector, exact Worker shape/identity policy, dependency requirements and pure generation verifier extend the reviewed whitelist and header dispatch. In tools/build_hp_native_provider.py, the Worker archive-provider selection applies those checks before processing and again before success, with separate Worker receipt fields. Existing Task-Worker receipt fields retain their previous meanings.

All seven existing manifests, default provider selection, original Git binding checks, native archive/configuration/toolchain checks, FILE/header requirements, and earlier API/generation proof dependency exclusions remain unchanged. The original F32 full-core verification remains mandatory; its status identity is SHA-256 d1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794.

## Actual HP validation

The actual HP controller and independent review receipts confirm:

| Check | Result |
| --- | --- |
| Exact existing suites | 319 tests rerun |
| New Worker input / provenance / admission suites | 14 + 16 + 10 = 40 tests |
| Total | 359 tests in the exact 23 reviewed suites; all exit 0 |
| Actual public CLI negatives | Broad provider root, old Task-Worker unit, and foreign Wait root each reject with exit 2 before creating the requested output or invoking native commands |
| Worker binding and provenance | 17 rows; 8 required compiler inputs / 9 proof-only; source verification PASS, native scan pending |
| Old profiles and full F32 core | Seven manifest identities and original core verification PASS |
| Preservation | 2006 checked states; no unexplained changes |
| Independent cold review | PASS; receipt SHA-256: 141234454b661766e5de36a0c0ff8e02f4d1ecad236b8b1028aff6363723b3de |

The tests cover all eight required-input omissions and all nine forbidden proof-input consumptions in both dependency paths, contract schema and ordered roots, profile crossing, Git identities, path aliases, typed and duplicate-key provenance, rebound fixture authorities, output and origin tampering, final generation/core failure overriding apparent compiler success, and the public builder through mocked native processes. The retained F49 recovery tests replay source recovery only inside owned temporary fixtures. This does not execute the producer against the canonical worktree.

The declared test resource allows 2048 entries and 64 MiB. The observed retained final state was 0 entries / 0 bytes. This is a final-state check, not a measurement of the peak during test execution.

Preservation reconciles 2001 unchanged physical old states, the two explicitly authorized shared-source replacements, and three new control states, totaling 2006 checked states. Source changes match the six implementation targets. The final result also checks the seven existing contracts, recovered Worker outputs/provenance, native prerequisites, and declared output nonexistence.

The [machine evidence](evidence/HP_F50_NATIVE_WORKER_INPUT_ADMISSION_20261111.json) records the actual test and CLI results, controller outcome, original baseline, current source identities, preservation findings, and independent review. Recorded receipt interval: 171.593822 seconds; initial read-only guards precede this interval. No result is inferred from the earlier local 40-test fixture preview.

## Governance and acceptance scope

The original PRE publication 2131d5c2012d12831a3266014531cf4d52b08ae2, original PRE event SHA-256 a264c66e5b7f9a2913f643e3609f3e44e466507d2770259eb7b007df75a30a60 (a264… prefix) and baseline SHA-256 ae7c9dcd649e23d973ba60434b59ebca9af25b336c4204a76fbdf6914dd9b537 are retained. A fresh Governance check initially stopped before source effects because Governance/main had advanced. The compatible advance was limited to five disjoint metadata path names for another project; HP-I915 projections and global/routing/validator bytes were unchanged. The clean sparse Governance fast-forward to 392534acc53d4e9229cbdf1ee23bb57aaa2c87cf retained both histories without reading foreign project contents. The controller revalidated the current fresh PRE boundary before continuing.

The F49 provenance still literally lists its historical open_gates, including “separate exact provider input contract.” Those historical bytes remain bound by their existing identity. F50 closes that current input-admission gate through this separate eighth contract and evidence; the historical list does not override the current F50 result. Its remaining native compilation, ownership/link, worker lifecycle, kernel and hardware gates remain open.

There was no actual native dependency scan (-M), C compilation, canonical-worktree producer execution, link, installation, boot or runtime execution in F50. No actual public --preflight-only invocation was used because that option would run the native dependency scan. A future Worker object needs a separate reviewed native action. Project-wide kernel and physical-hardware acceptance remains partial.
