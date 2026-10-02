#!/usr/bin/env python3
"""Generate pinned NetBSD eDP fixed-mode/EDID failure unwind candidate 0011.

Pinned Linux intel_edp_init_connector() disables eDP when neither EDID nor VBT
provides a fixed mode. Frozen NetBSD lacks that check and proceeds to the
Cherryview reboot notifier and backlight setup without a fixed panel mode.
NetBSD's failed-connector path skips intel_connector_destroy(), so free a
cached, non-error EDID before returning failure. This is bounded source
parity, not a demonstrated HP black-screen fix.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError(f"wrong frozen NetBSD version: {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("dirty frozen intel_dp.c")
    return committed


def unique_replace(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{what}: expected unique source anchor")
    return text.replace(old, new, 1)


def transform(source: str) -> str:
    begin = "static bool intel_edp_init_connector("
    end = "static void intel_dp_modeset_retry_work_fn("
    if source.count(begin) != 1 or source.count(end) != 1:
        raise RuntimeError("eDP function boundaries changed")
    i = source.index(begin)
    j = source.index(end, i)
    before = source[i:j]
    after = unique_replace(
        before,
        "\tmutex_unlock(&dev->mode_config.mutex);\n\n"
        "\tif (IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) {\n",
        "\tmutex_unlock(&dev->mode_config.mutex);\n\n"
        "\tif (!fixed_mode) {\n"
        "\t\tDRM_INFO(\"failed to find fixed mode for eDP, disabling eDP\\n\");\n"
        "\t\tgoto out_vdd_off;\n"
        "\t}\n\n"
        "\tif (IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) {\n",
        "reject eDP with no EDID/VBT mode before notifier/backlight",
    )
    after = unique_replace(
        after,
        "\twith_pps_lock(intel_dp, wakeref)\n"
        "\t\tedp_panel_vdd_off_sync(intel_dp);\n\n"
        "\treturn false;\n",
        "\twith_pps_lock(intel_dp, wakeref)\n"
        "\t\tedp_panel_vdd_off_sync(intel_dp);\n\n"
        "\tif (!IS_ERR_OR_NULL(intel_connector->edid))\n"
        "\t\tkfree(intel_connector->edid);\n"
        "\tintel_connector->edid = NULL;\n\n"
        "\treturn false;\n",
        "release cached EDID on aborted connector initialization",
    )
    return source[:i] + after + source[j:]


def generate(tree: Path, output: Path) -> None:
    original = pinned_source(tree)
    revised = transform(original)
    patch = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        revised.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if not patch or patch.count("+\tif (!fixed_mode) {") != 1:
        raise RuntimeError("eDP fixed-mode guard missing or ambiguous")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patch)
    print("I915_EDP_FIXED_MODE_PATCH_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
