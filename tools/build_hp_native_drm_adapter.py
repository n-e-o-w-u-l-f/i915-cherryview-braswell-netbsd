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
from hp_graph_preflight import arguments, execution_identity, preflight, require_hp
from audit_hp_native_drm_symbol_owners import verify_elf

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
EXPECTED_LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    arguments(ap)
    args = ap.parse_args()
    require_hp()
    if os.geteuid() == 0:
        ap.error('use the unprivileged HP owner workspace')
    inputs = preflight(args.native_tree, args.object_dir, args.tool_dir, args.graph_status)
    identity = execution_identity(inputs)
    native_tree, obj_stage, tool_dir = [Path(inputs[k]) for k in ('tree', 'object_dir', 'tool_dir')]
    output = args.output.resolve()
    if output.exists():
        ap.error("refusing existing output; choose a new audit directory")
    # Proof directory must be under the actual, non-root owner's repository parent.
    expected_parent = ROOT.parent.resolve()
    if output.parent != expected_parent or not output.name.startswith("i915-native-drm-"):
        ap.error("output must be an isolated sibling of source checkouts")
    if any(p == output or p in output.parents for p in (native_tree, obj_stage, tool_dir)):
        ap.error('output must not be inside source/object/tools')
    evidence_path = ROOT / "docs/evidence/HP_NATIVE_DRM_TASK_ENTRY_20261006.json"
    evidence = json.loads(evidence_path.read_text())
    checks = evidence["native_three_unit_gate"]["status"]["checks"]
    checked = {item["name"]: item for item in checks}
    if set(checked) != {"linux_task", "linux_module", "drm_cdevsw"}:
        raise RuntimeError("historical compiler contract does not match three-unit gate")
    canonical = ROOT / "compat/native-drm/drm_cdevsw.c"
    commands = {}
    # Historical commands supply the frozen strict flags, not current paths
    # or a claim that the old FAILED three-object evidence was successful.
    for name, row in checked.items():
        cmd = list(row['command'])
        if cmd.count('-o') != 1 or cmd.count('-c') != 1 or '-Werror' not in cmd or '-nostdinc' not in cmd:
            raise RuntimeError('malformed frozen compiler contract: ' + name)
        old_tree = '/root/hp-driver-port-20261005/netbsd-full-linux'
        old_obj = '/root/hp-driver-port-20261005/full-linux-obj'
        old_tools = '/root/hp-driver-port-20261005/full-linux-tools'
        cmd = [arg.replace(old_tree, str(native_tree)).replace(old_obj, str(obj_stage))
               .replace(old_tools, str(tool_dir)) for arg in cmd]
        original_source = Path(cmd[cmd.index('-c') + 1])
        if not original_source.is_file() or native_tree not in original_source.parents or original_source.stem != name:
            raise RuntimeError('unexpected stage source: ' + name)
        source = canonical if name == 'drm_cdevsw' else original_source
        cmd[cmd.index('-c') + 1] = str(source)
        cmd[cmd.index('-o') + 1] = str(output / (name + '.o'))
        if cmd[0] != str(tool_dir / 'bin/x86_64--netbsd-gcc'):
            raise RuntimeError('unexpected compiler')
        commands[name] = (cmd, source)
    output.mkdir(mode=0o700)
    state = {
        "state": "RUNNING",
        "hostname": socket.gethostname(),
        "netbsd_pin": EXPECTED_NETBSD_PIN,
        "linux_pin": EXPECTED_LINUX_PIN,
        "source_sha256": digest(canonical),
        "source_path": str(canonical),
        "owner_output": str(output),
        "compiler_cwd": str(obj_stage), "preflight": inputs, "execution_identity": identity,
        "frozen_command_ledger_sha256": digest(evidence_path),
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
            cmd, source = commands[name]
            obj = output / (name + ".o")
            cmd[cmd.index("-o") + 1] = str(obj)
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
                "command": cmd,
            }
            state["units"].append(entry)
            save()
            print("HP_NATIVE_DRM_UNIT", name, result.returncode,
                  entry["object_size"], flush=True)
            if result.returncode != 0 or not entry["source_unchanged"] or entry["object_size"] == 0:
                raise RuntimeError("native compile/verification failed: " + name)
            verify_elf(obj)
        if preflight(args.native_tree, args.object_dir, args.tool_dir, args.graph_status) != inputs or digest(canonical) != state['source_sha256']:
            raise RuntimeError('input identity changed during compilation')
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
