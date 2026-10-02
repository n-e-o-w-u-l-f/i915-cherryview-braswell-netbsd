#!/usr/bin/env python3
"""Run pinned, host-isolated i915 error-path regressions without touching HP.

Accept a clean frozen NetBSD git checkout and a clean pinned Linux checkout.
Optionally check a separate *real* six-edit NetBSD port overlay. Never pass
the frozen checkout again as the overlay: it would be misleading evidence.
Only source/patched-function host C and patch application are checked;
this is not a native NetBSD kernel build or hardware verification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"


def git_head(tree: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()


def invoke(script: str, *arguments: str) -> None:
    print("RUN", script, flush=True)
    subprocess.run([sys.executable, str(ROOT / "tests" / script),
                    *arguments], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", type=Path, required=True)
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--overlay-tree", type=Path, default=None,
                    help="optional actual unpublished six-edit port overlay")
    args = ap.parse_args()

    netbsd = args.netbsd_tree.resolve(strict=True)
    linux = args.linux_tree.resolve(strict=True)
    if netbsd == linux:
        raise RuntimeError("Linux and NetBSD reference paths must differ")
    if git_head(netbsd) != NETBSD_PIN or git_head(linux) != LINUX_PIN:
        raise RuntimeError("wrong frozen NetBSD/Linux reference revision")
    overlay = None
    if args.overlay_tree is not None:
        overlay = args.overlay_tree.resolve(strict=True)
        if overlay in (netbsd, linux):
            raise RuntimeError("real unpublished overlay must be distinct")
        if git_head(overlay) != NETBSD_PIN:
            raise RuntimeError("unpublished overlay has wrong NetBSD base")
    p7 = (ROOT / "patches/0007-i915-early-probe-resource-unwind-netbsd11.patch").resolve(strict=True)
    p8 = (ROOT / "candidates/0008-i915-drm-registration-unwind-netbsd11.patch").resolve(strict=True)
    p9 = (ROOT / "candidates/0009-netbsd-opregion-optional-asle-cleanup.patch").resolve(strict=True)
    p10 = (ROOT / "candidates/0010-netbsd-opregion-rvda-map-failure-unwind.patch").resolve(strict=True)
    p11 = (ROOT / "candidates/0011-i915-edp-reject-missing-fixed-mode-netbsd11.patch").resolve(strict=True)

    overlay_args = ["--overlay-tree", str(overlay)] if overlay else []
    invoke("test_early_probe_unwind.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p7),
           *overlay_args)
    invoke("test_opregion_optional_asle.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p9))
    invoke("test_opregion_rvda_map_failure.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p10),
           "--opregion-patch", str(p9), *overlay_args)
    invoke("test_register_failure.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p8),
           "--previous-patch", str(p7),
           "--opregion-patch", str(p9), *overlay_args)
    invoke("test_drm_registration_source_contract.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux))
    invoke("test_edp_fixed_mode.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p11), *overlay_args)

    # Standalone patch checks are intentionally on the unchanged frozen
    # worktree, never on a scratch tree already containing prior patches.
    for tree in ([netbsd, overlay] if overlay else [netbsd]):
        assert tree is not None
        for patch in (p7, p8, p9, p10, p11):
            subprocess.run(["git", "-C", str(tree), "apply",
                            "--check", str(patch)], check=True)

    print("I915_PINNED_SOURCE_CHECKS_PASS_" +
          ("FROZEN_AND_OVERLAY" if overlay else "FROZEN_ONLY"),
          flush=True)
    print("LIMITATION: host C/source and patch applicability only; "
          "NetBSD object/kernel build and HP display runtime NOT TESTED",
          flush=True)


if __name__ == "__main__":
    main()
