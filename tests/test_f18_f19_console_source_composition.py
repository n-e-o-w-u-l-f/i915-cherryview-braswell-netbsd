#!/usr/bin/env python3
"""Full-source F18 trace + F19 console preflight two-order git-apply gate.

F19 is the opt-in *functional* preflight candidate. F18 adds seven guarded
diagnostic markers. Neither patch is an installed HP/NetBSD kernel.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
F18 = ROOT / "patches/candidates/netbsd11-f18-i915-console-handoff-trace-20261027.patch"
F19 = ROOT / "patches/candidates/netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch"
DRMFB = Path("sys/external/bsd/drm2/drm/drmfb.c")
BLOBS = {
    Path("sys/dev/wsfb/genfb.c"): "cb9094da52262743df52d20b2bf0b2c320886fa1",
    Path("sys/dev/wscons/wsdisplay.c"): "64f1d2ed2113b6f16c86565dd4780be954dd2a35",
    DRMFB: "f71bee4c525b4199dc4e3eb52ad3f321787e5905",
    Path("sys/external/bsd/drm2/i915drm/intelfb.c"): "482f05fb6879cae8bebaf9aa6e3bd054dc6118b4",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() +
                        b"\0" + content).hexdigest()


def git_apply(root: Path, patch: Path, allowed: set[Path]) -> None:
    numstat = subprocess.check_output(
        ["git", "apply", "--numstat", str(patch)], text=True)
    actual = {Path(row.split("\t", 2)[2]) for row in numstat.splitlines()}
    require(actual == allowed, f"unexpected patch scope for {patch.name}")
    for flags in (("--check",), ()):
        subprocess.run(["git", "-C", str(root), "apply", "--whitespace=error",
                        *flags, str(patch)], capture_output=True,
                       check=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--netbsd-tree", type=Path)
    modes.add_argument("--verified-blob-dir", type=Path)
    args = ap.parse_args()
    tree = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree is not None:
        head = subprocess.check_output(
            ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
        require(head == NETBSD, "not pinned NetBSD original checkout")
    with tempfile.TemporaryDirectory(prefix="f18-f19-compose-") as d:
        root = Path(d)
        paths = (root / "f18-first", root / "f19-first")
        for rel, sha in BLOBS.items():
            contents = (tree / rel).read_bytes()
            require(blob_sha(contents) == sha, f"unpinned source {rel}")
            for scratch in paths:
                dest = scratch / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(contents)
        expected_f18 = set(BLOBS)
        expected_f19 = {DRMFB}
        for dest, sequence in (
            (paths[0], ((F18, expected_f18), (F19, expected_f19))),
            (paths[1], ((F19, expected_f19), (F18, expected_f18))),
        ):
            for patch, scope in sequence:
                git_apply(dest, patch, scope)
        for path in BLOBS:
            require((paths[0] / path).read_bytes() == (paths[1] / path).read_bytes(),
                    f"F18-F19 source output depends on patch order: {path}")
        drm = (paths[0] / DRMFB).read_text()
        search = drm.index("child = config_search(da->da_dev")
        legacy = drm.index("vga_cndetach();")
        mark = drm.index("[I915-CN DRM1]")
        require(search < legacy < mark, "unsafe preflight/VGA/trace order")
        require("return ENXIO;" in drm[search:legacy],
                "no console-child error must precede VGA detach")
        require(drm.count("HP_I915_CONSOLE_TRACE") == 2,
                "must retain both guarded original F18 DRM trace blocks")
        for path in BLOBS:
            require(b"HP_I915_CONSOLE_TRACE" in (paths[0] / path).read_bytes(),
                    f"F18 diagnostics missing in combined output: {path}")
    print("F18_F19_FOUR_PINNED_SOURCES_REAL_TWO_ORDER_GIT_APPLY_IDENTICAL_PASS")


if __name__ == "__main__":
    main()
