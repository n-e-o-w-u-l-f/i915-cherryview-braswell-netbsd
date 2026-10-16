#!/usr/bin/env python3
"""Pure Python adversarial fixtures for all-unit direct header inventory."""
import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "closure", ROOT / "tools/audit_i915_direct_include_closure.py")
assert spec is not None and spec.loader is not None
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def rejected(fn, needle):
    try:
        fn()
    except (ValueError, FileNotFoundError) as err:
        assert needle in str(err), str(err)
    else:
        raise AssertionError("missing rejection: " + needle)


with tempfile.TemporaryDirectory(prefix="i915-include-closure-") as tmp:
    base = Path(tmp)
    linux = base / "linux"
    netbsd = base / "netbsd"
    (linux / "display").mkdir(parents=True)
    (netbsd / "include/linux").mkdir(parents=True)
    (netbsd / "dist/include/drm").mkdir(parents=True)
    (netbsd / "include/linux/existing.h").write_text("/* header */\n")
    (netbsd / "dist/include/drm/print.h").write_text("/* header */\n")
    (linux / "display/intel_dp.c").write_text(
        "#include <linux/existing.h>\n"
        "#include <linux/missing.h>\n"
        '#include "intel_dp.h"\n'
        "#if 0\n#include <drm/print.h>\n#endif\n")
    (linux / "i915_mm.c").write_text("#include <linux/missing.h>\n")
    manifest = base / "active.list"
    manifest.write_text(
        "file external/bsd/drm2/dist/drm/i915/display/intel_dp.c i915drmkms\n"
        "file external/bsd/drm2/dist/drm/i915/i915_mm.c i915drmkms\n")
    coverage = base / "coverage.tsv"
    coverage.write_text(
        "linux_source\tstructural_class\tnetbsd_evidence\tsemantic_state\n"
        "display/intel_dp.c\tUNRESOLVED_NO_BASENAME\t\tUNREVIEWED\n"
        "i915_mm.c\tEXACT_ACTIVE_DIST\tdist:i915_mm.c\tUNREVIEWED\n")
    report = tool.audit(manifest, linux, netbsd, coverage, 2)
    s = report["summary"]
    assert s["active_units"] == 2
    assert s["unique_shared_direct_includes"] == 3
    assert s["netbsd_exact_header_matches"] == 2
    assert s["netbsd_exact_header_unmatched"] == 1
    assert s["units_with_unmatched_direct_include"] == 2
    assert report["unmatched_headers"][0]["header"] == "linux/missing.h"
    assert report["unmatched_headers"][0]["user_count"] == 2
    assert all(row["semantic_parity"] == "UNVERIFIED"
               for row in report["rows"])
    rejected(lambda: tool.audit(manifest, linux, netbsd, coverage, 323),
             "323-unit closure mismatch")
    coverage.write_text(coverage.read_text().replace("i915_mm.c\t", "other.c\t"))
    rejected(lambda: tool.audit(manifest, linux, netbsd, coverage, 2),
             "323-unit closure mismatch")
    coverage.write_text(coverage.read_text().replace("other.c\t", "i915_mm.c\t"))
    manifest.write_text(manifest.read_text() +
        "file external/bsd/drm2/dist/drm/i915/i915_mm.c i915drmkms\n")
    rejected(lambda: tool.active_paths(manifest), "duplicate active")
    manifest.write_text(
        "file external/bsd/drm2/dist/drm/i915/../../oops.c i915drmkms\n")
    rejected(lambda: tool.active_paths(manifest), "unsafe C source path")
print("I915_323_UNIT_DIRECT_INCLUDE_AUDIT_TEST_PASS")
print("LIMITATION: source-only synthetic fixture, not NetBSD ABI or KMS")
