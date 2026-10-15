#!/usr/bin/env python3
"""Host-independent source/argv regression: no NetBSD compiler is invoked.

Validate relocation of the exact historical HP compiler commands. A real
native ABI build and its source/header verification still run on HP only.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/build_hp_native_drm_adapter.py"
spec = importlib.util.spec_from_file_location("native_drm_replay", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

legacy = str(module.LEGACY_STAGE)
fresh = Path("/hypothetical/isolated/hp-stage")
output = Path("/hypothetical/owner/i915-native-drm-regression")
canonical = ROOT / "compat/native-drm/drm_cdevsw.c"

assert module.relocate_argument("-I" + legacy + "/netbsd-full-linux/sys", fresh) == (
    "-I" + str(fresh) + "/netbsd-full-linux/sys")
assert module.relocate_argument(
    "--sysroot=" + legacy + "/full-linux-obj/destdir.amd64", fresh
) == "--sysroot=" + str(fresh) + "/full-linux-obj/destdir.amd64"
assert module.relocate_argument(legacy + "/full-linux-tools/bin/x86_64--netbsd-gcc", fresh) == (
    str(fresh) + "/full-linux-tools/bin/x86_64--netbsd-gcc")
assert module.relocate_argument("-Werror", fresh) == "-Werror"
try:
    module.relocate_argument("-DUNMAPPED=" + legacy + "/unapproved", fresh)
except RuntimeError:
    pass
else:
    raise AssertionError("unknown historical stage embedding went undetected")

evidence = json.loads(
    (ROOT / "docs/evidence/HP_NATIVE_DRM_TASK_ENTRY_20261006.json").read_text()
)
checks = evidence["native_three_unit_gate"]["status"]["checks"]
assert {row["name"] for row in checks} == set(module.UNIT_RELS)
for row in checks:
    name = row["name"]
    old_cmd = row["command"]
    new_cmd, source = module.replay_command(
        row, name, fresh, output, canonical
    )
    assert len(old_cmd) == len(new_cmd)
    assert "-Werror" in new_cmd and "-nostdinc" in new_cmd
    assert new_cmd[0] == str(fresh / "full-linux-tools/bin/x86_64--netbsd-gcc")
    assert new_cmd[new_cmd.index("-o") + 1] == str(output / (name + ".o"))
    assert source == (canonical if name == "drm_cdevsw" else
                       fresh / "netbsd-full-linux" / module.UNIT_RELS[name])
    assert new_cmd[new_cmd.index("-c") + 1] == str(source)
    assert all(legacy not in arg for arg in new_cmd)
    assert any(arg.startswith("-I" + str(fresh)) for arg in new_cmd)
    assert any(arg.startswith("--sysroot=" + str(fresh)) for arg in new_cmd)

    for broken in (
        [arg for arg in old_cmd if arg != "-Werror"],
        old_cmd + ["-o", "/bad/repeated/output.o"],
        ["/untrusted/compiler"] + old_cmd[1:],
    ):
        try:
            module.replay_command({**row, "command": broken}, name,
                                  fresh, output, canonical)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unsafe historical command was accepted: " + name)

    modified = old_cmd.copy()
    modified[modified.index("-c") + 1] = legacy + "/wrong-owner.c"
    try:
        module.replay_command({**row, "command": modified}, name,
                              fresh, output, canonical)
    except RuntimeError:
        pass
    else:
        raise AssertionError("wrong historical source owner was accepted")

print("I915_HP_NATIVE_DRM_ARGV_RELOCATION_SOURCE_REGRESSION_PASS")
print("LIMITATION: no compiler, NetBSD kernel link, HP runtime or KMS executed")
