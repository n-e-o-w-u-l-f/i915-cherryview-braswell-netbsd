#!/usr/bin/env python3
"""Pin NetBSD AUX polling fallback to IRQ availability, candidate 0013.

Frozen NetBSD intel_dp_aux_wait_done() uses the interrupt wait when !cold,
even if intel_irq_install failed or runtime/system PM disabled IRQs.
NetBSD already records physical IRQ installation in drm.irq_enabled and
runtime IRQ availability in runtime_pm.irqs_enabled. Pinned Linux selects
the interrupt wait only with an enabled parent IRQ and otherwise polls.
Preserve all existing NetBSD wait, timeout and MMIO read mechanics.
This is a bounded lifecycle correction, not a proven HP black-screen fix.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
OLD = "\tif (!cold) {\n"
NEW = (
    "\tif (!cold && i915->drm.irq_enabled &&\n"
    "\t    i915->runtime_pm.irqs_enabled) {\n"
)


def pinned_source(tree: Path) -> str:
    sha = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if sha != NETBSD_PIN:
        raise RuntimeError("wrong pinned NetBSD commit: " + sha)
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True,
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("frozen NetBSD intel_dp.c is dirty")
    return committed


def transform(original: str) -> str:
    start_anchor = "static u32\nintel_dp_aux_wait_done("
    end_anchor = "static u32 g4x_get_aux_clock_divider("
    if original.count(start_anchor) != 1 or original.count(end_anchor) != 1:
        raise RuntimeError("AUX wait source bounds changed")
    start = original.index(start_anchor)
    end = original.index(end_anchor, start)
    function = original[start:end]
    if function.count(OLD) != 1 or function.count(NEW) != 0:
        raise RuntimeError("unexpected AUX wait/IRQ branch")
    if ("#ifdef __NetBSD__\n" + OLD) not in function:
        raise RuntimeError("candidate must affect only NetBSD IRQ branch")
    if "done = wait_for_atomic(C, timeout_ms) == 0;" not in function:
        raise RuntimeError("existing polling fallback missing")
    return original[:start] + function.replace(OLD, NEW, 1) + original[end:]


def generate(tree: Path, output: Path) -> None:
    original = pinned_source(tree)
    revised = transform(original)
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        revised.splitlines(keepends=True),
        fromfile="a/" + REL,
        tofile="b/" + REL,
    ))
    if diff.count("+\tif (!cold && i915->drm.irq_enabled &&") != 1:
        raise RuntimeError("missing IRQ-availability gate")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(diff)
    print("I915_EDP_AUX_IRQ_POLL_FALLBACK_PATCH_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
