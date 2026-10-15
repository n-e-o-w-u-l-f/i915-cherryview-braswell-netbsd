#!/usr/bin/env python3
"""Pure Python test of HP symbol-owner object discovery; no compiler or nm."""
from pathlib import Path
import importlib.util
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "owner_scan", ROOT / "tools/audit_hp_native_drm_symbol_owners.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory(prefix="i915-owner-scan-") as td:
    work = Path(td)
    root = work / "obj"
    (root / "drm" / "display").mkdir(parents=True)
    (root / "native").mkdir(parents=True)
    first = root / "drm/display/intel_dp.o"
    second = root / "native/linux_wait.o"
    first.write_bytes(b"mock one")
    second.write_bytes(b"mock two")
    partial = root / "modern_drm_three.o"
    partial.write_bytes(b"partial link")
    (root / "drm/display/ignore.a").write_bytes(b"archive")

    assert module.provider_objects([root], partial) == [first, second]
    assert module.provider_objects([root, root / "drm"], partial) == [
        first, second]
    assert partial not in module.provider_objects([root], partial)

    external = work / "unapproved.o"
    external.write_bytes(b"outside")
    (root / "drm/display/escape.o").symlink_to(external)
    try:
        module.provider_objects([root], partial)
    except RuntimeError as err:
        assert "escapes selected root" in str(err)
    else:
        raise AssertionError("escaping symlink was accepted")

print("I915_HP_DRM_SYMBOL_OWNER_RECURSIVE_SCAN_TEST_PASS")
print("LIMITATION: mocked objects only, no native nm/ABI/kernel link")
