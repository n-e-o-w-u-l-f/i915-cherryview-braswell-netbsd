#!/usr/bin/env python3
"""Verify a completed HP F26 compile-only build; never install or boot it."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys

PROTECTED = {
    "/netbsd": "9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde",
    "/boot.cfg": "f7e0ccc00308172d5787f47c2c66b33921c53341f896e2339079a66980b6a4df",
}
BUILD_SOURCE = "5c7ac64c8c740701365dfbf3bf9159cc13fcf344"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)

def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def checked(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                            timeout=180)
    require(result.returncode == 0,
            f"command failed {args[:4]}: {result.stderr[-2000:]}")
    return result.stdout

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--source-stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-log", type=Path, required=True)
    parser.add_argument("--exit-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    source = args.source_stage.resolve(strict=True)
    output = args.output.resolve(strict=True)
    receipt = args.receipt.resolve()
    require(output.is_relative_to(Path("/tmp")), "output must be private scratch")
    require(receipt.is_relative_to(output), "receipt must stay inside output")
    symbols_file = receipt.with_suffix(".symbols.txt")
    require(not receipt.exists() and not symbols_file.exists(),
            "refusing to replace existing diagnostic artifacts")
    sys.path.insert(0, str(project / "tools"))
    import run_f26_native_chv_kernel as f26
    f26.require_native_hp(platform.system(), platform.release(),
                          platform.machine(), socket.gethostname())
    require(checked(["git", "-C", str(project), "rev-parse", "HEAD"]).strip()
            == BUILD_SOURCE, "build source HEAD drift")
    require(not checked(["git", "-C", str(project), "status", "--porcelain"]).strip(),
            "build source worktree changed")
    require(args.exit_file.read_text().strip() == "0",
            "native build has not terminated successfully")
    log = args.runner_log.read_text()
    require("F26_NATIVE_HP_11_PATCH_17_FILE_CLEAN_KERNEL_COMPILE_LINK_PASS" in log,
            "missing F26 terminal acceptance marker")
    f26.verify_manifest(source, project)
    compile_dir = output / "obj/sys/arch/amd64/compile/F26_CHV_FULL_RTL_TEST"
    kernel = compile_dir / "netbsd"
    require(kernel.resolve().is_relative_to(output),
            "kernel path escapes scratch")
    require(kernel.is_file() and kernel.stat().st_size > 10_000_000,
            "missing or unexpectedly small kernel")
    tools = output / "tools/bin"
    elf = checked([str(tools / "x86_64--netbsd-readelf"), "-h", str(kernel)])
    require("ELF64" in elf and "Advanced Micro Devices X86-64" in elf,
            "unexpected executable architecture")
    require("EXEC (Executable file)" in elf, "kernel must be an executable")
    objects = checked([str(tools / "nbmake-amd64"), "-V", "${OBJS}"],
                      cwd=compile_dir).split()
    require(len(objects) >= 3000, "not the complete configured GENERIC object set")
    require(all("$" not in name for name in objects), "unexpanded object list")
    missing = [name for name in objects if not (compile_dir / name).is_file()]
    require(not missing, "configured objects missing: " + repr(missing[:20]))
    required = {Path(name).stem + ".o" for name in f26.ORIGINAL
                if name.endswith(".c")}
    pci_lines = (source / "sys/dev/pci/files.pci").read_text().splitlines()
    rtl_objects = set()
    for line in pci_lines:
        fields = line.split()
        if len(fields) >= 3 and fields[0] == "file" and fields[1].startswith(
                "dev/pci/rtwn8723be") and fields[1].endswith(".c"):
            rtl_objects.add(Path(fields[1]).stem + ".o")
    require(len(rtl_objects) == 25, "unexpected older RTL PHY stage configuration")
    required.update(rtl_objects)
    required.add("ioconf.o")
    require(required.issubset(set(objects)), "configured driver object omitted")
    object_hashes = {name: sha256(compile_dir / name) for name in sorted(required)}
    symbols = checked([str(tools / "x86_64--netbsd-nm"), "-n", str(kernel)])
    names = {line.split()[-1] for line in symbols.splitlines() if line.split()}
    require({"i915drmkms_ca", "rtwn8723be_native_ca"}.issubset(names),
            "both native PCI attachment owners must be linked")
    undefined = checked([str(tools / "x86_64--netbsd-nm"), "-u", str(kernel)])
    require(not undefined.strip(), "unresolved symbols in final kernel")
    protected = {name: sha256(Path(name)) for name in PROTECTED}
    require(protected == PROTECTED, "protected installed kernel or boot config changed")
    modified = {name: sha256(output / "pinned" / name)
                for name in sorted(f26.ORIGINAL)}
    report = {
        "schema": 1, "status": "NATIVE_COMPILE_LINK_ARTIFACT_VERIFIED",
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host": socket.gethostname(), "os": platform.platform(),
        "build_source_commit": BUILD_SOURCE,
        "netbsd_pin": f26.f25.PIN,
        "rtl_phy_pin": "df3bc40086d38dcf0e25628c22c06f8c7674fe3d",
        "kernel_path": str(kernel), "kernel_bytes": kernel.stat().st_size,
        "kernel_sha256": sha256(kernel), "elf_header": elf,
        "configured_object_count": len(objects),
        "driver_object_sha256": object_hashes,
        "modified_source_sha256": modified,
        "patches": [{"path": name, "git_blob": blob}
                    for name, blob, _ in f26.PATCHES],
        "source_manifest_sha256": sha256(args.runner_log.parent / "source-manifest.json"),
        "build_log_sha256": sha256(output / "kernel-build.log"),
        "runner_log_sha256": sha256(args.runner_log),
        "protected_sha256": protected,
        "symbol_map_path": str(symbols_file),
        "physical_test": "NOT_RUN", "installed": False, "booted": False,
        "modern_410_port": "OPEN", "full_rtl_runtime": "OPEN",
        "limitations": "F26 older native CHV plus partial RTL PHY only; never boot/install.",
    }
    with symbols_file.open("x") as stream:
        stream.write(symbols)
    report["symbol_map_sha256"] = sha256(symbols_file)
    with receipt.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
