#!/usr/bin/env python3
"""Create a separate HP development tree with the complete pinned i915 graph.

All Linux units remain selected, including units historically replaced by
NetBSD overrides. The old adapter units are retained as source for reconciliation;
only separate NetBSD additions join this experimental graph. This is a build
probe, not a parity claim or an installable candidate. Existing trees are never
overwritten. Compiler/tool execution is confined to HP.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tempfile

from generate_netbsd_i915_filelist import CONFIG, LINUX_PIN
from materialize_linux_i915 import NETBSD_PIN
from hp_graph_contract import selected_units
from namespace_linux_compiler_math import (disjoint, relative_input, require_native_hp,
                                          integrate)
from materialize_linux_api_inputs import populate

PROFILE = dict(CONFIG, CONFIG_64BIT="y", CONFIG_CC_HAS_INT128="y",
    CONFIG_ARCH_SUPPORTS_INT128="y", CONFIG_DRM="y", CONFIG_PCI="y", CONFIG_AGP="y",
    CONFIG_DRM_CLIENT="y", CONFIG_DRM_CLIENT_SELECTION="y",
    CONFIG_DRM_KMS_HELPER="y", CONFIG_DRM_DISPLAY_HELPER="y",
    CONFIG_DRM_DISPLAY_DP_HELPER="y", CONFIG_DRM_DISPLAY_DSC_HELPER="y",
    CONFIG_DRM_DISPLAY_HDCP_HELPER="y", CONFIG_DRM_DISPLAY_HDMI_HELPER="y",
    CONFIG_DRM_PANEL="y", CONFIG_DRM_MIPI_DSI="y", CONFIG_DRM_TTM="y",
    CONFIG_DRM_BUDDY="y")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def clean_reference(path, pin):
    head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain=v1",
                                     "--untracked-files=all"], text=True)
    if head != pin or dirty.strip():
        raise RuntimeError("clean pinned reference required: " + str(path))

def stage_outputs(work, inputs):
    """Admit only new, disjoint outputs; inputs may be siblings in work."""
    names = ("netbsd-full-linux", "full-linux-obj", "full-linux-tools",
             "full-linux-graph-status.json", "full-linux-graph-status.tmp",
             "full-linux-compiler-math-seeds.json", "full-linux-api-inputs.json",
             "full-linux-compiler-math-final.json", "configured-allfiles.txt", "configured-objs.txt")
    result = {name: work / name for name in names}
    for path in result.values():
        if path.exists() or path.is_symlink():
            raise RuntimeError("preserve existing full-graph output: " + str(path))
        resolved = path.resolve()
        if resolved.parent != work or any(not disjoint(resolved, item) for item in inputs):
            raise RuntimeError("output overlaps an explicit reference: " + str(path))
    return result

def copy_reference(reference, tree):
    # Never share the reference's Git index/config/worktree metadata. sys and
    # common are private copies; remaining source inputs are read-only links.
    for entry in reference.iterdir():
        if entry.name in {".git", ".gitignore", ".gitattributes", ".gitmodules"}:
            continue
        if entry.name in {"sys", "common"}:
            shutil.copytree(entry, tree / entry.name, symlinks=True)
        else:
            (tree / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())

def configured_graph(rows, tree, allfiles, objects):
    """Bind required Linux sources to the actual expanded config(5) owners."""
    owners = {}
    required = {row["object"] for row in rows}
    source_root = (tree / "sys").resolve()
    for token in allfiles.split():
        # Generated/support units outside the required Linux 410 are not
        # certified by this gate. Their full native selection is retained in
        # the receipt; inspect every possible same-basename owner of our set.
        if Path(token).stem + ".o" not in required:
            continue
        # Resolve native source spellings against S, rather than treating
        # config(5) output as an untrusted Linux-relative manifest name.
        source = Path(token) if Path(token).is_absolute() else source_root / token
        source = source.resolve(strict=True)
        if tree.resolve() not in source.parents:
            raise RuntimeError("configured source escapes explicit tree: " + token)
        relative = (source.relative_to(source_root).as_posix() if source_root in source.parents
                    else "../" + source.relative_to(tree.resolve()).as_posix())
        if source.suffix in {".c", ".S", ".s"}:
            owners.setdefault(source.stem + ".o", set()).add(relative)
    selected = objects.split()
    if len(selected) != len(set(selected)):
        raise RuntimeError("duplicate expanded configured objects")
    selected = set(selected)
    verified = []
    for row in rows:
        if row["object"] not in selected or owners.get(row["object"]) != {row["source"]}:
            raise RuntimeError("configured graph owner differs: " + row["object"])
        verified.append(dict(row, source_sha256=digest(tree / "sys" / row["source"])))
    return verified

def selected(root, directory, variables, direct=()):
    # GNU make expands the actual frozen Makefiles; no compiler is invoked.
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("show-port:\n\t@printf '%s\\n' " +
                " ".join("$(" + v + ")" for v in variables) + "\ninclude Makefile\n")
        wrapper = Path(f.name)
    try:
        result = subprocess.check_output(["gmake", "-s", "-f", str(wrapper), "show-port"],
            cwd=root / directory, env=dict(os.environ, **PROFILE, src="."), text=True)
    finally:
        wrapper.unlink()
    names = sorted(set([x[:-2] + ".c" for x in result.split() if x.endswith(".o")] + list(direct)))
    for name in names:
        if not (root / directory / name).is_file():
            raise RuntimeError("unmaterialized active source: " + directory + "/" + name)
    return names

def replace_units(path, units, attribute, additions):
    old = path.read_text()
    # Preserve definitions/options but discard every old source selection. Never
    # substitute a same-basename old override for an unreviewed Linux unit.
    prefix = "\n".join(line for line in old.splitlines()
        if not re.match(r"^\s*#?file\s", line)) + "\n"
    if attribute == "i915drmkms":
        prefix = prefix.replace("i915drmkms: acpivga, drmkms,", "i915drmkms: acpivga, drmkms, drmkms_ttm,")
        # Remove historical CONFIG values, which contradict the actual 323-unit
        # profile, e.g. CAPTURE_ERROR=0 and invalid FORCE_PROBE=0 (a string).
        prefix = "\n".join(line for line in prefix.splitlines()
            if not ("makeoptions" in line and "-DCONFIG_" in line)) + "\n"
        defaults = dict(PROFILE, CONFIG_PM="y", CONFIG_DRM_I915_DEBUG_GEM="y",
            CONFIG_DRM_I915_PREEMPT_TIMEOUT="640", CONFIG_DRM_I915_TIMESLICE_DURATION="1",
            CONFIG_DRM_I915_HEARTBEAT_INTERVAL="2500", CONFIG_DRM_I915_STOP_TIMEOUT="100")
        for key, value in sorted(defaults.items()):
            value = "1" if value == "y" else value
            prefix += f'makeoptions\ti915drmkms\t"CPPFLAGS.i915drmkms"+="-D{key}={value}"\n'
    lines = [f"file\t{source}\t{attribute}\n" for source in units]
    for source, condition in additions:
        lines.append(f"file\t{source}\t{condition}\n")
    path.write_text(prefix + "# Complete frozen Linux source graph; adapter parity remains open.\n" + "".join(lines))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--linux-tree", type=Path, required=True)
    p.add_argument("--netbsd-reference", type=Path, required=True)
    p.add_argument("--materialized-tree", type=Path, required=True)
    p.add_argument("--base-tool-dir", type=Path, default=Path("/usr/tools"))
    a = p.parse_args()
    try:
        require_native_hp()
        work, linux, reference, source, base_tools = [item.resolve(strict=True) for item in
            (a.workspace, a.linux_tree, a.netbsd_reference, a.materialized_tree, a.base_tool_dir)]
        if not all(item.is_dir() for item in (work, linux, reference, source, base_tools)):
            raise RuntimeError("explicit workspace and source/tool directories required")
        if work.stat().st_uid != os.geteuid():
            raise RuntimeError("workspace must belong to the executing HP owner")
        if not all(disjoint(left, right) for left, right in
                   ((linux, reference), (linux, source), (reference, source))):
            raise RuntimeError("Linux, NetBSD and materialized references must be separate")
        outputs = stage_outputs(work, (linux, reference, source, base_tools))
        clean_reference(reference, NETBSD_PIN)
        clean_reference(linux, LINUX_PIN)
        for name in ("nbmake-amd64", "nbconfig", "x86_64--netbsd-gcc", "x86_64--netbsd-nm",
                     "x86_64--netbsd-ld"):
            if not (base_tools / "bin" / name).is_file() or not os.access(base_tools / "bin" / name, os.X_OK):
                raise RuntimeError("missing executable native tool: " + name)
    except (OSError, ValueError, RuntimeError) as error:
        p.error(str(error))
    manifest = json.loads((source / "PORT-MANIFEST.json").read_text())
    if not manifest.get("linux_head_verified") or manifest.get("linux_pin") != LINUX_PIN or manifest.get("netbsd_pin") != NETBSD_PIN:
        p.error("unverified or different frozen reference")
    frozen = json.loads((Path(__file__).resolve().parents[1] /
                         "docs/evidence/HP_I915_REFERENCE_MANIFEST_20261005.json").read_text())
    observed = {row["path"]: row["sha256"] for row in manifest["files"]}
    if (len(observed) != len(manifest["files"]) or
            observed != {row["path"]: row["sha256"] for row in frozen["files"]}):
        p.error("materialized source membership/hashes differ from reviewed frozen ledger")
    for row in manifest["files"]:
        relative_input(row["path"])
        if source not in (source / row["path"]).resolve(strict=True).parents:
            p.error("materialized source escapes explicit reference: " + row["path"])
        if digest(source / row["path"]) != row["sha256"]:
            p.error("modified materialized reference: " + row["path"])
    groups = {
        "i915": selected(source, "drivers/gpu/drm/i915", ["i915-y"]),
        "drm": selected(source, "drivers/gpu/drm", ["drm-y", "drm_kms_helper-y"],
                        ["drm_buddy.c", "drm_mipi_dsi.c"]),
        "display": selected(source, "drivers/gpu/drm/display", ["drm_display_helper-y"]),
        "ttm": selected(source, "drivers/gpu/drm/ttm", ["ttm-y"]),
    }
    try:
        graph_rows = selected_units(groups, linux_pin=manifest.get("linux_pin"),
                                    netbsd_pin=manifest.get("netbsd_pin"))
    except (OSError, ValueError) as error:
        p.error(str(error))
    tree, obj, tools = [outputs[name] for name in ("netbsd-full-linux", "full-linux-obj", "full-linux-tools")]
    tree.mkdir()
    state = {"state": "STAGING", "host": socket.gethostname(), "linux_pin": LINUX_PIN,
        "netbsd_pin": NETBSD_PIN, "profile": PROFILE, "units": groups,
        "reference_manifest_sha256": digest(source / "PORT-MANIFEST.json"),
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(), "commands": [],
        "paths": {"workspace": str(work), "linux_reference": str(linux), "netbsd_reference": str(reference),
                  "materialized_reference": str(source), "tree": str(tree), "object_dir": str(obj),
                  "tool_dir": str(tools), "base_tool_dir": str(base_tools)},
        "eligible_for_install": False, "eligible_for_boot": False,
        "modern_bridge_state": "UNREVIEWED; complete file/MM/poll/DRM providers are not supplied by staging"}
    status = work / "full-linux-graph-status.json"
    def save():
        tmp = status.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        tmp.replace(status)
    def run(command):
        state["commands"].append(command); save()
        print("RUN", command, flush=True)
        env = dict(os.environ)
        if command[0] == "git":
            # git apply needs no repository. Do not discover or use a parent
            # checkout's index/config when this private source has no .git.
            env["GIT_CEILING_DIRECTORIES"] = str(tree.parent)
        subprocess.run(command, check=True, env=env)
    save()
    try:
        copy_reference(reference, tree)
        clean_reference(reference, NETBSD_PIN)
        drm = tree / "sys/external/bsd/drm2"
        # Real tristate helpers are needed before any modern DRM header is
        # parsed, matching Linux Kbuild's forced kconfig include. Native
        # nbconfig flags remain the inputs; no Linux VM-layout constants are
        # fabricated for the NetBSD page adapter.
        owner = Path(__file__).resolve().parents[1]
        native_kconfig = tree / "sys/external/bsd/common/include/linux/kconfig.h"
        shutil.copyfile(owner / "compat/linux/kconfig.h", native_kconfig)
        run(["git", "-C", str(tree), "apply", "--check",
             str(owner / "patches/0019-netbsd-linux-kconfig-helpers.patch")])
        run(["git", "-C", str(tree), "apply",
             str(owner / "patches/0019-netbsd-linux-kconfig-helpers.patch")])
        run(["git", "-C", str(tree), "apply", "--check",
             str(owner / "patches/0018-netbsd-linux-memory-ordering.patch")])
        run(["git", "-C", str(tree), "apply",
             str(owner / "patches/0018-netbsd-linux-memory-ordering.patch")])
        for patch in ("0020-netbsd-linux-posix-types.patch",
                      "0021-netbsd-linux-augmented-rbtree.patch",
                      "0023-netbsd-linux-native-word-size.patch",
                      "0024-netbsd-linux-raw-spinlock.patch",
                      "0025-netbsd-linux-instruction-pointer.patch",
                      "0026-netbsd-linux-compiler-math.patch",
                      "0027-netbsd-linux-math64.patch",
                      "0028-netbsd-linux-completion-contract.patch",
                      "0029-netbsd-linux-typecheck-wordpart.patch",
                      "0030-netbsd-linux-container-type-contract.patch",
                      "0031-netbsd-linux-typed-object-allocation.patch",
                      "0032-netbsd-linux-task-wait-worker.patch",
                      "0033-netbsd-linux-uuid-guid.patch",
                      "0034-netbsd-linux-pwm-consumer.patch", '0035-netbsd-linux-fatal-wait.patch',
                      '0036-netbsd-linux-bit-wait-policy.patch',
                      '0037-netbsd-linux-drm-ioctl-task-entry.patch'):
            run(["git", "-C", str(tree), "apply", "--check", str(owner / "patches" / patch)])
            run(["git", "-C", str(tree), "apply", str(owner / "patches" / patch)])
        # Source paths are translated explicitly, preserving the reference tree
        # and old NetBSD overrides. Changed ABI/header adapters remain visible.
        for row in manifest["files"]:
            rel = row["path"]
            target = drm / "dist" / (rel.removeprefix("drivers/gpu/") if rel.startswith("drivers/gpu/") else rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, target)
        root_callsites = owner / "patches/0022-netbsd-linux-rbtree-call-sites.patch"
        run(["git", "-C", str(tree), "apply", "--check", str(root_callsites)])
        run(["git", "-C", str(tree), "apply", str(root_callsites)])
        seed_ledger = outputs["full-linux-compiler-math-seeds.json"]
        api_ledger = outputs["full-linux-api-inputs.json"]
        final_ledger = outputs["full-linux-compiler-math-final.json"]
        integrate(linux, tree, source / "PORT-MANIFEST.json", None, seed_ledger)
        populate(linux, tree, api_ledger, json.loads(seed_ledger.read_text()),
                 manifest_path=source / "PORT-MANIFEST.json")
        integrate(linux, tree, source / "PORT-MANIFEST.json", api_ledger, final_ledger)
        state["source_transform_ledgers"] = {path.name: digest(path)
            for path in (seed_ledger, api_ledger, final_ledger)}
        # Distinguish NetBSD's module entry from Linux's selected i915_module.c.
        shutil.copyfile(drm / "i915drm/i915_module.c", drm / "i915drm/netbsd_i915_module.c")
        # config(5) otherwise silently selects the old same-basename PCI
        # adapter and omits the newly selected Linux drm_pci.c entirely.
        shutil.copyfile(drm / "pci/drm_pci.c", drm / "pci/netbsd_drm_pci.c")
        pci_manifest = drm / "pci/files.drmkms_pci"
        pci_text = pci_manifest.read_text()
        native_pci = "external/bsd/drm2/pci/drm_pci.c"
        if pci_text.count(native_pci) != 1:
            raise RuntimeError("unexpected native PCI adapter selection")
        pci_manifest.write_text(pci_text.replace(native_pci,
            "external/bsd/drm2/pci/netbsd_drm_pci.c"))
        prefix = "external/bsd/drm2/"
        replace_units(drm / "i915drm/files.i915drmkms",
            [prefix + "dist/drm/i915/" + name for name in groups["i915"]], "i915drmkms", [
                (prefix + "i915drm/netbsd_i915_module.c", "i915drmkms"),
                (prefix + "i915drm/i915_pci_autoconf.c", "i915drmkms"),
                (prefix + "i915drm/intel_gtt_subr.c", "i915drmkms"),
                (prefix + "i915drm/intelfb.c", "intelfb")])
        drm_manifest = drm / "drm/files.drmkms"
        additions = []
        for line in drm_manifest.read_text().splitlines():
            match = re.match(r"^file\s+(\S+)\s+(.+)$", line)
            if match and not match[1].startswith(prefix + "dist/"):
                # Historical local overrides require new-ABI reconciliation;
                # additions implement the distinct native character/VM/module API.
                if Path(match[1]).name in {"drm_agp_hook.c", "drm_cdevsw.c", "drm_gem_vm.c", "drm_module.c", "drm_stub.c", "drm_sysctl.c", "drm_pci_busid.c", "drmfb.c"}:
                    additions.append((match[1], match[2]))
        replace_units(drm_manifest,
            [prefix + "dist/drm/" + name for name in groups["drm"]] +
            [prefix + "dist/drm/display/" + name for name in groups["display"]], "drmkms", additions)
        # Linux Kconfig's disabled booleans are absent. A =0 definition
        # incorrectly enables #ifdef branches such as GPU buddy lockdep.
        shared = re.sub(r"-D(CONFIG_[A-Z0-9_]+)=0(?=[\"\s])", r"-U\1", drm_manifest.read_text())
        for key, value in sorted(PROFILE.items()):
            value = "1" if value == "y" else value
            shared += f'makeoptions\tdrmkms\t"CPPFLAGS.drmkms"+="-D{key}={value}"\n'
        drm_manifest.write_text(shared)
        native_manifest = drm / "linux/files.drmkms_linux"
        native_manifest.write_text(native_manifest.read_text() +
            'makeoptions\tdrmkms_linux\t"CPPFLAGS.drmkms_linux"+="${CPPFLAGS.drmkms}"\n')
        drm_manifest.write_text(drm_manifest.read_text() +
            'makeoptions\tdrmkms\t"CPPFLAGS.drmkms"+="-DCONFIG_64BIT=1"\n' +
            'makeoptions\tdrmkms\t"CPPFLAGS.drmkms"+="-include $S/external/bsd/common/include/linux/kconfig.h"\n')
        replace_units(drm / "ttm/files.ttm",
            [prefix + "dist/drm/ttm/" + name for name in groups["ttm"]], "drmkms_ttm",
            [(prefix + "ttm/ttm_bus_dma.c", "drmkms_ttm")])
        config = tree / "sys/arch/amd64/conf/HP-FULL-LINUX-PROBE"
        config.write_text('include "arch/amd64/conf/GENERIC"\nident "HP-FULL-LINUX-PROBE"\n'
                          'no nouveau*\n')
        obj.mkdir(); tools.mkdir(); (tools / "bin").mkdir()
        for entry in base_tools.iterdir():
            if entry.name != "bin": (tools / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
        for entry in (base_tools / "bin").iterdir():
            if entry.name != "nbmake-amd64": (tools / "bin" / entry.name).symlink_to(entry)
        wrapper = (base_tools / "bin/nbmake-amd64").read_text()
        for old, new in [("/usr/src", tree), ("/usr/obj", obj), (str(base_tools), tools)]: wrapper = wrapper.replace(old, str(new))
        (tools / "bin/nbmake-amd64").write_text(wrapper)
        (tools / "bin/nbmake-amd64").chmod(0o755)
        run([str(tools / "bin/nbconfig"), "-s", str(tree / "sys"), "-b", str(obj), str(config)])
        expanded = {}
        for variable, filename in (("ALLFILES", "configured-allfiles.txt"), ("OBJS", "configured-objs.txt")):
            command = [str(tools / "bin/nbmake-amd64"), "-C", str(obj), "-v", variable]
            state["commands"].append(command); save()
            value = subprocess.check_output(command, text=True,
                env=dict(os.environ, PATH=str(tools / "bin") + os.pathsep + os.environ.get("PATH", "")))
            outputs[filename].write_text(value)
            expanded[variable] = value
        state["configured_graph_ownership"] = configured_graph(graph_rows, tree,
            expanded["ALLFILES"], expanded["OBJS"])
        native_adapter = drm / "drm/drm_cdevsw.c"
        canonical = owner / "compat/native-drm/drm_cdevsw.c"
        state["native_drm_adapter"] = {"path": str(native_adapter), "sha256": digest(native_adapter),
            "canonical_sha256": digest(canonical), "matches_canonical": native_adapter.read_bytes() == canonical.read_bytes(),
            "acceptance": "UNREVIEWED; configured source identity is not modern bridge/provider acceptance"}
        roots = [tree / "sys/external/bsd/common/include", drm / "include", drm / "dist/include"]
        state["missing_modern_bridge_headers"] = [name for name in
            ("linux/file_netbsd.h", "linux/mm_netbsd.h", "linux/task_netbsd.h", "drm/drm_file_netbsd.h")
            if not any((root / name).is_file() for root in roots)]
        state["state"] = "CONFIGURED"
        state["active_linux_units"] = len(graph_rows)
        state["adapter_state"] = "UNREVIEWED; development probe only; installation prohibited"
        state["manifest_sha256"] = {str(path.relative_to(tree)): digest(path) for path in
            [drm / "i915drm/files.i915drmkms", drm_manifest, drm / "ttm/files.ttm"]}
        state["makefile_sha256"] = digest(obj / "Makefile")
        state["tools_sha256"] = {name: digest(tools / "bin" / name) for name in
            ("nbmake-amd64", "nbconfig", "x86_64--netbsd-gcc", "x86_64--netbsd-nm", "x86_64--netbsd-ld")}
        save()
    except Exception as exc:
        state["state"] = "FAILED"; state["error"] = str(exc); save(); raise
    print("HP_FULL_LINUX_GRAPH_CONFIGURED", state["active_linux_units"], flush=True)

if __name__ == "__main__":
    main()
