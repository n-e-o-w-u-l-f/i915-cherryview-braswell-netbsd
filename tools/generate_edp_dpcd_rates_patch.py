#!/usr/bin/env python3
"""Source-pinned eDP AUX rate-read failure handling, candidate 0012.

Frozen NetBSD intel_edp_init_dpcd() parses an uninitialized local rate array
after failed/short AUX reads. The pinned Linux reference sanitizes the array
and falls back to DP_MAX_LINK_RATE. The NetBSD drm_dp_dpcd_read() API returns
a byte count on success or a negative error code, so require a complete read.
No register or firmware behavioral guesses are introduced.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"

OLD = (
    "\t\tdrm_dp_dpcd_read(&intel_dp->aux, DP_SUPPORTED_LINK_RATES,\n"
    "\t\t\t\tsink_rates, sizeof(sink_rates));\n"
)
NEW = (
    "\t\tif (drm_dp_dpcd_read(&intel_dp->aux, DP_SUPPORTED_LINK_RATES,\n"
    "\t\t\t\t     sink_rates, sizeof(sink_rates)) !=\n"
    "\t\t    (ssize_t)sizeof(sink_rates)) {\n"
    "\t\t\tDRM_DEBUG_KMS(\"Unable to read eDP supported link rates, \"\n"
    "\t\t\t\t      \"using default rates\\n\");\n"
    "\t\t\tmemset(sink_rates, 0, sizeof(sink_rates));\n"
    "\t\t}\n"
)


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError(f"frozen NetBSD revision mismatch: {head}")
    source = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True
    )
    if (tree / REL).read_text() != source:
        raise RuntimeError("frozen NetBSD intel_dp.c is dirty")
    return source


def transform(source: str) -> str:
    start = source.index("static bool\nintel_edp_init_dpcd(")
    end = source.index("static bool\nintel_dp_get_dpcd(", start)
    function = source[start:end]
    if function.count(OLD) != 1 or function.count(NEW) != 0:
        raise RuntimeError("eDP supported-rates read anchor changed")
    if "else\n\t\tintel_dp_set_sink_rates(intel_dp);" not in function:
        raise RuntimeError("standard DPCD rate fallback changed")
    return source[:start] + function.replace(OLD, NEW, 1) + source[end:]


def generate(tree: Path, output: Path) -> None:
    original = pinned_source(tree)
    changed = transform(original)
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), changed.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if diff.count("+\t\t\tmemset(sink_rates, 0, sizeof(sink_rates));") != 1:
        raise RuntimeError("eDP rate-read failure guard lost")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(diff)
    print("I915_EDP_DPCD_RATES_PATCH_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
