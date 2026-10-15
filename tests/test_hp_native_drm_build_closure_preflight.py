#!/usr/bin/env python3
"""Source-only native DRM HP stage-header and partial-link safety gate."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_hp_build",
                    ROOT / "tools/build_hp_native_drm_adapter.py")
assert spec is not None and spec.loader is not None
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def rejected(call, message):
    try:
        call()
    except RuntimeError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError("expected failure: " + message)


with tempfile.TemporaryDirectory(prefix="i915-abi-preflight-") as td:
    root = Path(td)
    stage = root / "new-stage"
    include = stage / "netbsd-full-linux/sys/external/bsd/drm2/include"
    include.mkdir(parents=True)
    canonical = ROOT / "compat/native-drm/drm_cdevsw.c"
    args = ["-Werror", "-I" + str(include)]
    rejected(lambda: build.verify_bridge_headers(args, canonical, stage),
             "missing native DRM bridge headers")
    for header in build.REQUIRED_BRIDGE_HEADERS:
        p = include / header
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("/* synthetic NetBSD native bridge header */\n")
    found = build.verify_bridge_headers(args, canonical, stage)
    assert set(found) == set(build.REQUIRED_BRIDGE_HEADERS)
    p = include / build.REQUIRED_BRIDGE_HEADERS[0]
    p.unlink()
    rejected(lambda: build.verify_bridge_headers(args, canonical, stage),
             "missing native DRM bridge headers")

    external = root / "external-header"
    external.write_text("not owned by HP stage")
    p.symlink_to(external)
    rejected(lambda: build.verify_bridge_headers(args, canonical, stage),
             "escapes source stage")

    link = build.native_drm_partial_link_command(
        stage / "full-linux-tools/bin/x86_64--netbsd-ld", root / "results")
    assert link[1:3] == ["-r", "-o"]
    assert link[3] == str(root / "results/modern_drm_three.o")
    assert link[4:] == [
        str(root / "results" / (u + ".o")) for u in build.NATIVE_UNITS]
    assert len(link) == 7

print("I915_HP_NATIVE_FILE_BRIDGE_HEADER_AND_LD_R_CONTRACT_PASS")
print("LIMITATION: synthetic headers and command, NOT HP compiler or linker")
