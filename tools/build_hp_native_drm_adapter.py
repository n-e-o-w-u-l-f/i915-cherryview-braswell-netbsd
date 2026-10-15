#!/usr/bin/env python3
"""Re-run the exact frozen HP/NetBSD kernel build gate for the current DRM file adapter.

This tool never writes the root-owned source stage, replaces a kernel,
installs, reboots or claims physical Cherryview KMS acceptance.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# The compiler flags in the preserved 2026-10-06 evidence use this retired
# path.  It is a *translation anchor*, not a live source/build directory.
LEGACY_STAGE = Path("/root/hp-driver-port-20261005")
DRM_REL = Path("sys/external/bsd/drm2/drm/drm_cdevsw.c")
UNIT_RELS = {
    "linux_task": Path("sys/external/bsd/drm2/linux/linux_task.c"),
    "linux_module": Path("sys/external/bsd/drm2/linux/linux_module.c"),
    "drm_cdevsw": DRM_REL,
}
EXPECTED_NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
EXPECTED_LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def relocate_argument(arg, stage_root):
    """Relocate only exact historical path arguments; reject unknown uses."""
    old = str(LEGACY_STAGE)
    for prefix in ("--sysroot=", "-I", ""):
        if prefix and not arg.startswith(prefix):
            continue
        suffix = arg[len(prefix):]
        if suffix == old or suffix.startswith(old + "/"):
            return prefix + str(stage_root) + suffix[len(old):]
    if old in arg:
        raise RuntimeError("unmapped retired build argument: " + arg)
    return arg


def replay_command(row, name, stage_root, output, canonical):
    """Retarget a pinned NetBSD compiler invocation without changing flags."""
    cmd = list(row["command"])
    if (name not in UNIT_RELS or cmd.count("-c") != 1 or
            cmd.count("-o") != 1 or not cmd or
            cmd[0] != str(LEGACY_STAGE / "full-linux-tools/bin/x86_64--netbsd-gcc")):
        raise RuntimeError("unexpected historical compiler command: " + name)
    if "-Werror" not in cmd or "-nostdinc" not in cmd or "-D_KERNEL" not in cmd:
        raise RuntimeError("native kernel compiler safety flags changed: " + name)
    source_index = cmd.index("-c") + 1
    output_index = cmd.index("-o") + 1
    expected_source = LEGACY_STAGE / "netbsd-full-linux" / UNIT_RELS[name]
    if Path(cmd[source_index]) != expected_source:
        raise RuntimeError("unexpected historical source owner: " + name)
    source = (canonical if name == "drm_cdevsw" else
              stage_root / "netbsd-full-linux" / UNIT_RELS[name])
    cmd[source_index] = str(source)
    cmd[output_index] = str(output / (name + ".o"))
    cmd = [relocate_argument(arg, stage_root) for arg in cmd]
    if any(str(LEGACY_STAGE) in arg for arg in cmd):
        raise RuntimeError("retired build root survived relocation")
    return cmd, source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--stage-root", type=Path, required=True,
                    help="fresh HP build stage containing netbsd-full-linux, "
                         "full-linux-obj and full-linux-tools")
    ap.add_argument("--preflight-only", action="store_true",
                    help="validate stage, hashes and compiler argv without compiling")
    args = ap.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        ap.error("REFUSED: native kernel compilation is HP NetBSD only")
    stage_root = args.stage_root.resolve(strict=True)
    native_stage = stage_root / "netbsd-full-linux"
    obj_stage = stage_root / "full-linux-obj"
    compiler = stage_root / "full-linux-tools/bin/x86_64--netbsd-gcc"
    if (not stage_root.is_dir() or not native_stage.is_dir() or
            not (obj_stage / "machine/cdefs.h").is_file() or
            not compiler.is_file() or not os.access(compiler, os.X_OK)):
        ap.error("fresh HP native source/obj/tools stage is not configured")
    output = args.output.resolve()
    if output.exists():
        ap.error("refusing existing output; choose a new audit directory")
    # Proof directory must be under the actual, non-root owner's repository parent.
    expected_parent = ROOT.parent.resolve()
    if output.parent != expected_parent or not output.name.startswith("i915-native-drm-"):
        ap.error("output must be an isolated sibling of source checkouts")
    evidence_path = ROOT / "docs/evidence/HP_NATIVE_DRM_TASK_ENTRY_20261006.json"
    evidence = json.loads(evidence_path.read_text())
    checks = evidence["native_three_unit_gate"]["status"]["checks"]
    checked = {item["name"]: item for item in checks}
    if set(checked) != {"linux_task", "linux_module", "drm_cdevsw"}:
        raise RuntimeError("historical compiler contract does not match three-unit gate")
    staged = native_stage / DRM_REL
    canonical = ROOT / "compat/native-drm/drm_cdevsw.c"
    if not staged.is_file() or canonical.read_bytes() != staged.read_bytes():
        raise RuntimeError("GitHub DRM owner source differs from current HP stage")
    if digest(canonical) != "ae0ddb2629a89a2729fef8b1d6c00c865998d19d59c5a0aebafc7a66e6b0abc7":
        raise RuntimeError("DRM source baseline revision changed; review before native compilation")
    prepared = {}
    source_hashes = evidence["native_three_unit_gate"]["status"]["source_sha256"]
    for name in ("linux_task", "linux_module", "drm_cdevsw"):
        cmd, source = replay_command(checked[name], name, stage_root, output,
                                     canonical)
        if not source.is_file():
            raise RuntimeError("missing staged source: " + name)
        if name != "drm_cdevsw":
            expected = source_hashes[str(UNIT_RELS[name])]
            if digest(source) != expected:
                raise RuntimeError("staged task/module source drift: " + name)
        prepared[name] = (cmd, source)
    if args.preflight_only:
        print("HP_NATIVE_DRM_STAGE_REPLAY_PREFLIGHT_PASS", stage_root)
        return 0
    output.mkdir(mode=0o700)
    state = {
        "state": "RUNNING",
        "hostname": socket.gethostname(),
        "netbsd_pin": EXPECTED_NETBSD_PIN,
        "linux_pin": EXPECTED_LINUX_PIN,
        "source_sha256": digest(canonical),
        "source_path": str(canonical),
        "owner_output": str(output),
        "original_compiler_cwd": str(obj_stage),
        "stage_root": str(stage_root),
        "compiler": str(compiler),
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "units": [],
    }
    report = output / "status.json"
    def save():
        temp = output / "status.tmp"
        temp.write_text(json.dumps(state, indent=2) + "\n")
        temp.replace(report)
    save()
    try:
        for name in ("linux_task", "linux_module", "drm_cdevsw"):
            cmd, source = prepared[name]
            obj = output / (name + ".o")
            pre_hash = digest(source)
            result = subprocess.run(cmd, cwd=obj_stage,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=150)
            log = output / (name + ".log")
            log.write_text(result.stdout)
            entry = {
                "name": name, "exit": result.returncode,
                "source_sha256": pre_hash,
                "source_unchanged": digest(source) == pre_hash,
                "log_sha256": digest(log),
                "object": str(obj),
                "object_sha256": digest(obj) if obj.is_file() else None,
                "object_size": obj.stat().st_size if obj.is_file() else 0,
                "compiler_arguments_count": len(cmd),
            }
            state["units"].append(entry)
            save()
            print("HP_NATIVE_DRM_UNIT", name, result.returncode,
                  entry["object_size"], flush=True)
            if result.returncode != 0 or not entry["source_unchanged"] or entry["object_size"] == 0:
                raise RuntimeError("native compile/verification failed: " + name)
        state["state"] = "PASSED"
        state["limitation"] = (
            "Three native NetBSD kernel objects only; NOT a full DRM/TTM/i915 "
            "kernel link, HP KMS display/IRQ/PM acceptance or GPU hardware operation."
        )
    except Exception as e:
        state["state"] = "FAILED"
        state["error"] = str(e)
        raise
    finally:
        state["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print("HP_NATIVE_MODERN_DRM_THREE_OBJECTS_PASS", output)

if __name__ == "__main__":
    sys.exit(main())
