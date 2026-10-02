#!/usr/bin/env python3
"""Generate a scoped NetBSD i915 early-probe error-unwind correction.

The pinned Linux probe initializes sideband/runtime state before workqueues.
NetBSD's older import additionally owns explicit early uncore, QoS and locks.
On workqueue allocation failure, the NetBSD function previously returned
directly, skipping the already-existing early resource cleanup block.

This is a NetBSD integration/cleanup delta, not whole-driver Linux parity.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"

OLD = (
    "\tret = i915_workqueues_init(dev_priv);\n"
    "\tif (ret < 0)\n"
    "\t\treturn ret;\n"
)
NEW = (
    "\tret = i915_workqueues_init(dev_priv);\n"
    "\tif (ret < 0)\n"
    "\t\tgoto err_early;\n"
)
OLD_CLEANUP = (
    "err_workqueues:\n"
    "\ti915_workqueues_cleanup(dev_priv);\n"
    "\tmutex_destroy(&dev_priv->hdcp_comp_mutex);\n"
)
NEW_CLEANUP = (
    "err_workqueues:\n"
    "\ti915_workqueues_cleanup(dev_priv);\n"
    "err_early:\n"
    "\tmutex_destroy(&dev_priv->hdcp_comp_mutex);\n"
)


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError("wrong NetBSD reference commit: " + head)
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("dirty pinned i915_drv.c: refuse regeneration")
    return committed


def transform(source: str) -> str:
    start_marker = "static int i915_driver_early_probe("
    end_marker = "/**\n * i915_driver_late_release"
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise RuntimeError("early-probe function boundaries changed")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    original = source[start:end]
    if original.count(OLD) != 1 or original.count(OLD_CLEANUP) != 1:
        raise RuntimeError("expected exactly one unchanged failure/cleanup anchor")
    if original.count("err_gem:\n") != 1 or original.count("err_workqueues:\n") != 1:
        raise RuntimeError("expected original early-probe unwind labels")
    revised = original.replace(OLD, NEW, 1).replace(OLD_CLEANUP, NEW_CLEANUP, 1)
    return source[:start] + revised + source[end:]


def generate(tree: Path, output: Path) -> None:
    original = pinned_source(tree)
    revised = transform(original)
    patch = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), revised.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if not patch or "err_early:" not in patch:
        raise RuntimeError("missing early-unwind patch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patch)
    print("EARLY_PROBE_UNWIND_PATCH_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
