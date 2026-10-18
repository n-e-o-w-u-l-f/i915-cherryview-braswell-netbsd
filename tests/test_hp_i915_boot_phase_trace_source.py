#!/usr/bin/env python3
"""Pinned real-C NetBSD-only GPU initialization markers: 9 phases, 18 prints.

Requires an exact upstream NetBSD i915_drv.c supplied with --netbsd-i915;
running this test on Legion tests only a source/patch, NOT NetBSD kernel code.
"""
from __future__ import annotations
import argparse
import difflib
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hp_i915_phase", ROOT / "tools/generate_hp_i915_boot_phase_trace_patch.py")
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def refused(fn, name):
    try:
        fn()
    except RuntimeError:
        return
    raise AssertionError("test should have refused " + name)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-i915", type=Path, required=True)
    a = p.parse_args()
    orig = a.netbsd_i915.read_text()
    assert orig.startswith("/*\t$NetBSD: i915_drv.c")
    assert len(m.PHASES) == 9
    assert {entry[1] for entry in m.PHASES} == {
        "G01","G02","G03","G04","G05","G06","G07","G08","G09"}
    new = m.transform(orig)
    begin = re.findall(r'\tprintf\("\[I915 (G0[1-9])\] [^"]+ BEGIN\\n"\);', new)
    end = re.findall(r'\tprintf\("\[I915 (G0[1-9])\] [^"]+ END(?: ret=%d)?\\n"(?:, ret)?\);', new)
    assert len(begin) == len(end) == 9
    assert set(begin) == set(end) == {x[1] for x in m.PHASES}
    # Remove exact NetBSD-guarded messages and require the rest to be
    # byte-for-byte equal. This catches accidental return/error changes.
    guard = (
        r'#ifdef __NetBSD__\n'
        r'\tprintf\("\[I915 G0[1-9]\] [^"\n]+\\n"(?:, ret)?\);\n'
        r'#endif\n'
    )
    stripped, count = re.subn(guard, "", new)
    assert count == 18, "marker guards missing or wrong"
    assert stripped == orig, "actual source call/order/unwind changed"
    for scope, _, _, call, _ in m.PHASES:
        assert orig.count(call) >= 1
        assert new.count(call) == orig.count(call)
    assert new.index("[I915 G01]") < new.index("[I915 G02]") < new.index("[I915 G03]") < new.index("[I915 G04]")
    assert new.index("[I915 G05]") < new.index("[I915 G06]") < new.index("[I915 G07]") < new.index("[I915 G08]") < new.index("[I915 G09]")
    refused(lambda: m.transform(new), "repeat instrumentation")
    refused(lambda: m.transform(orig.replace("\tret = i915_driver_hw_probe(dev_priv);\n", "", 1)),
            "missing hardware probe")
    refused(lambda: m.transform(orig.replace("\tret = intel_irq_install(i915);\n",
                "\tret = intel_irq_install(i915);\n\tret = intel_irq_install(i915);\n",1)),
            "duplicate IRQ anchor")

    patch = "".join(difflib.unified_diff(
        orig.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="a/" + m.REL, tofile="b/" + m.REL))
    assert patch.count("+\tprintf(") == 18
    with tempfile.TemporaryDirectory(prefix="netbsd-i915-trace-fixture-") as td:
        root = Path(td)
        target = root / m.REL
        target.parent.mkdir(parents=True)
        target.write_text(orig)
        out = root / "phase.patch"
        out.write_text(patch)
        check = subprocess.run(["git","apply","--check",str(out)],cwd=root,
                               capture_output=True,text=True,timeout=12)
        assert check.returncode == 0, check.stderr
        apply = subprocess.run(["git","apply",str(out)],cwd=root,
                               capture_output=True,text=True,timeout=12)
        assert apply.returncode == 0, apply.stderr
        assert target.read_text() == new
        refused(lambda: m.transform(target.read_text()), "applied patch reentry")
    print("NETBSD_I915_PINNED_G01_G09_18_MARKERS_PATCH_PASS")
    print("RESULT: original C minus 18 guarded traces is byte-identical; "
          "negative tests and real git apply PASS")
    print("LIMIT: source-only; no native HP build or physical display diagnosis")

if __name__ == "__main__":
    main()
