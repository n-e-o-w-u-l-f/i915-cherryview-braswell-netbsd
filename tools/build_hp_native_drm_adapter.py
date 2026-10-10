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
EXPECTED_NATIVE_STAGE = Path("/root/hp-driver-port-20261005/netbsd-full-linux")
EXPECTED_OBJ_STAGE = Path("/root/hp-driver-port-20261005/full-linux-obj")
EXPECTED_NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
EXPECTED_LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        ap.error("REFUSED: native kernel compilation is HP NetBSD only")
    if not EXPECTED_NATIVE_STAGE.is_dir() or not (EXPECTED_OBJ_STAGE / "machine/cdefs.h").is_file():
        ap.error("native HP source/object stage is absent")
    output = args.output.resolve()
    if output.exists():
        ap.error("refusing existing output; choose a new audit directory")
    # Proof directory must be under the actual, non-root owner's repository parent.
    expected_parent = ROOT.parent.resolve()
    if output.parent != expected_parent or not output.name.startswith("i915-native-drm-"):
        ap.error("output must be an isolated sibling of source checkouts")
    output.mkdir(mode=0o700)
    evidence_path = ROOT / "docs/evidence/HP_NATIVE_DRM_TASK_ENTRY_20261006.json"
    evidence = json.loads(evidence_path.read_text())
    checks = evidence["native_three_unit_gate"]["status"]["checks"]
    checked = {item["name"]: item for item in checks}
    if set(checked) != {"linux_task", "linux_module", "drm_cdevsw"}:
        raise RuntimeError("historical compiler contract does not match three-unit gate")
    staged = EXPECTED_NATIVE_STAGE / "sys/external/bsd/drm2/drm/drm_cdevsw.c"
    canonical = ROOT / "compat/native-drm/drm_cdevsw.c"
    if canonical.read_bytes() != staged.read_bytes():
        raise RuntimeError("GitHub DRM owner source differs from current HP stage")
    if digest(canonical) != "ae0ddb2629a89a2729fef8b1d6c00c865998d19d59c5a0aebafc7a66e6b0abc7":
        raise RuntimeError("DRM source baseline revision changed; review before native compilation")
    state = {
        "state": "RUNNING",
        "hostname": socket.gethostname(),
        "netbsd_pin": EXPECTED_NETBSD_PIN,
        "linux_pin": EXPECTED_LINUX_PIN,
        "source_sha256": digest(canonical),
        "source_path": str(canonical),
        "owner_output": str(output),
        "original_compiler_cwd": str(EXPECTED_OBJ_STAGE),
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
            row = checked[name]
            cmd = list(row["command"])
            if "-o" not in cmd or "-c" not in cmd:
                raise RuntimeError(f"malformed native compiler command: {name}")
            original_source = Path(cmd[cmd.index("-c") + 1])
            if not original_source.is_file() or EXPECTED_NATIVE_STAGE not in original_source.parents:
                raise RuntimeError(f"unexpected original source path: {name}")
            source = canonical if name == "drm_cdevsw" else original_source
            cmd[cmd.index("-c") + 1] = str(source)
            obj = output / (name + ".o")
            cmd[cmd.index("-o") + 1] = str(obj)
            pre_hash = digest(source)
            result = subprocess.run(cmd, cwd=EXPECTED_OBJ_STAGE,
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
