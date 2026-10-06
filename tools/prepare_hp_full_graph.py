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

PROFILE = dict(CONFIG, CONFIG_64BIT="y", CONFIG_DRM="y", CONFIG_PCI="y", CONFIG_AGP="y",
    CONFIG_DRM_CLIENT="y", CONFIG_DRM_CLIENT_SELECTION="y",
    CONFIG_DRM_KMS_HELPER="y", CONFIG_DRM_DISPLAY_HELPER="y",
    CONFIG_DRM_DISPLAY_DP_HELPER="y", CONFIG_DRM_DISPLAY_DSC_HELPER="y",
    CONFIG_DRM_DISPLAY_HDCP_HELPER="y", CONFIG_DRM_DISPLAY_HDMI_HELPER="y",
    CONFIG_DRM_PANEL="y", CONFIG_DRM_MIPI_DSI="y", CONFIG_DRM_TTM="y",
    CONFIG_DRM_BUDDY="y")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

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
    p.add_argument("--linux-tree", type=Path, default=Path("/root/linux-rtl8723be-ref-fresh"))
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("native staging/build probes are authorized only on HP/NetBSD")
    work = a.workspace.resolve(strict=True)
    if work != Path("/root/hp-driver-port-20261005"):
        p.error("expected the isolated HP task workspace")
    source = work / "full-scope-audit/linux-stage-verified"
    manifest = json.loads((source / "PORT-MANIFEST.json").read_text())
    if not manifest.get("linux_head_verified") or manifest["linux_pin"] != LINUX_PIN or manifest["netbsd_pin"] != NETBSD_PIN:
        p.error("unverified or different frozen reference")
    for row in manifest["files"]:
        if digest(source / row["path"]) != row["sha256"]:
            p.error("modified materialized reference: " + row["path"])
    groups = {
        "i915": selected(source, "drivers/gpu/drm/i915", ["i915-y"]),
        "drm": selected(source, "drivers/gpu/drm", ["drm-y", "drm_kms_helper-y"],
                        ["drm_buddy.c", "drm_mipi_dsi.c"]),
        "display": selected(source, "drivers/gpu/drm/display", ["drm_display_helper-y"]),
        "ttm": selected(source, "drivers/gpu/drm/ttm", ["ttm-y"]),
    }
    if len(groups["i915"]) != 323:
        p.error("frozen i915 graph changed")
    linux_names = [Path(name).stem for names in groups.values() for name in names]
    if len(set(linux_names)) != len(linux_names):
        p.error("native object-name collision in frozen Linux graph")
    tree, obj, tools = [work / name for name in ("netbsd-full-linux", "full-linux-obj", "full-linux-tools")]
    if any(path.exists() for path in (tree, obj, tools)):
        p.error("full-graph output exists; preserve it and reconcile before another stage")
    reference = work / "netbsd-reference"
    tree.mkdir()
    state = {"state": "STAGING", "host": socket.gethostname(), "linux_pin": LINUX_PIN,
        "netbsd_pin": NETBSD_PIN, "profile": PROFILE, "units": groups,
        "reference_manifest_sha256": digest(source / "PORT-MANIFEST.json"),
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(), "commands": []}
    status = work / "full-linux-graph-status.json"
    def save():
        tmp = status.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        tmp.replace(status)
    def run(command):
        state["commands"].append(command); save()
        print("RUN", command, flush=True)
        subprocess.run(command, check=True)
    save()
    try:
        for entry in reference.iterdir():
            if entry.name == "sys":
                shutil.copytree(entry, tree / "sys", symlinks=True)
            else:
                (tree / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
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
                      "0026-netbsd-linux-compiler-math.patch"):
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
        run(["python3", str(owner / "tools/namespace_linux_compiler_math.py"),
             "--linux-tree", str(a.linux_tree), "--netbsd-tree", str(tree),
             "--manifest", str(source / "PORT-MANIFEST.json"),
             "--out-ledger", str(work / "full-linux-compiler-math-seeds.json")])
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
        config = tree / "sys/arch/amd64/conf/HP-FULL-LINUX-20261005"
        config.write_text('include "arch/amd64/conf/GENERIC"\nident "HP-FULL-LINUX-20261005"\n'
                          'no nouveau*\n')
        obj.mkdir(); tools.mkdir(); (tools / "bin").mkdir()
        for entry in Path("/usr/tools").iterdir():
            if entry.name != "bin": (tools / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
        for entry in Path("/usr/tools/bin").iterdir():
            if entry.name != "nbmake-amd64": (tools / "bin" / entry.name).symlink_to(entry)
        wrapper = (Path("/usr/tools/bin/nbmake-amd64")).read_text()
        for old, new in [("/usr/src", tree), ("/usr/obj", obj), ("/usr/tools", tools)]: wrapper = wrapper.replace(old, str(new))
        (tools / "bin/nbmake-amd64").write_text(wrapper)
        (tools / "bin/nbmake-amd64").chmod(0o755)
        run([str(tools / "bin/nbconfig"), "-s", str(tree / "sys"), "-b", str(obj), str(config)])
        state["state"] = "CONFIGURED"
        state["active_linux_units"] = len(linux_names)
        state["adapter_state"] = "UNREVIEWED; development probe only; installation prohibited"
        state["manifest_sha256"] = {str(path.relative_to(tree)): digest(path) for path in
            [drm / "i915drm/files.i915drmkms", drm_manifest, drm / "ttm/files.ttm"]}
        save()
    except Exception as exc:
        state["state"] = "FAILED"; state["error"] = str(exc); save(); raise
    print("HP_FULL_LINUX_GRAPH_CONFIGURED", state["active_linux_units"], flush=True)

if __name__ == "__main__":
    main()
