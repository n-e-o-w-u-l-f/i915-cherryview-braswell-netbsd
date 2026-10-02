#!/usr/bin/env python3
"""Generate pinned NetBSD i915 RVDA failed-map NULL-unmap fix (candidate 0010).

NetBSD AcpiOsMapMemory may return NULL; intel_bios_is_valid_vbt() then
rejects the VBT, but the old NetBSD error branch passed NULL to
AcpiOsUnmapMemory() -> x86 bus_space unmap, which requires a valid mapping.
Candidate 0009 separately handles the optional-ASLE unregister path.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c"
OLD = (
    "#ifdef __NetBSD__\n"
    "\t\t\tAcpiOsUnmapMemory(opregion->rvda,\n"
    "\t\t\t    opregion->asle->rvds);\n"
    "#else\n"
)
NEW = (
    "#ifdef __NetBSD__\n"
    "\t\t\tif (opregion->rvda)\n"
    "\t\t\t\tAcpiOsUnmapMemory(opregion->rvda,\n"
    "\t\t\t\t    opregion->asle->rvds);\n"
    "#else\n"
)


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError(f"wrong NetBSD reference: {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("dirty pinned OpRegion file")
    return committed


def transform(source: str) -> str:
    start = source.index("int intel_opregion_setup(struct drm_i915_private *dev_priv)")
    end = source.index("static int intel_use_opregion_panel_type_callback", start)
    body = source[start:end]
    if body.count(OLD) != 1:
        raise RuntimeError("missing or ambiguous RVDA map-failure error branch")
    if "vbt = opregion->rvda;\n" not in body:
        raise RuntimeError("RVDA validation behavior changed")
    return source[:start] + body.replace(OLD, NEW, 1) + source[end:]


def generate(tree: Path, out: Path) -> None:
    source = pinned_source(tree)
    changed = transform(source)
    patch = "".join(difflib.unified_diff(
        source.splitlines(keepends=True),
        changed.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if patch.count("if (opregion->rvda)") != 1:
        raise RuntimeError("RVDA mapping guard absent or nonunique")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(patch)
    print("I915_RVDA_MAP_FAILURE_PATCH_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
