# HP native DRM compiler replay — source-only checkpoint 2026-10-15

State: **BRANCH WORK / SOURCE CHECK ONLY**. Not a complete i915/DRM/TTM
port and not a successful HP native build. The source-of-truth branch is
`work/hp-native-drm-stage-replay-20261015` based on
`main@27fd4d7d483be456158884c08d04446dd5312326`.

## PRE — verified cause and scope

`tools/build_hp_native_drm_adapter.py` required the retired fixed tree
`/root/hp-driver-port-20261005/netbsd-full-linux` and object directory
`/root/hp-driver-port-20261005/full-linux-obj`. The retired tree was
removed from the active HP workflow, as documented in
`docs/PINNED_SOURCE_CHECK_SCOPE_20261011.md`. The script therefore could
not safely replay the previously successful three-object native build in a
newly prepared workspace, even with a legitimate replacement stage.

The historical source of the compiler flags is still the three recorded
131-argument commands in
`docs/evidence/HP_NATIVE_DRM_TASK_ENTRY_20261006.json`, not arbitrary flags
collected from another host. Linux pin:
`fd179f8a05be3ccae366b9b96e176b51fbe54aab`. NetBSD source pin:
`03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

## Change (no OS or hardware effect)

- Require `--stage-root` naming a **fresh HP** tree with
  `netbsd-full-linux`, `full-linux-obj` and `full-linux-tools` children.
- Relocate recognized historical path arguments, including compiler binary,
  `-I`, `--sysroot=`, and `-include` operands. Reject any other argument
  retaining the retired root; do not relax strict kernel warning flags.
- Replace only `-c` (with the exact expected source owner, or the repository
  canonical DRM adapter) and `-o` (with an isolated output). Preserve all
  unrelated compiler switches and their order.
- Check compiled-stage Linux task/module **source SHA-256** values from the
  recorded evidence; require the staged DRM adapter to match the exact
  repository copy, and validate configured `machine/cdefs.h` and executable
  native compiler before creating a report directory.
- Provide `--preflight-only`, which performs the same validation but executes
  **no compiler** and does not create a build report or output object.
- Add host-independent Python source/argv regression
  `tests/test_hp_native_drm_stage_replay.py`, covering three actual recorded
  commands and rejection of dropped `-Werror`, wrong compiler, duplicate
  `-o`, wrong source and unrecognized old-root embedding.

## POST — evidence and limits

- GitHub connector write/readback: source and test are committed and bytewise
  retrievable on the isolated branch.
- A separate **JavaScript source-level model check** processed all 393
  historical argument elements across the three recorded commands; 81
  historical path arguments were relocated; no stale absolute build root
  remained; `-Werror`, `-nostdinc`, `-D_KERNEL` remained present; unknown
  embedded old-root arguments were rejected.
- **NOT EXECUTED**: the newly published Python test; NetBSD-native compiler;
  final DRM/TTM/i915 closure; full kernel build/link; HP boot/display/KMS.
  The model check is not a substitute for those gates.

## Next execution on HP only (after independent authorized access)

From the repository checkout, on the HP NetBSD target:

```sh
python3 -B tests/test_hp_native_drm_stage_replay.py
python3 -B tools/build_hp_native_drm_adapter.py \
  --stage-root /path/to/verified/fresh/hp-stage \
  --output /path/to/checkout-parent/i915-native-drm-20261015 \
  --preflight-only
```

After an actual clean stage and source hashes have been verified, run the
same command without `--preflight-only` in a **new, nonexisting output path**
and preserve the JSON/log/object hashes. Three-object PASS is only a
partial ABI checkpoint. Continue compiling the actual owner/provider graph
for the 121 partial-link undefineds and the selected 323 i915 active source
units. A source owner text match must never be counted as a real linked
symbol; a relocatable `ld -r` result must never be counted as a full kernel.

**Safe-state invariant:** no driver/display register write, test-kernel
installation, boot menu change, reboot, network reset or firmware change
was performed. HP's live boot identity is still unverified in this chat.
F83/F84 blackscreen remains unsolved until G01–G09 hardware-independent
early-console trace and recovery prerequisites exist. Do not reuse the
rejected fbdev-async hypothesis as a fix.

NEXT: run portable Python source test where legitimately available; verify
fresh HP source/object/tool stage, and only then perform native HP build.
Do not promote this branch to `main` on the basis of this model check alone.
