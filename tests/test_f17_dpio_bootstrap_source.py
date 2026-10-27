#!/usr/bin/env python3
"""Pinned native i915 early-PHY port-map precondition for the F16/F17 provider.

Checks the actual NetBSD i915 initialization owner, mapped IOSF constants,
and call ordering before power-domain/MMIO display setup. This is a
source-only precondition; it is not a driver compile or hardware proof.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
BASE = Path("sys/external/bsd/drm2/dist/drm/i915")
DRIVER = BASE / "i915_drv.c"
REGISTER = BASE / "i915_reg.h"
BLOBS = {
    DRIVER: "bf64ff40059fc38188f6f3d7b55bef9793abeb57",
    REGISTER: "a070913dc965ebfb467b99da599e75dd03df61de",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def object_id(source: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(source)).encode() +
                        b"\0" + source).hexdigest()


def inspect(driver: str, regs: str) -> None:
    """Raise on missing or misordered CHV mapping/initialization prerequisites."""
    map_start = driver.index("static void intel_init_dpio(")
    map_end = driver.index("static int i915_workqueues_init(", map_start)
    body = driver[map_start:map_end]
    check(body.count("if (IS_CHERRYVIEW(dev_priv))") == 1,
          "CHV DPIO mapping platform predicate drift")
    check(body.count("DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO_2;") == 1,
          "CHV PHY0 must target second IOSF DPIO port")
    check(body.count("DPIO_PHY_IOSF_PORT(DPIO_PHY1) = IOSF_PORT_DPIO;") == 1,
          "CHV PHY1 must target first IOSF DPIO port")
    check(body.count("DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO;") == 1,
          "VLV PHY0 must target first IOSF DPIO port")
    check("#define DPIO_PHY_IOSF_PORT(phy)" in regs and
          "dev_priv->dpio_phy_iosf_port[phy]" in regs,
          "DPIO IOSF port macro no longer maps to physical-PHY array")

    early_start = driver.index("static int i915_driver_early_probe(")
    early_end = driver.index("\nerr_gem:", early_start)
    early = driver[early_start:early_end]
    anchors = [
        "mutex_init(&dev_priv->sb_lock);",
        "intel_init_dpio(dev_priv);",
        "intel_power_domains_init(dev_priv);",
        "intel_irq_init(dev_priv);",
        "intel_init_display_hooks(dev_priv);",
    ]
    for anchor in anchors:
        check(early.count(anchor) == 1, f"early initialization anchor: {anchor}")
    check([early.index(anchor) for anchor in anchors] ==
          sorted(early.index(anchor) for anchor in anchors),
          "DPIO mapping must initialize after sideband lock and before display setup")
    check(driver.count("intel_init_dpio(dev_priv);") == 1,
          "early DPIO mapping call count drift")


def main() -> None:
    parser = argparse.ArgumentParser()
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--netbsd-tree", type=Path)
    sources.add_argument("--verified-blob-dir", type=Path)
    args = parser.parse_args()
    root = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree is not None:
        actual = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        check(actual == PIN, "wrong NetBSD source Git HEAD")

    actual = {}
    for relative, expected in BLOBS.items():
        data = (root / relative).read_bytes()
        check(object_id(data) == expected,
              f"pinned i915 boot original blob drift: {relative}")
        actual[relative] = data.decode("utf-8")
    inspect(actual[DRIVER], actual[REGISTER])
    print("F17_PINNED_I915_DPIO_INITIALIZATION_ORDER_AND_PHY_IOSF_MAPPING_PASS")


if __name__ == "__main__":
    main()
