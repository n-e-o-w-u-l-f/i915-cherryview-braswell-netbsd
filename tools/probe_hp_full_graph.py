#!/usr/bin/env python3
"""Fresh HP-native compilation of the exact configured 410 Linux C owners.

Failed/unbuilt units are retained. Not a full kernel link, provider closure,
install/boot admission or physical DRM acceptance.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import time

from hp_graph_contract import selected_units
from namespace_linux_compiler_math import require_native_hp
from prepare_hp_full_graph import configured_graph, digest

TOOLS = ("nbmake-amd64", "nbconfig", "x86_64--netbsd-gcc", "x86_64--netbsd-nm", "x86_64--netbsd-ld")


def fresh_artifacts(rows, obj):
    for row in rows:
        for suffix in (".o", ".d"):
            path = obj / (Path(row["object"]).stem + suffix)
            if path.exists() or path.is_symlink():
                raise RuntimeError("preserve existing object/dependency; configure a new stage: " + str(path))


def verify_elf(path):
    with path.open("rb") as stream:
        header = stream.read(64)
    if (len(header) < 64 or header[:7] != b"\x7fELF\x02\x01\x01" or
            header[16:24] != b"\x01\x00\x3e\x00\x01\x00\x00\x00" or header[52:54] != b"\x40\x00"):
        raise RuntimeError("expected actual amd64 ELF relocatable: " + str(path))


def dependency_inputs(dependency, source, tree, obj, base_tools):
    """Bind the actual new mkdep output; no lexical C include guessing."""
    if not dependency.is_file() or not dependency.stat().st_size:
        raise RuntimeError("successful dependency command produced no nonempty .d")
    paths = set()
    for line in dependency.read_text().replace("\\\n", " ").splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise RuntimeError("unrecognized native dependency record")
        for token in line.split(":", 1)[1].split():
            if any(char in token for char in ("$", "\\", "\x00")):
                raise RuntimeError("unexpanded/unsupported dependency token: " + token)
            path = Path(token)
            path = (path if path.is_absolute() else obj / path).resolve(strict=True)
            if not path.is_file() or not any(root in path.parents for root in (tree, obj, base_tools)):
                raise RuntimeError("dependency escapes admitted native inputs: " + str(path))
            paths.add(path)
    if source.resolve(strict=True) not in paths:
        raise RuntimeError("dependency output does not bind the selected C source")
    return {str(path): digest(path) for path in sorted(paths)}


def run_command(command, obj, env, log, timeout):
    """On timeout stop this invocation's whole native process group."""
    process = subprocess.Popen(command, cwd=obj, env=env, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # The make parent may exit before a compiler descendant. Always
        # finish group teardown, even when wait() already reaped that parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        log.write("native process-group timeout\n")
        return 124


def compile_one(item, tree, obj, tools, base_tools, output, env, timeout):
    row = dict(item, state="FAILED", commands=[])
    source = tree / "sys" / item["source"]
    stem = Path(item["object"]).stem
    dependency, artifact = obj / (stem + ".d"), obj / item["object"]
    log_path = output / (stem + ".log")
    started = time.monotonic()
    try:
        fresh_artifacts([item], obj)
        if digest(source) != item["source_sha256"]:
            raise RuntimeError("source changed before native compile")
        with log_path.open("w") as log:
            command = [str(tools / "bin/nbmake-amd64"), "-C", str(obj), stem + ".d"]
            row["commands"].append(command)
            row["d_exit"] = run_command(command, obj, env, log, timeout)
            if row["d_exit"] != 0:
                raise RuntimeError("native dependency command failed")
            deps = dependency_inputs(dependency, source, tree, obj, base_tools)
            if artifact.exists() or artifact.is_symlink():
                raise RuntimeError("dependency command unexpectedly produced an object; preserve it")
            row["dependency_sha256"] = digest(dependency)
            inventory = output / (stem + ".inputs.json")
            inventory.write_text(json.dumps(deps, indent=2) + "\n")
            row["input_inventory"] = {"path": str(inventory), "sha256": digest(inventory), "count": len(deps)}
            command = [str(tools / "bin/nbmake-amd64"), "-C", str(obj), item["object"]]
            row["commands"].append(command)
            row["o_exit"] = run_command(command, obj, env, log, timeout)
            row["source_unchanged"] = digest(source) == item["source_sha256"]
            row["inputs_unchanged"] = all(digest(Path(name)) == sha for name, sha in deps.items())
            row["dependency_graph_unchanged"] = dependency_inputs(dependency, source, tree, obj, base_tools) == deps
            if (row["o_exit"] != 0 or not row["source_unchanged"] or not row["inputs_unchanged"] or
                    not row["dependency_graph_unchanged"]):
                raise RuntimeError("native compile failed or its real inputs changed")
            verify_elf(artifact)
            row["artifact"] = {"path": str(artifact), "bytes": artifact.stat().st_size, "sha256": digest(artifact)}
            row["state"] = "PASSED"
    except (OSError, ValueError, RuntimeError) as error:
        row["error"] = str(error)
    row["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if log_path.is_file():
        row["log_sha256"] = digest(log_path)
        row["diagnostics"] = [line[:800] for line in log_path.read_text(errors="replace").splitlines()
            if "fatal error:" in line or "error:" in line or "Error code" in line][:12]
    return row


def stage_identity(work, staged, rows):
    paths = staged.get("paths", {})
    tree, obj, tools = [work / name for name in ("netbsd-full-linux", "full-linux-obj", "full-linux-tools")]
    for key, path in (("workspace", work), ("tree", tree), ("object_dir", obj), ("tool_dir", tools)):
        if Path(paths.get(key, "/missing")).resolve(strict=True) != path or not path.is_dir():
            raise RuntimeError("configured receipt does not bind the explicit workspace: " + key)
        if key != "workspace" and path.resolve(strict=True) != path:
            raise RuntimeError("stage directory is redirected outside its new workspace")
    recorded = staged.get("configured_graph_ownership", [])
    if (len(recorded) != len(rows) or {(r["group"], r["source"], r["object"]) for r in recorded} !=
            {(r["group"], r["source"], r["object"]) for r in rows}):
        raise RuntimeError("complete actual configured-owner receipt required")
    for row in recorded:
        source = (tree / "sys" / row["source"]).resolve(strict=True)
        if tree not in source.parents or digest(source) != row.get("source_sha256"):
            raise RuntimeError("source differs from configured owner receipt: " + row["source"])
    makefile = obj / "Makefile"
    if obj not in makefile.resolve(strict=True).parents:
        raise RuntimeError("configured Makefile escapes private object directory")
    if "makefile_sha256" in staged and digest(makefile) != staged["makefile_sha256"]:
        raise RuntimeError("configured Makefile differs from recorded hash")
    tool_hashes = {name: digest(tools / "bin" / name) for name in TOOLS}
    if "tools_sha256" in staged and tool_hashes != staged["tools_sha256"]:
        raise RuntimeError("native tool identity differs from configured stage")
    configs = {str(p.relative_to(tree)): digest(p) for p in
               sorted((tree / "sys/external/bsd/drm2").rglob("files.*")) if p.is_file()}
    for relative, sha in staged.get("manifest_sha256", {}).items():
        if digest(tree / relative) != sha:
            raise RuntimeError("native config manifest differs: " + relative)
    for name, sha in staged.get("source_transform_ledgers", {}).items():
        if Path(name).name != name or digest(work / name) != sha:
            raise RuntimeError("source transformation ledger differs")
    return {"stage_receipt_sha256": digest(work / "full-linux-graph-status.json"),
            "makefile_sha256": digest(makefile), "tools_sha256": tool_hashes,
            "staging_hashes_recorded": "makefile_sha256" in staged and "tools_sha256" in staged,
            "identity_scope": "Current before/after native identities; older staging receipts may omit initial Makefile/tool hashes.",
            "config_manifest_sha256": configs, "units": recorded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unit-timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        require_native_hp()
        work = args.workspace.resolve(strict=True)
        output = args.output
        if (not output.is_absolute() or output.exists() or output.is_symlink() or
                output.resolve().parent != work or work.stat().st_uid != os.geteuid() or args.unit_timeout <= 0):
            raise RuntimeError("new absolute owner output directly inside explicit workspace required")
        output = output.resolve()
        staged = json.loads((work / "full-linux-graph-status.json").read_text())
        if staged.get("state") != "CONFIGURED":
            raise RuntimeError("complete native CONFIGURED stage required")
        rows = selected_units(staged.get("units"), linux_pin=staged.get("linux_pin"), netbsd_pin=staged.get("netbsd_pin"))
        baseline = stage_identity(work, staged, rows)
        tree, obj, tools = [work / name for name in ("netbsd-full-linux", "full-linux-obj", "full-linux-tools")]
        base_tools = Path(staged["paths"]["base_tool_dir"]).resolve(strict=True)
        env = dict(os.environ, PATH=str(tools / "bin") + os.pathsep + os.environ.get("PATH", ""))
        fresh_artifacts(baseline["units"], obj)
        commands = [[str(tools / "bin/nbmake-amd64"), "-C", str(obj), "-v", variable]
                    for variable in ("ALLFILES", "OBJS")]
        expanded = [subprocess.check_output(command, text=True, env=env, timeout=60) for command in commands]
        if configured_graph(rows, tree, *expanded) != baseline["units"]:
            raise RuntimeError("actual expanded native selection differs from staged owners")
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    output.mkdir(mode=0o700)
    for name, value in zip(("configured-allfiles.txt", "configured-objs.txt"), expanded):
        (output / name).write_text(value)
    state = {"state": "RUNNING", "host": socket.gethostname(), "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "preflight": baseline, "selection_commands": commands,
             "units": [dict(row, state="UNBUILT") for row in baseline["units"]],
             "eligible_for_install": False, "eligible_for_boot": False,
             "limitation": "Fresh native 410-unit objects only; provider/semantic closure, full kernel link and physical DRM acceptance remain OPEN."}
    status = output / "status.json"

    def save():
        temporary = status.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(status)

    save()
    try:
        dependencies = {}
        for index, item in enumerate(baseline["units"]):
            row = compile_one(item, tree, obj, tools, base_tools, output, env, args.unit_timeout)
            state["units"][index] = row
            save()
            print(row["group"], Path(row["source"]).name, row["state"], flush=True)
            if row["state"] == "PASSED":
                for name, sha in json.loads(Path(row["input_inventory"]["path"]).read_text()).items():
                    if name in dependencies and dependencies[name] != sha:
                        raise RuntimeError("shared dependency changed between native units: " + name)
                    dependencies[name] = sha
        if stage_identity(work, staged, rows) != baseline:
            raise RuntimeError("source/configuration/tool identity changed during full probe")
        for name, sha in dependencies.items():
            if digest(Path(name)) != sha:
                raise RuntimeError("compiled dependency changed after its object: " + name)
        for row in state["units"]:
            if row["state"] == "PASSED":
                if digest(Path(row["artifact"]["path"])) != row["artifact"]["sha256"]:
                    raise RuntimeError("compiled object changed during probe")
                if digest(Path(row["input_inventory"]["path"])) != row["input_inventory"]["sha256"]:
                    raise RuntimeError("retained dependency inventory changed during probe")
        state["passed"] = sum(row["state"] == "PASSED" for row in state["units"])
        state["failed"] = sum(row["state"] == "FAILED" for row in state["units"])
        state["unbuilt"] = sum(row["state"] == "UNBUILT" for row in state["units"])
        state["state"] = "PASSED" if state["passed"] == 410 else "FAILED"
    except Exception as error:
        state["state"] = "FAILED"
        state["error"] = str(error)
    state["passed"] = sum(row["state"] == "PASSED" for row in state["units"])
    state["failed"] = sum(row["state"] == "FAILED" for row in state["units"])
    state["unbuilt"] = sum(row["state"] == "UNBUILT" for row in state["units"])
    state["finished"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
    return 0 if state["state"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
