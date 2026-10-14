#!/usr/bin/env python3
"""Compile every configured Linux i915/DRM/display/TTM unit on HP.

Retains per-unit logs and explicit failed/unbuilt rows. No kernel installation,
no skipped units, and no inference of semantic parity from compilation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import time
from hp_graph_preflight import arguments, digest, execution_identity, preflight, require_hp
from audit_hp_native_drm_symbol_owners import verify_elf

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    arguments(p)
    a = p.parse_args()
    require_hp()
    work = a.workspace.resolve(strict=True)
    output = a.output.resolve()
    protected = [a.native_tree.resolve(), a.object_dir.resolve(), a.tool_dir.resolve()]
    if output.parent != work or output.exists() or any(p == output or p in output.parents for p in protected):
        p.error("expected a new output directory in the isolated HP workspace")
    inputs = preflight(a.native_tree, a.object_dir, a.tool_dir, a.graph_status)
    tree, obj = Path(inputs['tree']), Path(inputs['object_dir'])
    make = Path(inputs['tool_dir']) / 'bin/nbmake-amd64'
    units = inputs['units']
    identity = execution_identity(inputs)
    # An up-to-date old object is not evidence of this invocation compiling it.
    for row in units:
        for suffix in ('.o', '.d'):
            if (obj / (Path(row['object']).stem + suffix)).exists():
                p.error('preserve existing outputs and use a fresh configured object stage: ' + row['object'])
    output.mkdir()
    state = {"state": "RUNNING", "host": socket.gethostname(),
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "expected_units": len(units), "expected_i915_units": 323,
        "makefile_sha256": hashlib.sha256((obj / "Makefile").read_bytes()).hexdigest(),
        "preflight": inputs, "execution_identity": identity,
        "units": [], "limitation": "native development compilation only; semantic/API/adapter/runtime closure remains required"}
    status = output / "status.json"
    def save():
        state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tmp = status.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n"); tmp.replace(status)
    def compile_one(item):
        group, source = item['group'], item['source']
        stem = Path(source).stem
        started = time.monotonic()
        row = {"group": group, "source": source,
            "source_sha256": hashlib.sha256((tree / "sys" / source).read_bytes()).hexdigest(), "commands": []}
        log_path = output / (stem + ".log")
        with log_path.open("w") as log:
            for suffix in (".d", ".o"):
                command = [str(make), "-C", str(obj), stem + suffix]
                row["commands"].append(command)
                try:
                    rc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120).returncode
                except subprocess.TimeoutExpired:
                    rc = 124
                except OSError as error:
                    log.write(str(error) + '\n')
                    rc = 127
                row[suffix[1:] + "_exit"] = rc
                if rc != 0:
                    break
                if suffix == '.d':
                    dependency = obj / (stem + '.d')
                    if not dependency.is_file() or not dependency.stat().st_size:
                        row['error'] = 'successful dependency command produced no nonempty .d'
                        break
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        row["source_unchanged"] = digest(tree / 'sys' / source) == row['source_sha256']
        row["state"] = "PASSED" if row.get("o_exit") == 0 and row['source_unchanged'] else "FAILED"
        if row["state"] == "PASSED":
            artifact = obj / (stem + ".o")
            if not artifact.is_file() or not artifact.stat().st_size:
                row["state"] = "FAILED"; row["error"] = "missing/empty object"
            else:
                verify_elf(artifact)
                row["artifact"] = {"path": str(artifact), "bytes": artifact.stat().st_size,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        row["diagnostics"] = [line[:500] for line in log_path.read_text(errors="replace").splitlines()
            if "fatal error:" in line or "error:" in line or "Error code" in line][:6]
        return row
    save()
    # Serial by default: native dependency/header generators can share outputs.
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {pool.submit(compile_one, unit): unit for unit in units}
        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception as error:
                unit = futures[future]
                row = dict(group=unit['group'], source=unit['source'], state='FAILED', error=str(error))
            state["units"].append(row); save()
            print(row["group"], Path(row["source"]).name, row["state"], flush=True)
    state["units"].sort(key=lambda row: row["source"])
    state["passed"] = sum(row["state"] == "PASSED" for row in state["units"])
    state["failed"] = len(units) - state["passed"]
    # Revalidate configuration/tool/source identity after all unit probes.
    try:
        if preflight(a.native_tree, a.object_dir, a.tool_dir, a.graph_status) != inputs:
            raise ValueError('stage identity changed during probe')
    except (ValueError, OSError) as error:
        state['preflight_error'] = str(error)
    state["state"] = "PASSED" if not state["failed"] and not state.get('preflight_error') else "FAILED"
    save()
    return 0 if state["state"] == "PASSED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
