#!/usr/bin/env python3
"""Source-only recursive NetBSD .a provider candidate discovery tests."""
from pathlib import Path
import importlib.util
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "owner_scan", ROOT / "tools/audit_hp_native_drm_symbol_owners.py")
assert spec is not None and spec.loader is not None
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

with tempfile.TemporaryDirectory(prefix="i915-provider-archives-") as td:
    base = Path(td)
    stage = base / "provider"
    (stage / "kernel").mkdir(parents=True)
    (stage / "drm" / "lib").mkdir(parents=True)
    first = stage / "kernel" / "netbsd.a"
    second = stage / "drm" / "lib" / "drm2.a"
    first.write_bytes(b"fixture only, no native archive")
    second.write_bytes(b"fixture only, no native archive")
    (stage / "drm" / "lib" / "excluded.o").write_bytes(b"object")
    expected = sorted([first, second])
    assert tool.provider_archives([stage]) == expected
    assert tool.provider_archives([stage, stage / "drm"]) == expected
    assert tool.provider_archives([stage, stage]) == expected
    assert tool.provider_archives([stage / "kernel"]) == [first]

    outside = base / "outside.a"
    outside.write_bytes(b"external archive")
    link = stage / "drm" / "lib" / "outside.a"
    link.symlink_to(outside)
    try:
        tool.provider_archives([stage])
    except RuntimeError as error:
        assert "escapes selected root" in str(error)
    else:
        raise AssertionError("out-of-stage library symlink was accepted")
    link.unlink()

    old = tool.MAX_PROVIDER_OBJECTS
    try:
        tool.MAX_PROVIDER_OBJECTS = 1
        try:
            tool.provider_archives([stage])
        except RuntimeError as error:
            assert "archive scan exceeds" in str(error)
        else:
            raise AssertionError("unbounded archive scan succeeded")
    finally:
        tool.MAX_PROVIDER_OBJECTS = old

print("I915_DRM_ARCHIVE_PROVIDER_DISCOVERY_REGRESSION_PASS")
print("LIMITATION: synthetic archives only; no native nm or link proof")
