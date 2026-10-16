#!/usr/bin/env python3
"""Mutation tests: each critical Intel display callback failure must be caught."""
import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit", ROOT / "tools/audit_i915_parent_provider_closure.py")
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

a = argparse.ArgumentParser()
a.add_argument("--linux-i915", required=True, type=Path)
a.add_argument("--filelist", required=True, type=Path)
a.add_argument("--interface", required=True, type=Path)
args = a.parse_args()
units = module.read_units(args.linux_i915, args.filelist)
header = args.interface.read_text()
report = module.audit(units, header)
assert (report["source_units"], report["provider_count"],
        report["declared_methods"], report["bound_methods"]) == (323,16,95,94)
assert report["optional_unbound"] == {"fb_pin": ["reuse_vma"]}
assert report["providers"]["panic"]["members"] == 3
assert report["providers"]["vlv_iosf"]["owner"] == "vlv_iosf_sb.c"
assert report["providers"]["vlv_iosf"]["bound"] == 4


def rejects(key, needle, before, after, expected_message):
    changed = dict(units)
    assert before in changed[key], (key, needle)
    changed[key] = changed[key].replace(before, after, 1)
    try:
        module.audit(changed, header)
    except ValueError as err:
        assert expected_message in str(err), (key, str(err))
    else:
        raise AssertionError("Silent acceptance of missing " + needle)


rejects("vlv_iosf_sb.c", "IOSF write",
        ".write =", ".write_broken =", "provider missing/unknown methods")
rejects("i915_driver.c", "IOSF provider",
        ".vlv_iosf = &i915_display_vlv_iosf_interface,",
        "", "16 provider and four direct assignments")
rejects("i915_driver.c", "IRQ probe",
        "ret = intel_irq_install(i915);",
        "ret = deliberately_missing_irq_install(i915);",
        "Linux initialization order")
rejects("display/intel_display_device.c", "early parent assignment",
        "display->parent = parent;", "/* parent deliberately omitted */",
        "parent pointer not assigned")
print("I915_323_UNIT_PARENT_16_PROVIDER_95_METHOD_4_NEGATIVE_TESTS_PASS")
print("LIMITATION: source-only checks, no C preprocessing, linker, NetBSD or KMS")
