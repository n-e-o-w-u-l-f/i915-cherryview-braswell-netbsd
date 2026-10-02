#!/usr/bin/env python3
"""Pinned VLV/CHV PIPE_MSA_MISC source and genuine overlay regression.

The existing 0003 patch is already on the genuine Legion overlay. Check
the published patch against frozen NetBSD and the original pinned Linux
register definition/modeset ordering. Never double-apply on the overlay:
verify reverse applicability instead. No native NetBSD/HP runtime claim.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
ROOT = "sys/external/bsd/drm2/dist/drm/i915/"
N_DISPLAY = ROOT + "display/intel_display.c"
N_REG = ROOT + "i915_reg.h"
L_DISPLAY = "drivers/gpu/drm/i915/display/intel_display.c"
L_REG = "drivers/gpu/drm/i915/display/intel_display_regs.h"

INSERT_WRITE = "\tI915_WRITE(VLV_PIPE_MSA_MISC(pipe), 0);\n\n"
OLD_WRITE_CONTEXT = (
    "\tintel_set_pipe_src_size(new_crtc_state);\n\n"
    "\tif (IS_CHERRYVIEW(dev_priv) && pipe == PIPE_B) {"
)
NEW_WRITE_CONTEXT = OLD_WRITE_CONTEXT.replace(
    "\tif (IS_CHERRYVIEW", INSERT_WRITE + "\tif (IS_CHERRYVIEW"
)
REG_ADDITION = (
    "\n#define _VLV_PIPE_MSA_MISC_A\t\t0x70048\n"
    "#define VLV_PIPE_MSA_MISC(pipe)\t\t_MMIO_PIPE2(pipe, _VLV_PIPE_MSA_MISC_A)\n"
    "#define   VLV_MSA_MISC1_HW_ENABLE\t\tREG_BIT(31)\n"
    "#define   VLV_MSA_MISC1_SW_S3D_MASK\t\tREG_GENMASK(2, 0)\n"
)


def pinned(tree: Path, commit: str, name: str) -> str:
    sha = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if sha != commit:
        raise RuntimeError(f"wrong pinned checkout {tree}: {sha}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + name], text=True
    )
    if (tree / name).read_text() != committed:
        raise RuntimeError("dirty or missing pinned file: " + name)
    return committed


def crtc_enable(src: str) -> str:
    start = "static void valleyview_crtc_enable("
    if src.count(start) != 1:
        raise AssertionError("Valleyview/Cherryview enable function changed")
    i = src.index(start)
    return src[i:src.index("\n}\n", i) + 3]


def source_checks(linux_display: str, linux_reg: str,
                  netbsd_display: str, netbsd_reg: str) -> None:
    l = crtc_enable(linux_display)
    n = crtc_enable(netbsd_display)
    l_write = "intel_de_write(display, VLV_PIPE_MSA_MISC(display, pipe), 0);"
    n_write = "I915_WRITE(VLV_PIPE_MSA_MISC(pipe), 0);"
    if l.count(l_write) != 1 or n.count(n_write) != 1:
        raise AssertionError("MSA MISC reset missing or duplicated")
    for src, write, before, after in (
        (l, l_write, "intel_set_pipe_src_size(new_crtc_state);",
         "intel_encoders_pre_pll_enable(state, crtc);"),
        (n, n_write, "intel_set_pipe_src_size(new_crtc_state);",
         "intel_encoders_pre_pll_enable(state, crtc);"),
    ):
        if not (src.index(before) < src.index(write) < src.index(after)):
            raise AssertionError("MSA MISC reset moved outside pipe setup")
    required = (
        "#define _VLV_PIPE_MSA_MISC_A", "0x70048",
        "VLV_MSA_MISC1_HW_ENABLE", "REG_BIT(31)",
        "VLV_MSA_MISC1_SW_S3D_MASK", "REG_GENMASK(2, 0)"
    )
    if not all(x in linux_reg and x in netbsd_reg for x in required):
        raise AssertionError("pinned Linux/NetBSD MSA register values diverged")
    if ("#define VLV_PIPE_MSA_MISC(__display, pipe)" not in linux_reg or
            "#define VLV_PIPE_MSA_MISC(pipe)" not in netbsd_reg):
        raise AssertionError("OS-specific register address API changed")
    if "#define VLV_PIPE_MSA_MISC(pipe)\t\t_MMIO_PIPE2(pipe, _VLV_PIPE_MSA_MISC_A)" not in netbsd_reg:
        raise AssertionError("NetBSD register addressing differs from patch")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", required=True, type=Path)
    ap.add_argument("--linux-tree", required=True, type=Path)
    ap.add_argument("--patch", required=True, type=Path)
    ap.add_argument("--overlay-tree", default=None, type=Path)
    args = ap.parse_args()
    frozen_display = pinned(args.netbsd_tree, NETBSD_PIN, N_DISPLAY)
    frozen_reg = pinned(args.netbsd_tree, NETBSD_PIN, N_REG)
    linux_display = pinned(args.linux_tree, LINUX_PIN, L_DISPLAY)
    linux_reg = pinned(args.linux_tree, LINUX_PIN, L_REG)
    if frozen_display.count(OLD_WRITE_CONTEXT) != 1:
        raise AssertionError("frozen NetBSD modeset insertion anchor drift")
    if frozen_reg.count("#define   PIPE_PIXEL_SHIFT        0\n") != 1:
        raise AssertionError("frozen register insertion anchor drift")
    expected_display = frozen_display.replace(
        OLD_WRITE_CONTEXT, NEW_WRITE_CONTEXT, 1
    )
    expected_reg = frozen_reg.replace(
        "#define   PIPE_PIXEL_SHIFT        0\n",
        "#define   PIPE_PIXEL_SHIFT        0\n" + REG_ADDITION, 1
    )
    source_checks(linux_display, linux_reg, expected_display, expected_reg)
    patch = args.patch.resolve(strict=True)
    subprocess.run(
        ["git", "-C", str(args.netbsd_tree), "apply", "--check", str(patch)],
        check=True
    )
    with tempfile.TemporaryDirectory() as root:
        tmp = Path(root)
        for relative, src in ((N_DISPLAY, frozen_display),
                              (N_REG, frozen_reg)):
            target = tmp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(src)
        subprocess.run(["git", "-C", str(tmp), "apply", str(patch)], check=True)
        if ((tmp / N_DISPLAY).read_text() != expected_display or
                (tmp / N_REG).read_text() != expected_reg):
            raise AssertionError("published MSA patch modifies unrelated source")
    print("I915_0003_PINNED_MSA_PATCH_AND_LINUX_REFERENCE_OK", flush=True)

    if args.overlay_tree is not None:
        overlay = args.overlay_tree.resolve(strict=True)
        if overlay == args.netbsd_tree.resolve():
            raise RuntimeError("genuine overlay must differ from frozen tree")
        source_checks(linux_display, linux_reg,
                      (overlay / N_DISPLAY).read_text(),
                      (overlay / N_REG).read_text())
        subprocess.run(["git", "-C", str(overlay), "apply",
                        "--reverse", "--check", str(patch)], check=True)
        print("I915_0003_EXISTING_OVERLAY_REVERSE_CHECK_OK", flush=True)
    else:
        print("I915_0003_FROZEN_ONLY_OVERLAY_UNVERIFIED", flush=True)


if __name__ == "__main__":
    main()
