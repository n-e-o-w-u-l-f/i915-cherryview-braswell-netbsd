#!/usr/bin/env python3
"""Check F17 composition with the two native CHV IOSF transport candidates.

The checked-status patch must precede the modern guard. F17 may be applied
either before or after that ordered pair. Verify exact pinned original blobs,
real git apply, byte parity of the outputs, and provider/caller preservation.
This checks source composition, not NetBSD kernel ABI or runtime lock safety.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
BASE = Path("sys/external/bsd/drm2/dist/drm/i915")
SIDE_C = BASE / "intel_sideband.c"
SIDE_H = BASE / "intel_sideband.h"
DPIO = BASE / "display/intel_dpio_phy.c"
ORIGINAL_BLOBS = {
    SIDE_C: "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed",
    SIDE_H: "ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea",
    DPIO: "9029d10774992a62a3f2ac84bb8a37f724360442",
}
CHECKED = (ROOT / "compat/native-runtime/vlv-iosf/patches/"
           "netbsd-intel-sideband-checked-status.patch")
MODERN = (ROOT / "compat/native-runtime/vlv-iosf/patches/"
          "netbsd-intel-sideband-modern-guard.patch")
F17 = (ROOT / "patches/candidates/"
       "netbsd-11-chv-dpio-signal-phy-consumer-20261026.patch")
EXACT_MARKER = "/* BEGIN F17 EXACT PATCHED NATIVE FUNCTION */\n"
EXACT_END = "/* END F17 EXACT PATCHED NATIVE FUNCTION */"


def require(ok: bool, why: str) -> None:
    if not ok:
        raise AssertionError(why)


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def apply(root: Path, patch: Path, paths: set[Path]) -> None:
    assert patch.is_file()
    summary = subprocess.check_output(["git", "apply", "--numstat",
                                       str(patch)], text=True)
    actual = {Path(s.split("\t", 2)[2]) for s in summary.splitlines()}
    require(actual == paths, f"wrong patch path scope: {patch.name}: {actual}")
    for options in (("--check",), ()):
        subprocess.run(["git", "-C", str(root), "apply", "--whitespace=error",
                        *options, str(patch)], check=True,
                       capture_output=True, text=True)


def function(source: str) -> str:
    needle = "void chv_set_phy_signal_level("
    require(source.count(needle) == 1, "missing/ambiguous native CHV function")
    start = source.index(needle)
    end = source.find("\n}\n", start)
    require(end >= 0, "unterminated signal function")
    return source[start:end + 2].strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    args = parser.parse_args()
    tree = args.netbsd_tree.resolve(strict=True)
    current = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
    require(current == PIN, "wrong original NetBSD Git HEAD")

    originals = {}
    with tempfile.TemporaryDirectory(prefix="f17-iosf-composition-") as temporary:
        root = Path(temporary)
        first, second = root / "iosf-then-f17", root / "f17-then-iosf"
        for path, expected in ORIGINAL_BLOBS.items():
            source = (tree / path).read_bytes()
            require(blob_id(source) == expected, f"pinned original drift: {path}")
            originals[path] = source
            for folder in (first, second):
                dest = folder / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(source)
        side_paths = {SIDE_C, SIDE_H}
        for folder, sequence in (
            (first, (CHECKED, MODERN, F17)),
            (second, (F17, CHECKED, MODERN)),
        ):
            for patch in sequence:
                apply(folder, patch, set(ORIGINAL_BLOBS) if patch == F17 else side_paths)

        for path in ORIGINAL_BLOBS:
            require((first / path).read_bytes() == (second / path).read_bytes(),
                    f"F17/IOSF order-dependent output: {path}")

        source = (first / SIDE_C).read_text()
        header = (first / SIDE_H).read_text()
        for symbol in ("nb_i915_vlv_iosf_rw_checked",
                       "nb_i915_iosf_acquire",
                       "nb_i915_iosf_release",
                       "nb_i915_iosf_read_checked",
                       "nb_i915_iosf_write_checked",
                       "vlv_dpio_phy_read",
                       "vlv_dpio_phy_write"):
            require(symbol in source and symbol in header,
                    f"missing provider/ABI symbol in IOSF composition: {symbol}")
        require("NB_I915_IOSF_DPIO2 = 4" in header and
                "NB_I915_IOSF_PUNIT = 8" in header,
                "legacy-modern IOSF unit numbering drift")
        require("case NB_I915_IOSF_DPIO2: *port = IOSF_PORT_DPIO_2;" in source,
                "modern IOSF DPIO2 routing drift")

        native = (first / DPIO).read_text()
        fixture = (ROOT / "tests/test_f17_chv_signal_phy_source.c").read_text()
        require(fixture.count(EXACT_MARKER) == fixture.count(EXACT_END) == 1,
                "ambiguous exact source fixture")
        exact = fixture.split(EXACT_MARKER, 1)[1].split(EXACT_END, 1)[0].strip()
        require(function(native) == exact, "composed F17 signal C fixture drift")
        old = originals[DPIO].decode("utf-8")
        require(native.replace(function(native), function(old), 1) == old,
                "IOSF composition changed unrelated display function")

    print("F17_IOSF_CHECKED_MODERN_GUARD_TWO_PATCH_ORDERS_EXACT_PINNED_PASS")


if __name__ == "__main__":
    main()
