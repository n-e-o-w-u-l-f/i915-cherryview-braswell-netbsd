#!/usr/bin/env python3
"""Verify published F16/F17 patches against complete pinned NetBSD originals.

Source-only gate: git-apply, exact original blob identity, caller-only edit,
F16 provider identity, and verbatim F17 C fixture parity. No kernel ABI claim.
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
SIDEBAND_C = BASE / "intel_sideband.c"
SIDEBAND_H = BASE / "intel_sideband.h"
DPIO_C = BASE / "display/intel_dpio_phy.c"
ORIGINAL_BLOBS = {
    SIDEBAND_C: "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed",
    SIDEBAND_H: "ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea",
    DPIO_C: "9029d10774992a62a3f2ac84bb8a37f724360442",
}
F16 = ROOT / "patches/candidates/netbsd-11-chv-dpio-explicit-phy-20261026.patch"
F17 = ROOT / "patches/candidates/netbsd-11-chv-dpio-signal-phy-consumer-20261026.patch"
FIXTURE = ROOT / "tests/test_f17_chv_signal_phy_source.c"
BEGIN = "/* BEGIN F17 EXACT PATCHED NATIVE FUNCTION */\n"
END = "/* END F17 EXACT PATCHED NATIVE FUNCTION */"
FUNCTION = "void chv_set_phy_signal_level("
EXPECTED_FNV64 = 0x25d4c36ad02b2783


def check(ok: bool, why: str) -> None:
    if not ok:
        raise AssertionError(why)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii")
                        + b"\0" + data).hexdigest()


def function(text: str) -> str:
    check(text.count(FUNCTION) == 1, "missing or ambiguous native signal function")
    start = text.index(FUNCTION)
    end = text.find("\n}\n", start)
    check(end >= 0, "missing native signal function terminator")
    return text[start:end + 2]


def fnv64(text: str) -> int:
    result = 0xcbf29ce484222325
    for byte in text.encode("utf-8"):
        result = ((result ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return result


def apply(root: Path, patch: Path, expected_paths: set[Path]) -> None:
    check(patch.is_file(), f"missing patch {patch}")
    records = subprocess.check_output(["git", "apply", "--numstat", str(patch)],
                                      text=True).splitlines()
    paths = {Path(record.split("\t", 2)[2]) for record in records}
    check(paths == expected_paths, f"unexpected patch file scope: {paths}")
    for flags in (("--check",), ()):
        subprocess.run(["git", "-C", str(root), "apply",
                        "--whitespace=error", *flags, str(patch)],
                       check=True, capture_output=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    args = parser.parse_args()
    tree = args.netbsd_tree.resolve(strict=True)
    revision = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
    check(revision == PIN, "NetBSD source checkout is not at pinned commit")

    with tempfile.TemporaryDirectory(prefix="i915-f17-full-source-") as tmp:
        scratch = Path(tmp)
        f16_dir, f17_dir = scratch / "f16", scratch / "f17"
        original = {}
        for relative, expected in ORIGINAL_BLOBS.items():
            blob = (tree / relative).read_bytes()
            check(git_blob(blob) == expected, f"pinned original blob drift: {relative}")
            original[relative] = blob
            for dstroot in (f16_dir, f17_dir):
                dest = dstroot / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(blob)

        apply(f16_dir, F16, {SIDEBAND_C, SIDEBAND_H})
        apply(f17_dir, F17, set(ORIGINAL_BLOBS))

        for relative in (SIDEBAND_C, SIDEBAND_H):
            check((f16_dir / relative).read_bytes() ==
                  (f17_dir / relative).read_bytes(),
                  f"F17 changed F16 provider: {relative}")

        original_display = original[DPIO_C].decode("utf-8")
        updated_display = (f17_dir / DPIO_C).read_text(encoding="utf-8")
        previous = function(original_display)
        updated = function(updated_display)
        check(updated != previous, "F17 signal function not changed")
        check(updated_display.replace(updated, previous, 1) == original_display,
              "F17 modified display code outside signal function")
        check((f16_dir / DPIO_C).read_bytes() == original[DPIO_C],
              "F16 changed the display caller")

        model = FIXTURE.read_text(encoding="utf-8")
        check(model.count(BEGIN) == model.count(END) == 1,
              "ambiguous F17 C fixture delimiters")
        exact = model.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        check(updated.strip() == exact, "F17 C fixture differs from patched native source")
        check(fnv64(exact) == EXPECTED_FNV64, "F17 function checksum drift")

        check(updated.count("vlv_dpio_phy_read(dev_priv, phy,") == 9,
              "F17 has wrong PHY-read call-site count")
        check(updated.count("vlv_dpio_phy_write(dev_priv, phy,") == 9,
              "F17 has wrong PHY-write call-site count")
        check("vlv_dpio_read(dev_priv, pipe," not in updated and
              "vlv_dpio_write(dev_priv, pipe," not in updated,
              "F17 still routes signal level by pipe")
        check("enum dpio_phy phy = vlv_dport_to_phy(dport);" in updated,
              "F17 does not select physical port PHY")
        check(updated.count("vlv_dpio_get(dev_priv);") == 1 and
              updated.count("vlv_dpio_put(dev_priv);") == 1,
              "DPIO lock boundary drift")

    print("F17_PINNED_ORIGINAL_3_FILES_4_HUNKS_GIT_APPLY_AND_EXACT_C_PARITY_PASS")


if __name__ == "__main__":
    main()
