# HP i915 checkpoint, 2026-10-05

STATE: IN_PROGRESS. Build and installation host: HP only.
The full 323 active Linux units plus DRM/TTM/OS-adapter contract is unchanged.

Starting canonical driver revision: 64a7d044552f59ef0abc260e0828a37902e2672f.
References: Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab and NetBSD
03d918f6d0e81fa05b8f1160eca0628ad39988a6. Current source/tests were materialized
on HP separately from `/usr/src` and existing import worktrees.

All 17 project Python/C regression scripts passed on HP NetBSD 11 against
both the frozen reference and the genuine six-edit overlay. The runner
verified all 24 eDP patch orders on frozen source, six orders on the overlay,
and exact combined complete-file equivalence. The six concatenated combined
source files have SHA256
`13cb25441ce3768181bc33983c38752bbbc5100510dbd3b32f5a7299b56b7c53`.
See [the source/C regression evidence](evidence/HP_PINNED_REGRESSIONS_20261005.json).
These are mocked C/source tests, separate from hardware acceptance.

Same-step repairs preserve the acceptance gates:

- Registration rollback anchors search after their predecessor, avoiding the
  earlier success-path RPM assertion call. Reversed cleanup is rejected.
- Candidates 0008 and 0011 now byte-match their canonical generators. Original
  and regenerated patches produce identical complete target source bytes;
  only diff context/blank-line classification differed.
- The MSA fixture includes the patch's trailing separator blank line.
- The AUX IRQ fallback generator's invalid parenthesis is repaired.
- ASan/UBSan executables use NetBSD's ELF PaX flag on resolved disposable
  temporary binaries only. No global security policy is changed.
- Negative controls require SIGABRT and the specific violated expression,
  including NetBSD's lowercase assertion format.
- The DPCD C11 test includes stdbool.h explicitly for `true`.
- Audio tests accept an explicit, clean pinned NetBSD reference instead of
  a Legion-only path. Audio and terminal PPGTT ownership tests are included
  in the shared runner; all 17 scripts now execute there.

The initial frozen-and-overlay job stopped at the missing stdbool.h include.
The connection outage prevented its result being read. After the user's
continuation, the live HP SSH route recovered, that durable failure was read,
the evidenced test defect was repaired, and the complete final suite passed.
Read `i915-all17.status` (EXIT 0) and `i915-all17.log` in the task workspace.
No infrastructure failure was counted as a pass.

All eleven affected native NetBSD C objects subsequently compiled with the
actual frozen kernel headers and HP's GCC 12.5.0 tools, with `_KERNEL`,
`-nostdinc` and warnings as errors. This bounded stack consists of the genuine
six-edit overlay plus 0005/0006/0007..0013/0016/0017; 0014 and 0015 are already
present in the overlay. The isolated build stage holds twelve changed files,
including the shared register header. Object hashes, patch hashes, source
hashes and actual make commands are recorded in
[the native object evidence](evidence/HP_BACKPORT_OBJECTS_20261005.json).
The existing tools, original references, user overlay and `/usr/src` remain
separate from the writable stage.

Actual commands on HP:

```sh
python3 -B tools/run_pinned_i915_source_checks.py \
  --netbsd-tree /root/netbsd-src-ref \
  --linux-tree /root/linux-rtl8723be-ref-fresh \
  --overlay-tree /root/hp-driver-port-20261005/netbsd-six-overlay-verified
python3 -B tools/build_hp_backport_objects.py \
  --netbsd-tree /root/hp-driver-port-20261005/netbsd-native \
  --objdir /root/hp-driver-port-20261005/native-obj \
  --overlay-tree /root/hp-driver-port-20261005/netbsd-six-overlay-verified
```

The genuine six-file Legion overlay's binary Git diff SHA256 is
`2623b640b713b01b1aa83383f9bf4a318abdd8d76963a3478f39dcc0cadca5bb`.
Its HP copy is byte-identical. Original Legion files and HP's older 497-file
whole-driver import were preserved. A local clone of the partial frozen
reference failed because upload-pack could not obtain a promisor object with
lazy fetching disabled; the separately materialized detached sparse worktree
succeeded. Do not repeat that failed partial-clone command.

Source publication uses verified HP commits and BMAX's ordinary Git route;
HP's HTTPS push has no credentials. Commit messages skip hosted CI to honor
HP-only builds. This checkpoint does not reactivate the quarantined workflow.

No kernel link, installation, reboot or physical KMS acceptance is claimed.
The F77 boot selection, `/boot.cfg`, `/netbsd` and F77 kernel hashes were
rechecked unchanged after the object builds. i915 remains disabled there.

NEXT: continue semantic/dependency classification and implementation of all
323 active Linux units and required DRM/TTM/NetBSD adapters; link the complete
experimental graph, test ownership/PM/reset, and establish HP display/runtime
acceptance before installation eligibility. Eleven backport objects do not
close the complete Linux-driver contract.
