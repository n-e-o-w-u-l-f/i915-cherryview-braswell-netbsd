#!/usr/bin/env python3
"""F25: full clean NetBSD amd64 kernel build, with F19/F20/F21/F22 and RTL PHY.

Strictly scratch-only. Reuses a previously completed native toolchain,
but NOT any kernel object. The historical RTL8723BE PHY source stage
is the read-only source base. F19–F22 modify four NetBSD source files.
Do NOT boot/install the compilation-only RTL test kernel.

This does NOT apply every separate experimental CHV patch candidate.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"

ORIGINAL = {
    "sys/external/bsd/drm2/drm/drmfb.c":
        "f71bee4c525b4199dc4e3eb52ad3f321787e5905",
    "sys/arch/x86/x86/consinit.c":
        "9ef384c2c07a2202040d0fe672fdfa58a5c07a78",
    "sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c":
        "9798385b02f247c08db9b16624d5ddc9d11a8ca5",
    "sys/external/bsd/drm2/i915drm/files.i915drmkms":
        "23d352b64eb1799caf3e9b2770f78795accc8439",
}
PATCHES = [
    "netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch",
    "netbsd11-f20-x86-genfb-early-fallback-20261027.patch",
    "netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch",
    "netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch",
]
CONFIG = "F25_CONSOLE_RTL_TEST"
CONFIG_PATH = f"sys/arch/amd64/conf/{CONFIG}"
COMPILE_MAKEFILE = "sys/arch/amd64/compile/Makefile"


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode()
                        + b"\0" + data).hexdigest()


def checked(cmd: list[str], *, cwd: Path | None = None,
            timeout: int = 75) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                            timeout=timeout)
    require(result.returncode == 0,
            f"exit={result.returncode} {cmd[:6]} {result.stderr[-1800:]}")
    return result.stdout


def overlay(source: Path, target: Path, changes: dict[str, Path]) -> None:
    """Create a sparse symlink forest with only explicit changed files copied."""
    require(not target.exists(), f"refusing existing overlay {target}")
    target.mkdir()
    branches = {name.partition("/")[0] for name in changes}
    present = set()
    for item in source.iterdir():
        present.add(item.name)
        dest = target / item.name
        if item.name not in branches:
            dest.symlink_to(item)
            continue
        if item.name in changes:
            require(item.is_file(), f"not a source file: {item}")
            dest.write_bytes(changes[item.name].read_bytes())
        else:
            require(item.is_dir(), f"not a source directory: {item}")
            subtree = {name[len(item.name) + 1:]: replacement
                       for name, replacement in changes.items()
                       if name.startswith(item.name + "/")}
            overlay(item, dest, subtree)
    for name in branches - present:
        require(name in changes, f"missing subdirectory: {name}")
        (target / name).write_bytes(changes[name].read_bytes())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-stage", required=True, type=Path,
                   help="read-only NetBSD 11 + RTL8723BE PHY source snapshot")
    p.add_argument("--toolchain", required=True, type=Path,
                   help="read-only historical native NetBSD cross tools")
    p.add_argument("--output", required=True, type=Path,
                   help="MUST be a completely new directory under /tmp")
    p.add_argument("--jobs", default=8, type=int)
    args = p.parse_args()

    stage = args.source_stage.resolve(strict=True)
    tools = args.toolchain.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists(), "output already exists")
    require(output.is_relative_to(Path("/tmp")), "scratch must be under /tmp")
    require(1 <= args.jobs <= 12, "unsafe job count")
    require(shutil.disk_usage(output.parent).free >= 4_000_000_000,
            "insufficient scratch disk space")
    for name in ("bin/nbconfig", "bin/nbmake-amd64",
                 "bin/x86_64--netbsd-gcc", "bin/nbctfconvert"):
        require((tools / name).is_file(), f"missing tool {name}")
    baseconf = (stage / "sys/arch/amd64/conf/RTWN8723BE_STAGE").read_text()
    require("Never boot/install" in baseconf,
            "unexpected baseline kernel config; refuse to build")
    rtl_phy = stage / "sys/dev/pci/rtwn8723be_netbsd.c"
    rtl_sha = "9542ec44fddf5861fd815cb065af3b3330306726"
    require(blob_id(rtl_phy.read_bytes()) == rtl_sha,
            "RTL8723BE PHY native source stage is not the verified df3bc40 pin")
    print("F25_RTL8723BE_NATIVE_PHY_BLOB_VERIFIED", flush=True)

    # Do the read-only SHA source checks before creating new files.
    original = {}
    for rel, expected in ORIGINAL.items():
        source = (stage / rel).read_bytes()
        require(blob_id(source) == expected, f"source drift in {rel}")
        original[rel] = source
    print("F25_SOURCE_4_ORIGINAL_PINNED_BLOBS_PASS", flush=True)

    output.mkdir()
    patch_root = output / "pinned"
    for rel, source in original.items():
        file = patch_root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(source)
    for name in PATCHES:
        patch = ROOT / "patches/candidates" / name
        for opts in (["--check"], []):
            checked(["git", "-C", str(patch_root), "apply",
                     "--whitespace=error", *opts, str(patch)])
        print("F25_PATCH_PASS", name, flush=True)

    config = output / "kernel.config"
    config.write_text(baseconf + "\noptions HP_I915_FWFB_FAILOVER\n")
    changes = {path: patch_root / path for path in ORIGINAL}
    changes[CONFIG_PATH] = config
    changes[COMPILE_MAKEFILE] = (stage / COMPILE_MAKEFILE)

    # build.sh with -O still creates configuration files in the source
    # sys/arch/amd64/compile directory. This leaf therefore MUST be real
    # and writable, never a symlink to the historical source stage.
    overlay(stage, output / "src", changes)
    for rel, source in changes.items():
        require((output / "src" / rel).read_bytes() == source.read_bytes(),
                f"overlay replacement failed: {rel}")

    print("F25_ISOLATED_NETBSD_SOURCE_OVERLAY_READY", flush=True)
    # build.sh always rewrites bin/nbmake-amd64. Never point -T to the
    # original root-owned toolchain: copy the tools first.
    shutil.copytree(tools, output / "tools", symlinks=True)
    require((output / "tools/bin/nbmake-amd64").is_file(),
            "private toolchain was not copied")
    print("F25_PRIVATE_CROSS_TOOLCHAIN_READY", flush=True)

    command = [
        "./build.sh", "-U", "-m", "amd64", "-j" + str(args.jobs),
        "-O", str(output / "obj"), "-T", str(output / "tools"),
        "kernel=" + CONFIG,
    ]
    started = time.monotonic()
    with (output / "kernel-build.log").open("w") as stream:
        result = subprocess.run(command, cwd=output / "src",
                                stdout=stream, stderr=subprocess.STDOUT,
                                timeout=3400)
    require(result.returncode == 0,
            f"clean kernel build failed rc={result.returncode}; "
            f"see {output / 'kernel-build.log'}")
    print("F25_CLEAN_KERNEL_BUILD_SH_EXIT_ZERO", flush=True)

    compile_root = (output / "obj/sys/arch/amd64/compile" / CONFIG)
    kernel = compile_root / "netbsd"
    require(kernel.is_file() and kernel.stat().st_size > 10_000_000,
            "kernel image not created by clean build")
    for obj in ("i915_pci_autoconf.o", "drmfb.o", "consinit.o",
                "ioconf.o"):
        require((compile_root / obj).is_file(),
                f"missing newly compiled kernel object: {obj}")
    generated = compile_root / "opt_hp_i915_fwfb_failover.h"
    require(generated.exists() and
            "#define\tHP_I915_FWFB_FAILOVER\t1" in generated.read_text(),
            "F22 compile-time option was not enabled by real NetBSD config")
    ioconf = (compile_root / "ioconf.c").read_text()
    require("wsemuldisplaydevcf_iattrdata, &intelfbbuscf_iattrdata"
            in ioconf, "new native i915 wsdisplay parent interface absent")
    elf = checked([str(output / "tools/bin/x86_64--netbsd-readelf"),
                   "-h", str(kernel)])
    require("ELF64" in elf and "X86-64" in elf or
            ("ELF64" in elf and "Advanced Micro Devices X86-64" in elf),
            "wrong kernel executable architecture")
    image_sha = hashlib.sha256(kernel.read_bytes()).hexdigest()
    print("F25_CLEAN_NETBSD_FULL_KERNEL_COMPILE_AND_LINK_PASS", flush=True)
    print("F25_ELAPSED_S", round(time.monotonic() - started), flush=True)
    print("F25_NETBSD_KERNEL_SHA256", image_sha, flush=True)
    print("F25_IMAGE_PATH", kernel, flush=True)
    print("F25_NOT_CHV_ALL_CANDIDATES_NOT_PHYSICAL_HP_BOOT", flush=True)


if __name__ == "__main__":
    main()
