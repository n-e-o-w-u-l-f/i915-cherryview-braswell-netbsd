# F28: modern source integration and native build admission — 2026-11-09

Scoped PASS: source/history preservation and native build admission. Parent
HP-I915 remains PARTIAL. No modern C/provider/kernel or physical test was run.

## Source integration

New isolated HP worktree:
/home/andreas/projects/hp-i915-f26-20261106/f28-integration;
branch work/hp-f28-modern-provider-integration-20261109.

Merge 51e6c20c172f940f686ba128cfac634238a2d4b3 retains F26
6db373c5462d29541a57a36c54409d04399cb9fa and recovered debug
fd61cceac3774f68795f6bd91b241889c3b69f13. All 146 recovered manifest files
match their original blobs at this merge. F26 changed 85 paths and debug 161
disjoint paths; independent parent/index review found no mismatch or conflict.
37 merged Python sources pass AST syntax checks.

The subsequent admission repair intentionally changes three build tools and
one existing test, and adds a helper and its tests. Recovered CRLF and embedded
patch bytes are preserved. Whole inherited merge diff-check returns 2 for
whitespace; final checks separately cover the six repaired files.

## Implemented repair

Three build tools now require --toolchain. Historical fixed UID1004 and
/usr/tools assumptions are removed. HP/NetBSD11/amd64/nonroot, exact source pin,
clean tree, strict kernel flags and source/header/patch/kernel hash guards remain.

Executable tools must resolve inside the explicit toolchain, and configured CC
must resolve to its compiler. Provider admission requires the core receipt's
original toolchain and tool hashes before output creation. Missing legacy
provenance, different paths/root and replaced tools are rejected. New outputs
are created exclusively with mode0700 and owner/input/path checks; safe sticky
temporary parents remain supported.

## Executed verification

On HP as andreas uid1000: 18/18 new preflight tests and 8/8 existing patchchain
admission tests PASS, exits0. All three help entrypoints, real host/toolchain
admission, GCC12.5 version query and native Make query without build exit0.
All six repaired Python sources pass syntax/whitespace checks.

The initial test import regression was reproduced and corrected with an explicit
tools import path. Independent review found missing predecessor-toolhash
validation; six additional provenance tests now cover its correction.
The /usr/src/obj Make backend alias is the same /usr/obj binary.

[Complete evidence](evidence/HP_F28_MODERN_SOURCE_INTEGRATION_20261109.json)
contains source hashes, final commands/exits/log hashes, coverage and fleet data.
Durable logs: /home/andreas/projects/hp-i915-f26-20261106/f28-native-preflight*.

## Fleet

| Host | Observed project state | Result |
|---|---|---|
| HP | Original clean5c7ac64; isolated F28 | Original build/artifacts preserved |
| Legion | Clean mirrors27fd4d7 and9b5e118 | Read-only role; not advanced |
| Spinnennet | Clean master eae449e; no remote | Ancestry unresolved; preserved |
| BMAX-B6 | Strict SSH works; exact project ACL denies access | Source UNVERIFIED |
| PHOBOS | DC offline; current-account route unverified | UNVERIFIED |
| Pi-hole | Identity only; no registered project path | No project scan |
| localhost | Android; no registered project path | No project scan |

Protected/root/megal HP locations remain unverified where ownership or
filesystem access prevented inspection. No complete fleet synchronization claim.

## Governance and safe state

Historical F27 POST has invalid status CLOSED and invariant drift. Its original
ledger remains unchanged; a new explicit re-entry PRE/POST records fresh F27
artifact/protected hashes and passes the real re-entry validator. No build replay.
The old owner record already exceeded16KiB: its exact19858bytes were archived
before compacting, SHA25618ee04e33fa22786ac3af4cc35e0bb23c603499c13a8554426b633b2c4617e0f.

Installed /netbsd remains
9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde;
/boot.cfg remains
f7e0ccc00308172d5787f47c2c66b33921c53341f896e2339079a66980b6a4df.
Durable F27 kernel remains
d845e4c33ef26222641c20084ba46d7a31d3049ce9e281a9db88b99fb62092d2.
No install/boot/EFI/radio/cleanup/hostedCI. Earlier denied operations not rerouted.

## Open coverage and next action

Recovered0038 late fileops dispatch must not be stacked with F11's alternative
patch against the same originals. Next is a superseding candidate correcting
native Linux DRM zero-size data to NULL before the native raw-userpointer branch,
retaining the early direction/highbit/single-copyout gates. Include canonical
descriptor larger than forged zero-size command. No actual corruption is asserted.

Compat32 has a separate netbsd32_ioctl preparation/dispatch/copyout and does not
automatically invoke fo_ioctl_user; it remains a separate open gate. Then compose
actual FILE/task/page/MM/UVM lifetimes and complete configured provider objects
and kernel link. prepare_hp_full_graph remains UNREVIEWED probe. Physical KMS,
PM/recovery and companion WPA2 stay open. The F26 artifact is not promoted by
this source merge.
