#!/usr/bin/env python3
"""Fail-closed native git-apply source composition gate for F15 + F17.

F15 supersedes F14 (it includes both F14 display hunks, plus GT/RPS lock
correction). It is not valid to apply F14 and then F15 as separate layers.
No NetBSD object or target-hardware execution is claimed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
BASE = Path("sys/external/bsd/drm2/dist/drm/i915")
ORIGINAL_BLOBS = {
    BASE / "intel_sideband.c": "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed",
    BASE / "intel_sideband.h": "ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea",
    BASE / "display/intel_dpio_phy.c": "9029d10774992a62a3f2ac84bb8a37f724360442",
    BASE / "display/intel_display.c": "faff25ecd0a1d57d47f862891810daf5299571a3",
    BASE / "display/intel_display.h": "03e7f21e578248e80ae03510715dc97eb855ca6f",
    BASE / "gt/intel_rps.c": "d3faefcffe985725a0cee09a25f7d2270a35e5ea",
}
F14 = ROOT / "patches/candidates/netbsd-11-chv-vlv-gpll-clock-20261026.patch"
F15 = ROOT / "patches/candidates/netbsd-11-chv-gpll-rps-lock-order-20261026.patch"
F17 = ROOT / "patches/candidates/netbsd-11-chv-dpio-signal-phy-consumer-20261026.patch"
F15_PATHS = {BASE / "display/intel_display.c", BASE / "display/intel_display.h",
             BASE / "gt/intel_rps.c"}
F17_PATHS = set(ORIGINAL_BLOBS) - F15_PATHS
F14_PATHS = F15_PATHS - {BASE / "gt/intel_rps.c"}
DISPLAY = BASE / "display/intel_dpio_phy.c"
RPS = BASE / "gt/intel_rps.c"
BEGIN = "/* BEGIN F17 EXACT PATCHED NATIVE FUNCTION */\n"
END = "/* END F17 EXACT PATCHED NATIVE FUNCTION */"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def blob_sha(blob: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()


def apply(root: Path, patch: Path, permitted: set[Path]) -> None:
    require(patch.is_file(), f"missing patch {patch}")
    output = subprocess.check_output(["git", "apply", "--numstat", str(patch)],
                                     text=True)
    paths = {Path(line.split("\t", 2)[2]) for line in output.splitlines()}
    require(paths == permitted, f"unexpected patch paths for {patch.name}: {paths}")
    for options in (("--check",), ()):
        subprocess.run(["git", "-C", str(root), "apply", "--whitespace=error",
                        *options, str(patch)], check=True,
                       capture_output=True, text=True)


def signal_function(content: str) -> str:
    marker = "void chv_set_phy_signal_level("
    require(content.count(marker) == 1, "missing/ambiguous CHV signal function")
    begin = content.index(marker)
    end = content.find("\n}\n", begin)
    require(end > begin, "unterminated CHV signal function")
    return content[begin:end + 2]


def run() -> None:
    parser = argparse.ArgumentParser()
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--netbsd-tree", type=Path,
                        help="actual NetBSD checkout; require pinned Git HEAD")
    inputs.add_argument("--verified-blob-dir", type=Path,
                        help="exact original source blobs; no Git HEAD claim")
    args = parser.parse_args()
    original_root = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree is not None:
        head = subprocess.check_output(["git", "-C", str(original_root),
                                        "rev-parse", "HEAD"], text=True).strip()
        require(head == NETBSD_PIN, "wrong NetBSD checkout revision")

    originals = {}
    with tempfile.TemporaryDirectory(prefix="f15-f17-composition-") as scratch:
        root = Path(scratch)
        f14_root, forward, reverse = (root / name for name in ("f14", "f15-17", "f17-15"))
        for rel, expected in ORIGINAL_BLOBS.items():
            data = (original_root / rel).read_bytes()
            require(blob_sha(data) == expected, f"original Git blob drift: {rel}")
            originals[rel] = data
            for stage in (f14_root, forward, reverse):
                file = stage / rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)

        apply(f14_root, F14, F14_PATHS)
        for rootdir, order in ((forward, ((F15, F15_PATHS), (F17, F17_PATHS))),
                               (reverse, ((F17, F17_PATHS), (F15, F15_PATHS)))):
            for patch, paths in order:
                apply(rootdir, patch, paths)

        for rel in ORIGINAL_BLOBS:
            require((forward / rel).read_bytes() == (reverse / rel).read_bytes(),
                    f"F15/F17 source order depends on patch order: {rel}")
        for rel in F14_PATHS:
            require((f14_root / rel).read_bytes() == (forward / rel).read_bytes(),
                    f"F15 does not preserve F14 display helper: {rel}")
        for rel in F17_PATHS:
            require((f14_root / rel).read_bytes() == originals[rel],
                    f"F14 unexpectedly touches F17-owned path: {rel}")

        before = originals[DISPLAY].decode("utf-8")
        after = (forward / DISPLAY).read_text(encoding="utf-8")
        old_signal, new_signal = signal_function(before), signal_function(after)
        require(before == after.replace(new_signal, old_signal, 1),
                "F15/F17 changed display code outside the signal function")

        c = (ROOT / "tests/test_f17_chv_signal_phy_source.c").read_text()
        require(c.count(BEGIN) == c.count(END) == 1, "invalid C model delimiters")
        model = c.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        require(new_signal.strip() == model, "F17 model != F15/F17 native function")
        require(new_signal.count("vlv_dpio_phy_read(dev_priv, phy,") == 9,
                "PHY read count drift")
        require(new_signal.count("vlv_dpio_phy_write(dev_priv, phy,") == 9,
                "PHY write count drift")

        rps = (forward / RPS).read_text()
        require(rps.count("rps->gpll_ref_freq = vlv_get_gpll_clock(i915);") == 1,
                "F15 GPLL helper call missing")
        calls = [m.end() for m in re.finditer(r"vlv_init_gpll_ref_freq\(rps\);", rps)]
        require(len(calls) == 2, "F15 expected two RPS init call sites")
        for end in calls:
            require("vlv_iosf_sb_get(i915," in rps[end:end + 180],
                    "F15 GPLL helper still inside the IOSF lock")
        display_h = (forward / (BASE / "display/intel_display.h")).read_text()
        sideband_h = (forward / (BASE / "intel_sideband.h")).read_text()
        require("int vlv_get_gpll_clock(" in display_h, "missing F15 declaration")
        require("u32 vlv_dpio_phy_read(" in sideband_h, "missing F17 declaration")

    provenance = ("CHECKOUT_PIN" if args.netbsd_tree is not None
                  else "BLOB_SHA_ONLY_NO_GIT_HEAD_CLAIM")
    print(f"F15_F17_SIX_EXACT_NETBSD_FILES_F14_SUPERSESSION_2_ORDERS_PASS_{provenance}")


if __name__ == "__main__":
    run()
