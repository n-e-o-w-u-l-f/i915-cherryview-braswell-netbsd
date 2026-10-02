#!/usr/bin/env python3
"""Pin candidate 0014 to the already staged Legion Cherryview AUX fix.

The frozen NetBSD G4x AUX send control selects precharge=5 on CHV Gen8.
The pinned Linux formula uses (16+16-10-16)/2 = 3 extra 2us units.
Candidate 0014 records the *existing*, not newly inferred, local port
edit. For the frozen tree it must apply; on an optional separate real
six-edit overlay it must ALREADY be present and reverse-apply cleanly.

No code here changes the original frozen tree or the unpublished overlay.
Host/source contract only, not hardware timing or native NetBSD execution.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_DP = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
NETBSD_REG = "sys/external/bsd/drm2/dist/drm/i915/i915_reg.h"
LINUX_AUX = "drivers/gpu/drm/i915/display/intel_dp_aux.c"
OLD = (
    "\tu32 precharge, timeout;\n\n"
    "\tif (IS_GEN(dev_priv, 6))\n"
    "\t\tprecharge = 3;\n"
    "\telse\n"
    "\t\tprecharge = 5;\n"
)
NEW = "\tu32 timeout;\n"
OLD_BITS = "\t       (precharge << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT) |"
NEW_BITS = "\t       (3 << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT) |"


def checked_ref(tree: Path, sha: str, relative: str) -> str:
    actual = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if actual != sha:
        raise RuntimeError("source is not the pinned Git commit: " + relative)
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative], text=True,
    )
    if (tree / relative).read_text() != committed:
        raise RuntimeError("frozen reference file is dirty: " + relative)
    return committed


def aux_function(source: str) -> str:
    first = "static u32 g4x_get_aux_send_ctl("
    stop = "static u32 skl_get_aux_send_ctl("
    if source.count(first) != 1 or source.count(stop) != 1:
        raise AssertionError("G4x AUX function boundaries changed")
    i = source.index(first)
    return source[i:source.index(stop, i)]


def expected_overlay(original: str) -> str:
    f = aux_function(original)
    if f.count(OLD) != 1 or f.count(OLD_BITS) != 1:
        raise AssertionError("pinned NetBSD Gen8 precharge branch changed")
    transformed = f.replace(OLD, NEW, 1).replace(OLD_BITS, NEW_BITS, 1)
    return original.replace(f, transformed, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", required=True, type=Path)
    ap.add_argument("--linux-tree", required=True, type=Path)
    ap.add_argument("--patch", required=True, type=Path)
    ap.add_argument("--overlay-tree", type=Path, default=None)
    args = ap.parse_args()
    frozen = checked_ref(args.netbsd_tree, NETBSD_PIN, NETBSD_DP)
    reg = checked_ref(args.netbsd_tree, NETBSD_PIN, NETBSD_REG)
    linux = checked_ref(args.linux_tree, LINUX_PIN, LINUX_AUX)
    if re.search(
        r"(?m)^#define\s+DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT\s+16\s*$",
        reg,
    ) is None or re.search(
        r"(?m)^#define\s+DP_AUX_CH_CTL_PRECHARGE_2US_MASK\s+\(0xf << 16\)\s*$",
        reg,
    ) is None:
        raise AssertionError("pinned NetBSD precharge bitfield changed")
    if "static int intel_dp_aux_sync_len(void)" not in linux:
        raise AssertionError("pinned Linux sync-length source missing")
    sync = linux[linux.index("static int intel_dp_aux_sync_len(void)"):
                 linux.index("int intel_dp_aux_fw_sync_len(", 
                             linux.index("static int intel_dp_aux_sync_len(void)"))]
    if ("int precharge = 16;" not in sync or
            "int preamble = 16;" not in sync or
            "return precharge + preamble;" not in sync):
        raise AssertionError("pinned Linux base AUX sync length changed")
    precharge = linux[linux.index("static int g4x_dp_aux_precharge_len(void)"):
                      linux.index("static u32 g4x_get_aux_send_ctl(")]
    if ("int precharge_min = 10;" not in precharge or
            "int preamble = 16;" not in precharge or
            "return (intel_dp_aux_sync_len() -" not in precharge or
            "precharge_min - preamble) / 2;" not in precharge):
        raise AssertionError("pinned Linux G4x precharge conversion changed")
    if (16 + 16 - 10 - 16) // 2 != 3:
        raise AssertionError("pinned Linux AUX precharge value changed")
    send = aux_function(linux)
    if "DP_AUX_CH_CTL_PRECHARGE_2US(g4x_dp_aux_precharge_len())" not in send:
        raise AssertionError("pinned Linux AUX control no longer uses formula")

    revised = expected_overlay(frozen)
    if revised == frozen:
        raise AssertionError("precharge transform did not alter frozen NetBSD")
    patch = args.patch.resolve(strict=True)
    if ("- \t" in patch.read_text()):
        raise AssertionError("suspicious candidate patch syntax")
    subprocess.run(
        ["git", "-C", str(args.netbsd_tree), "apply", "--check", str(patch)],
        check=True,
    )
    # Verify actual applied bytes without writing to pinned source.
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        temp = Path(root)
        dest = temp / NETBSD_DP
        dest.parent.mkdir(parents=True)
        dest.write_text(frozen)
        subprocess.run(
            ["git", "-C", str(temp), "apply", str(patch)], check=True,
        )
        if dest.read_text() != revised:
            raise AssertionError("published 0014 changes more than expected")
    print("I915_0014_FROZEN_PATCH_AND_PINNED_LINUX_PARITY_OK", flush=True)

    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("real overlay must be distinct from frozen tree")
        overlay = args.overlay_tree / NETBSD_DP
        # The overlay may have *other* preserved local edits, so compare
        # only the bounded function, never the whole-file content.
        if aux_function(overlay.read_text()) != aux_function(revised):
            raise AssertionError("0014 is not the expected existing AUX overlay")
        subprocess.run(
            ["git", "-C", str(args.overlay_tree), "apply",
             "--reverse", "--check", str(patch)],
            check=True,
        )
        print("I915_0014_EXISTING_OVERLAY_REVERSE_APPLY_OK", flush=True)
    else:
        print("I915_0014_FROZEN_ONLY_OVERLAY_UNVERIFIED", flush=True)


if __name__ == "__main__":
    main()
