#!/usr/bin/env python3
"""Rebuild NetBSD F21/F22 native amd64 objects and re-link a WIP kernel.

Read-only inputs:
- pinned NetBSD/src snapshot, whose two original i915 blobs are verified;
- staged native NetBSD tree with historically buildable RTWN test config;
- existing native NetBSD toolchain;
- previous NetBSD compile log used to reproduce exact compiler arguments;
- previously linked RTL STAGE kernel object directory.

All modified sources, generated config, compiled objects, and linked kernel
remain in a new, user-specified scratch output path. NEVER INSTALL OR BOOT
THE ARTIFACT. This is NOT a fresh build of the entire kernel object tree.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
I915 = Path("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c")
FILES = Path("sys/external/bsd/drm2/i915drm/files.i915drmkms")
SHAS = {
    I915: "9798385b02f247c08db9b16624d5ddc9d11a8ca5",
    FILES: "23d352b64eb1799caf3e9b2770f78795accc8439",
}
PATCHES = (
    ROOT / "patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch",
    ROOT / "patches/candidates/netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch",
)
OPTION = "HP_I915_FWFB_FAILOVER"
NETBSD_TARGET = "x86_64--netbsd"
OLD_ATTR = ("static const struct cfiattrdata * const "
            "i915drmkms_attrs[] = { &intelfbbuscf_iattrdata, "
            "&acpivgacf_iattrdata, NULL };")
NEW_ATTR = ("static const struct cfiattrdata * const "
            "i915drmkms_attrs[] = { &wsemuldisplaydevcf_iattrdata, "
            "&intelfbbuscf_iattrdata, &acpivgacf_iattrdata, NULL };")


def require(cond: bool, reason: str) -> None:
    if not cond:
        raise RuntimeError(reason)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode()
                        + b"\0" + data).hexdigest()


def checked(command: list[str], *, cwd: Path | None = None,
            timeout: int = 90) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True,
                            text=True, timeout=timeout)
    require(result.returncode == 0,
            f"command failed rc={result.returncode}: "
            f"{shlex.join(command[:5])}: {result.stderr[-2500:]}")
    return result.stdout


def check_patch(src: Path, patch: Path) -> None:
    for flags in (["--check"], []):
        checked(["git", "-C", str(src), "apply", "--whitespace=error",
                 *flags, str(patch)])


def make_overlay(staged_sys: Path, root: Path,
                 patched_src: Path) -> Path:
    """Symlink unchanged staged source trees; never mutate any originals."""
    target = root / "overlay/sys"
    original = staged_sys
    for part in ("external", "bsd", "drm2", "i915drm"):
        target.mkdir(parents=True, exist_ok=True)
        for item in original.iterdir():
            if item.name != part:
                (target / item.name).symlink_to(item)
        target = target / part
        original = original / part
    target.mkdir(parents=True, exist_ok=True)
    for item in original.iterdir():
        dest = target / item.name
        if item.name in (I915.name, FILES.name):
            dest.write_bytes((patched_src / item.name).read_bytes())
        else:
            dest.symlink_to(item)
    return root / "overlay/sys"


def find_compiler_commands(compile_log: Path,
                           gcc: Path) -> dict[str, list[str]]:
    commands = {}
    with compile_log.open(errors="replace") as stream:
        for line in stream:
            if " -c " not in line or str(gcc) not in line:
                continue
            argv = shlex.split(line.strip())
            if not argv or argv[0] != str(gcc):
                continue
            for name in ("i915_pci_autoconf.o", "ioconf.o"):
                if (name not in commands and len(argv) >= 5 and
                        argv[-3:] == [argv[-3], "-o", name] and
                        argv[-4] == "-c"):
                    commands[name] = argv
            if len(commands) == 2:
                break
    require(len(commands) == 2,
            "historical GCC invocation for i915/ioconf objects not found")
    for name, argv in commands.items():
        require(argv[-4] == "-c" and argv[-2:] == ["-o", name],
                f"invalid compile command for {name}")
    return commands


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pinned-source", type=Path, required=True,
                   help="full pinned NetBSD source snapshot (read-only)")
    p.add_argument("--staged-source", type=Path, required=True,
                   help="previously built RTL STAGE NetBSD tree (read-only)")
    p.add_argument("--tools", type=Path, required=True,
                   help="existing NetBSD cross-toolchain root (read-only)")
    p.add_argument("--baseline-objects", type=Path, required=True,
                   help="previously linked kernel compile object dir (read-only)")
    p.add_argument("--historical-compile-log", type=Path, required=True)
    p.add_argument("--kernel-config", default="RTWN8723BE_STAGE")
    p.add_argument("--output", type=Path, required=True,
                   help="NEW scratch directory; never existing data")
    args = p.parse_args()

    pinned = args.pinned_source.resolve(strict=True)
    staged = args.staged_source.resolve(strict=True)
    tools = args.tools.resolve(strict=True)
    objs = args.baseline_objects.resolve(strict=True)
    log = args.historical_compile_log.resolve(strict=True)
    target = args.output.resolve()
    require(not target.exists(), "output must not already exist")
    require(target.is_relative_to(Path("/tmp")),
            "isolation guard: output must be within /tmp")
    require(objs != target and pinned != target and staged != target,
            "output may not overlap read-only inputs")
    require(shutil.disk_usage(target.parent).free > 2_000_000_000,
            "need at least 2 GiB of available scratch storage")
    require(args.kernel_config == objs.name,
            "kernel config must match existing compiled object directory")

    gcc = tools / "bin/x86_64--netbsd-gcc"
    nbconfig = tools / "bin/nbconfig"
    nbmake = tools / "bin/nbmake-amd64"
    ctf = tools / "bin/nbctfconvert"
    readelf = tools / "bin/x86_64--netbsd-readelf"
    for path in (gcc, nbconfig, nbmake, ctf, readelf):
        require(path.is_file(), f"missing original NetBSD build tool {path}")
    require(NETBSD_TARGET in checked([str(gcc), "-dumpmachine"]).strip(),
            "crosscompiler is not targeting NetBSD amd64")
    require((objs / "netbsd").is_file() and
            (objs / "i915_pci_autoconf.o").is_file() and
            (objs / "ioconf.o").is_file(),
            "baseline linked test kernel objects missing")

    # Source integrity gate occurs before allocating scratch or writing data.
    originals = {}
    for rel, expected in SHAS.items():
        data = (pinned / rel).read_bytes()
        require(git_blob(data) == expected,
                f"unpinned original NetBSD blob: {rel}")
        staged_data = (staged / rel).read_bytes()
        require(git_blob(staged_data) == expected,
                f"staged source is not the original i915 blob: {rel}")
        originals[rel] = data
    print("F24_2_PINNED_NETBSD_GIT_BLOBS_VERIFIED", flush=True)

    target.mkdir(parents=True)
    source_root = target / "pinned-original"
    for rel, data in originals.items():
        item = source_root / rel
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(data)
    for patch in PATCHES:
        check_patch(source_root, patch)
        print("F24_REAL_GIT_APPLY_PASS", patch.name, flush=True)
    patched = source_root / I915.parent
    overlay = make_overlay(staged / "sys", target, patched)
    compiled = target / "native-objects"
    compiled.mkdir()

    original_config = (
        staged / "sys/arch/amd64/conf" / args.kernel_config).read_text()
    baseline_ioconf = (objs / "ioconf.c").read_text()
    generated = {}
    for enabled in (False, True):
        label = "ON" if enabled else "OFF"
        conf_file = target / f"config-{label}"
        conf_file.write_text(
            original_config +
            ("\noptions " + OPTION + "\n" if enabled else "\n"))
        confdir = target / f"generated-{label}"
        confdir.mkdir()
        checked([str(nbconfig), "-s", str(overlay), "-b", str(confdir),
                 str(conf_file)], timeout=80)
        hdr = confdir / "opt_hp_i915_fwfb_failover.h"
        require(hdr.is_file(), "NetBSD config option header not generated")
        hdr_content = hdr.read_text()
        require((f"#define\t{OPTION}\t1" in hdr_content) == enabled,
                f"wrong NetBSD configuration status {label}")
        ioconf = (confdir / "ioconf.c").read_text()
        require(ioconf.count(NEW_ATTR) == 1,
                f"i915 wsdisplay interface missing from {label}")
        require(baseline_ioconf.count(OLD_ATTR) == 1,
                "historical i915 attribute line changed")
        changes = [line for line in difflib.unified_diff(
            baseline_ioconf.splitlines(), ioconf.splitlines())
            if line.startswith(("+", "-")) and
            not line.startswith(("+++", "---"))]
        require(len(changes) == 4 and
                any(NEW_ATTR in line for line in changes),
                "unexpected old-to-new ioconf metadata drift")
        generated[label] = confdir
        print("F24_NBCONFIG_AND_IOCONF_INTERFACE_PASS", label, flush=True)

    commands = find_compiler_commands(log, gcc)
    for label in ("OFF", "ON"):
        directory = compiled / label
        directory.mkdir()
        c = directory / I915.name
        c.write_bytes((source_root / I915).read_bytes())
        shutil.copyfile(
            generated[label] / "opt_hp_i915_fwfb_failover.h",
            directory / "opt_hp_i915_fwfb_failover.h")
        output = directory / "i915_pci_autoconf.o"
        argv = commands[output.name][:-3] + [str(c), "-o", str(output)]
        checked(argv, cwd=objs, timeout=100)
        require(output.stat().st_size > 100_000,
                "NetBSD native i915 object unexpectedly small")
        print("F24_REAL_NETBSD_AMD64_I915_OBJECT_PASS", label, flush=True)

    ondir = compiled / "ON"
    generated_conf = ondir / "ioconf.c"
    shutil.copyfile(generated["ON"] / "ioconf.c", generated_conf)
    ioconf_obj = ondir / "ioconf.o"
    argv = commands[ioconf_obj.name][:-3] + [
        str(generated_conf), "-o", str(ioconf_obj)]
    checked(argv, cwd=objs, timeout=100)
    print("F24_REAL_NETBSD_AMD64_IOCONF_OBJECT_PASS", flush=True)

    # This is an isolated incremental re-link from an existing, historical
    # RTL STAGE kernel. It does not recompilate the full kernel source.
    linkdir = target / "isolated-RTWN-link" / args.kernel_config
    shutil.copytree(objs, linkdir, symlinks=True)
    for name in ("i915_pci_autoconf.o", "ioconf.o"):
        shutil.copyfile(ondir / name, linkdir / name)
        checked([str(ctf), "-g", "-L", "VERSION", "-g", name],
                cwd=linkdir, timeout=60)
    print("F24_NATIVE_CTF_CONVERSION_PASS", flush=True)

    result = subprocess.run(
        [str(nbmake), "-C", str(linkdir), "-j2", "netbsd"],
        capture_output=True, text=True, timeout=300)
    (target / "kernel-link.log").write_text(
        result.stdout + "\n" + result.stderr)
    require(result.returncode == 0,
            "NetBSD native kernel re-link failed: " +
            (result.stdout + result.stderr)[-3500:])
    kernel = linkdir / "netbsd"
    debug = linkdir / "netbsd.gdb"
    require(kernel.is_file() and kernel.stat().st_size > 10_000_000,
            "linked kernel artifact missing")
    require(debug.is_file(), "CTF-merged NetBSD debug kernel missing")
    elf = checked([str(readelf), "-h", str(kernel)])
    require("ELF64" in elf and "Advanced Micro Devices X86-64" in elf,
            "kernel is not a native NetBSD amd64 ELF executable")
    sections = checked([str(readelf), "-S", str(debug)])
    require(".SUNW_ctf" in sections, "native CTF merge did not finish")
    digest = hashlib.sha256(kernel.read_bytes()).hexdigest()
    print("F24_REAL_NETBSD_AMD64_KERNEL_RELINK_CTF_PASS", flush=True)
    print("F24_KERNEL_SHA256", digest, flush=True)
    print("F24_KERNEL_PATH", kernel, flush=True)
    print("F24_HISTORICAL_RTL_STAGE_NOT_A_FRESH_BUILD_OR_HP_BOOT",
          flush=True)


if __name__ == "__main__":
    main()
