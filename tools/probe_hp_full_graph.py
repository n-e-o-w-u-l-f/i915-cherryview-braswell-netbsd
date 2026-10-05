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

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("all compiler execution is authorized only on HP/NetBSD")
    work = a.workspace.resolve(strict=True)
    output = a.output.resolve()
    if work != Path("/root/hp-driver-port-20261005") or output.parent != work or output.exists():
        p.error("expected a new output directory in the isolated HP workspace")
    staged = json.loads((work / "full-linux-graph-status.json").read_text())
    if staged["state"] != "CONFIGURED" or len(staged["units"]["i915"]) != 323:
        p.error("complete frozen i915 graph must be configured first")
    tree, obj = work / "netbsd-full-linux", work / "full-linux-obj"
    make = work / "full-linux-tools/bin/nbmake-amd64"
    generated = (obj / "Makefile").read_text()
    units = []
    for group, names in staged["units"].items():
        for name in names:
            relative = "external/bsd/drm2/dist/drm/" + ("" if group == "drm" else group + "/") + name
            if relative not in generated or not (tree / "sys" / relative).is_file():
                p.error("configured native graph omits source: " + relative)
            units.append((group, relative))
    output.mkdir()
    state = {"state": "RUNNING", "host": socket.gethostname(),
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "expected_units": len(units), "expected_i915_units": 323,
        "makefile_sha256": hashlib.sha256((obj / "Makefile").read_bytes()).hexdigest(),
        "units": [], "limitation": "native development compilation only; semantic/API/adapter/runtime closure remains required"}
    status = output / "status.json"
    def save():
        state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tmp = status.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n"); tmp.replace(status)
    def compile_one(item):
        group, source = item
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
                row[suffix[1:] + "_exit"] = rc
                if rc != 0:
                    break
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        row["state"] = "PASSED" if row.get("o_exit") == 0 else "FAILED"
        if row["state"] == "PASSED":
            artifact = obj / (stem + ".o")
            if not artifact.is_file() or not artifact.stat().st_size:
                row["state"] = "FAILED"; row["error"] = "missing/empty object"
            else:
                row["artifact"] = {"bytes": artifact.stat().st_size,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        row["diagnostics"] = [line[:500] for line in log_path.read_text(errors="replace").splitlines()
            if "fatal error:" in line or "error:" in line or "Error code" in line][:6]
        return row
    save()
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(compile_one, unit) for unit in units]):
            row = future.result(); state["units"].append(row); save()
            print(row["group"], Path(row["source"]).name, row["state"], flush=True)
    state["units"].sort(key=lambda row: row["source"])
    state["passed"] = sum(row["state"] == "PASSED" for row in state["units"])
    state["failed"] = len(units) - state["passed"]
    state["state"] = "PASSED" if not state["failed"] else "FAILED"
    save()
    return 0 if state["state"] == "PASSED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
