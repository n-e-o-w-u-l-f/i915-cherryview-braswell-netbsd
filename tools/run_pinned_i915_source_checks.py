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
import hashlib
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile

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
    p12 = (ROOT / "candidates/0012-i915-edp-dpcd-rates-failed-aux-read-netbsd11.patch").resolve(strict=True)
    p13 = (ROOT / "candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch").resolve(strict=True)

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
    invoke("test_chv_dpio_routing_source_contract.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux))
    invoke("test_edp_aux_irq_fallback.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p13), *overlay_args)
    invoke("test_edp_fixed_mode.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p11), *overlay_args)
    invoke("test_edp_dpcd_rates.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p12), *overlay_args)

    # Apply all three independent eDP patches in every possible order to
    # intel_dp.c file in both orders. The original frozen checkout and the
    # unpublished six-edit overlay must remain untouched.
    dp_rel = Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c")
    dp_original = (netbsd / dp_rel).read_bytes()
    combined = []
    with tempfile.TemporaryDirectory() as name:
        scratch = Path(name)
        target = scratch / dp_rel
        target.parent.mkdir(parents=True)
        for pair in itertools.permutations((p11, p12, p13)):
            target.write_bytes(dp_original)
            for patch in pair:
                subprocess.run(["git", "-C", str(scratch),
                                "apply", str(patch)], check=True)
            combined.append(target.read_bytes())
    if len(set(combined)) != 1 or combined[0] == dp_original:
        raise AssertionError("0011/0012/0013 combined patch orders diverged")
    print("I915_0011_0012_0013_COMBINED_REAL_GIT_APPLY_6_ORDERS_OK",
          flush=True)

    # Standalone patch checks are intentionally on the unchanged frozen
    # worktree, never on a scratch tree already containing prior patches.
    for tree in ([netbsd, overlay] if overlay else [netbsd]):
        assert tree is not None
        for patch in (p7, p8, p9, p10, p11, p12, p13):
            subprocess.run(["git", "-C", str(tree), "apply",
                            "--check", str(patch)], check=True)

    # Integration gate, not merely six independent git apply --checks:
    # apply the complete seven-patch stack to the three actual source files
    # in a disposable tree. Include the *real* overlay files only if the
    # caller supplied a distinct checkout. Never mutate the reference,
    # published patch artifacts, or the user's unpublished overlay.
    sources = (
        Path("sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"),
    )
    patch_stack = (p7, p8, p9, p10, p11, p12, p13)
    for tree in ([netbsd, overlay] if overlay else [netbsd]):
        assert tree is not None
        originals = {relative: (tree / relative).read_bytes()
                     for relative in sources}
        with tempfile.TemporaryDirectory() as name:
            scratch = Path(name)
            for relative, content in originals.items():
                dest = scratch / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            for patch in patch_stack:
                subprocess.run(
                    ["git", "-C", str(scratch), "apply", str(patch)],
                    check=True,
                )
            changed = {relative: (scratch / relative).read_bytes()
                       for relative in sources}
            if any(changed[relative] == original
                   for relative, original in originals.items()):
                raise AssertionError(
                    "complete patch stack left a target source unchanged"
                )
            driver = changed[sources[0]].decode("utf-8")
            opregion = changed[sources[1]].decode("utf-8")
            dp = changed[sources[2]].decode("utf-8")
            required = (
                (driver, "out_cleanup_registration:"),
                (driver, "err_early:"),
                (opregion, "opregion->rvda ? opregion->asle->rvds : 0;"),
                (opregion, "if (opregion->rvda)\n"
                 "\t\t\t\tAcpiOsUnmapMemory(opregion->rvda,"),
                (dp, 'DRM_INFO("failed to find fixed mode for eDP,'),
                (dp, "(ssize_t)sizeof(sink_rates)) {"),
                (dp, "if (!cold && i915->drm.irq_enabled &&"),
            )
            for content, anchor in required:
                if anchor not in content:
                    raise AssertionError(
                        "complete stack lost required change: " + anchor
                    )
            fingerprint = hashlib.sha256(
                b"".join(changed[relative] for relative in sources)
            ).hexdigest()
        scope = "OVERLAY" if overlay is not None and tree == overlay else "FROZEN"
        print("I915_0007_TO_0013_COMBINED_REAL_GIT_APPLY_" +
              scope + "_OK sha256=" + fingerprint, flush=True)

    print("I915_PINNED_SOURCE_CHECKS_PASS_" +
          ("FROZEN_AND_OVERLAY" if overlay else "FROZEN_ONLY"),
          flush=True)
    print("LIMITATION: host C/source and patch applicability only; "
          "NetBSD object/kernel build and HP display runtime NOT TESTED",
          flush=True)


if __name__ == "__main__":
    main()
