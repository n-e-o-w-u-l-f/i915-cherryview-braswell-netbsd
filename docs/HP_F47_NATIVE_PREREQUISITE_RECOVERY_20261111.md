# HP-I915 F47: native prerequisite recovery, attempt A01

F47 remains **BLOCKED**. Attempt A01 stopped during its governance network preflight, before creating the historical native build directory or running native configuration, dependency generation, compilation or CTF conversion. F46 source and all 287 tests remain verified at c55836ef62fae1b3f5d314ecc383a6c713160755; its complete native core prerequisite is still open.

## Concrete recovery plan

Read-only reconstruction established the exact previous 1495-byte make wrapper, the matching compiler and nm, the original configuration seed and derived 189-byte kernel configuration, 17 durable patched source inputs, and nine saved commands for the three original stock owners. Those nine commands include dependency generation, GCC compilation and the required CTF conversion.

A same-build durable drmfb.o, verified against the original manifest, contains the default CTF label. The executor explicitly leaves VERSION unset to reproduce that label. The plan enumerates 724 source-forest entries and 1641 private tool paths, with 305516952 regular tool bytes and one internal symlink. Native configuration has a fixed fresh object-directory resource, a 5000-entry/64-MiB bound, and an immediate per-path inventory before any compilation.

All 49 original missing-path hashes and the unchanged F32 core receipt must pass. No replacement core receipt, contract relaxation, alternative object or successful fixture test can discharge that criterion. The original contracts and source remain unchanged.

## Actual attempt and diagnosed failure

The published PRE is 7388ccbadaedd9d26de85fd49748f3522cae6f06. Reviewed executor SHA256 is c13c9907eebb154938395fa5cbad7b2e94ef53a93156f582e7e5621161693cc4; static plan SHA256 is 32abb4e0563dc3603293f3650b9a56360ca1385f92abc18e205fd50ce142e245.

Real process 22727 started at 2026-11-11T04:38:35.626632+00:00 and exited 1 after 101.29 seconds. Its read-only input checks reached the fresh Governance reference check. The new guard incorrectly applied local Git configuration isolation to network access, disabling the existing configured authentication. The network reference command exited 128 before the executor created its status, baseline or native output tree.

Independent diagnosis found normal existing Git configuration returned the exact published Governance head with exit 0. The isolated configuration failed with a missing-username error and terminal prompts disabled. DNS resolution worked. This is a guard defect; no credential content was read or changed.

Independent readback confirms the process ended, the historical output root remains absent, all 49 missing native paths remain absent, and all 1327 current frozen states remain unchanged. Protected boot files and source are unchanged. Observer-labelled status and exit receipts were created after this readback; they are explicitly distinguished from native executor-produced receipts.

## Repair and next attempt

A corrected network check must retain normal authorized authentication configuration after removing inherited Git environment overrides. Local object reads retain their existing isolation. The correction also needs a focused regression and bounded redacted failure diagnostics.

A01's original controller and evidence are retained. A02 requires a new published PRE binding the corrected controller and plan hashes, independent review, fresh source/Governance checks and the same complete original native acceptance. No blind native retry occurred.

[Machine-readable evidence](evidence/HP_F47_NATIVE_PREREQUISITE_RECOVERY_20261111.json) includes the complete static plan, original executor, launch and independent readback receipts. Source evidence and scoped Governance are published and read back; only HP and canonical Git publication are covered. Native Poll, link, kernel build, installation, boot and physical acceptance remain NOT_RUN. The parent project remains PARTIAL.
