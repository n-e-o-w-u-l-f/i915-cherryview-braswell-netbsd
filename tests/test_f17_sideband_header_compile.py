#!/usr/bin/env python3
"""Compile the actual F17-patched NetBSD intel_sideband.h with host GCC/Clang.

Uses mock *system* dependencies only: the actual NetBSD sideband header is
copied byte-for-byte and the published three-file patch is applied by git.
This validates declarations/include ordering, not a native NetBSD ABI build.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = Path("sys/external/bsd/drm2/dist/drm/i915/intel_sideband.h")
BLOB = "ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea"
PATCH = ROOT / "patches/candidates/netbsd-11-chv-dpio-signal-phy-consumer-20261026.patch"
FLAGS = ("-std=gnu11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only")


def assert_equal(a: object, b: object, description: str) -> None:
    if a != b:
        raise AssertionError(f"{description}: {a!r} != {b!r}")


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def write(root: Path, path: str | Path, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def run() -> None:
    ap = argparse.ArgumentParser()
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--netbsd-tree", type=Path)
    modes.add_argument("--verified-blob-dir", type=Path)
    ap.add_argument("--compilers", nargs="+", default=["gcc", "clang"])
    args = ap.parse_args()
    tree = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree is not None:
        actual = subprocess.check_output(
            ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
        assert_equal(actual, PIN, "NetBSD checkout revision")

    original = (tree / REL).read_bytes()
    assert_equal(git_blob(original), BLOB, "original NetBSD Git blob")
    for cc in args.compilers:
        if not shutil.which(cc):
            raise RuntimeError(f"host C compiler not installed: {cc}")

    with tempfile.TemporaryDirectory(prefix="f17-header-c-") as d:
        scratch = Path(d)
        copied = scratch / REL
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(original)
        for options in (("--check",), ()):
            subprocess.run(
                ["git", "-C", str(scratch), "apply", "--whitespace=error",
                 *options, "--include=" + str(REL), str(PATCH)],
                check=True, capture_output=True, text=True)
        patched = copied.read_bytes()
        if patched == original:
            raise AssertionError("F17 patch did not change actual header")
        body = patched.decode("utf-8")
        if body.count("u32 vlv_dpio_phy_read(") != 1:
            raise AssertionError("F17 PHY read header prototype missing")
        if body.count("void vlv_dpio_phy_write(") != 1:
            raise AssertionError("F17 PHY write header prototype missing")

        includes = scratch / "mock"
        write(includes, "linux/bitops.h", "#define BIT(n) (1UL << (n))\n")
        write(includes, "linux/types.h",
              "#include <stdint.h>\n"
              "typedef uint8_t u8;\n"
              "typedef uint16_t u16;\n"
              "typedef uint32_t u32;\n")
        write(includes, "sys/file.h", "/* NetBSD file header mock */\n")
        write(includes, "intel_sideband.h", body)

        for order in ("enum_before_header", "enum_after_header"):
            enum = "enum dpio_phy { DPIO_PHY0, DPIO_PHY1 };\n"
            before = enum if order == "enum_before_header" else ""
            after = enum if order == "enum_after_header" else ""
            source = (before + '#include "intel_sideband.h"\n' + after +
                      "enum pipe { PIPE_A, PIPE_B, PIPE_C };\n"
                      "void f17_proto_compile_only(struct drm_i915_private *d, "
                      "enum dpio_phy phy) {\n"
                      "    u32 val = vlv_dpio_phy_read(d, phy, 0x123);\n"
                      "    vlv_dpio_phy_write(d, phy, 0x123, val);\n"
                      "}\n")
            file = scratch / (order + ".c")
            file.write_text(source)
            for cc in args.compilers:
                subprocess.run([cc, *FLAGS, "-I", str(includes), str(file)],
                               check=True, capture_output=True, text=True)
                print(f"F17_REAL_PATCHED_SIDEBAND_HEADER_GNU11_PASS_{cc}_{order}")

    print("F17_HEADER_REAL_PATCH_2_ENUM_ORDERS_GCC_CLANG_PASS_HOST_ONLY")


if __name__ == "__main__":
    run()
