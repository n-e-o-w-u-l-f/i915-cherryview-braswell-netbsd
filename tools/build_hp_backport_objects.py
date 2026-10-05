#!/usr/bin/env python3
"""HP-only native object check for the preserved six-edit/backport stack.

Uses the separately prepared NetBSD stage and tools. This does not compile
the complete pinned Linux i915/DRM/TTM import, link or install a kernel.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import re
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
OVERLAY_SHA = "2623b640b713b01b1aa83383f9bf4a318abdd8d76963a3478f39dcc0cadca5bb"
DIRECTORY = Path("sys/external/bsd/drm2/dist/drm/i915")
OVERLAY_FILES = (
    "display/intel_display.c", "display/intel_display_power.c",
    "display/intel_dp.c", "gt/intel_lrc.c", "i915_pci.c", "i915_reg.h",
)
PATCHES = (
    "patches/0005-vlv-chv-dp-hdmi-audio-phase-linux-netbsd11.patch",
    "patches/0006-vlv-chv-display-error-irq-linux-netbsd11.patch",
    "patches/0007-i915-early-probe-resource-unwind-netbsd11.patch",
    "candidates/0008-i915-drm-registration-unwind-netbsd11.patch",
    "candidates/0009-netbsd-opregion-optional-asle-cleanup.patch",
    "candidates/0010-netbsd-opregion-rvda-map-failure-unwind.patch",
    "candidates/0011-i915-edp-reject-missing-fixed-mode-netbsd11.patch",
    "candidates/0012-i915-edp-dpcd-rates-failed-aux-read-netbsd11.patch",
    "candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch",
    "candidates/0016-i915-gen8-ppgtt-vm-init-error-unwind-netbsd11.patch",
    "candidates/0017-i915-gen6-ppgtt-vm-flush-error-unwind-netbsd11.patch",
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--overlay-tree", type=Path, required=True)
    p.add_argument("--objdir", type=Path, required=True)
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("builds are authorized only on HP/NetBSD")
    tree = a.netbsd_tree.resolve(strict=True)
    obj = a.objdir.resolve(strict=True)
    overlay = a.overlay_tree.resolve(strict=True)
    workspace = tree.parent
    if (tree.name != "netbsd-native" or obj.parent != workspace or
            obj.name != "native-obj" or overlay.parent != workspace or
            not (workspace / "native-stage.status").read_text().startswith("DONE ")):
        p.error("expected the isolated HP source/object/overlay workspace")
    head = subprocess.check_output(["git", "-C", str(overlay), "rev-parse", "HEAD"], text=True).strip()
    diff = subprocess.check_output(["git", "-C", str(overlay), "diff", "--binary", "HEAD"])
    if head != NETBSD_PIN or sha(diff) != OVERLAY_SHA:
        p.error("overlay revision or six-file diff changed; reconcile first")
    report = obj / "i915-backport-objects-status.json"
    state = {"state": "RUNNING", "host": socket.gethostname(),
             "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "reference": NETBSD_PIN, "overlay_sha256": OVERLAY_SHA,
             "commands": [], "patch_sha256": {}, "source_sha256": {}}
    def save():
        state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        temporary = report.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(report)
    def run(command):
        state["commands"].append(command)
        save()
        print("RUN", command, flush=True)
        subprocess.run(command, check=True)
    save()
    try:
        paths = {DIRECTORY / name for name in OVERLAY_FILES}
        for name in PATCHES:
            patch = ROOT / name
            data = patch.read_bytes()
            state["patch_sha256"][name] = sha(data)
            for path in re.findall(r"^\+\+\+ b/(\S+)$", data.decode("utf-8"), re.M):
                relative = Path(path)
                if relative.is_absolute() or ".." in relative.parts or DIRECTORY not in relative.parents:
                    raise RuntimeError("patch outside i915 scope: " + path)
                paths.add(relative)
        originals = {}
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            for relative in sorted(paths):
                original = subprocess.check_output(["git", "-C", str(overlay), "show", "HEAD:" + relative.as_posix()])
                originals[relative] = original
                destination = scratch / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((overlay / relative).read_bytes())
            for name in PATCHES:
                run(["git", "-C", str(scratch), "apply", "--check", str(ROOT / name)])
                run(["git", "-C", str(scratch), "apply", str(ROOT / name)])
            revised = {relative: (scratch / relative).read_bytes() for relative in paths}
        # Verify all destinations before changing any file. A repeated check
        # accepts only the same complete stack, never another dirty overlay.
        for relative in paths:
            if (tree / relative).read_bytes() not in (originals[relative], revised[relative]):
                raise RuntimeError("unexpected native source: " + relative.as_posix())
        for relative in sorted(paths):
            destination = tree / relative
            temporary = destination.with_suffix(destination.suffix + ".hp-stage")
            temporary.write_bytes(revised[relative])
            temporary.replace(destination)
            state["source_sha256"][relative.as_posix()] = sha(destination.read_bytes())
        units = sorted(relative for relative in paths if relative.suffix == ".c")
        if len(units) != 11 or len({relative.stem for relative in units}) != 11:
            raise RuntimeError("unexpected object scope; inventory before build")
        makefile = (obj / "Makefile").read_text()
        if any(relative.name not in makefile for relative in units):
            raise RuntimeError("configured kernel omits an affected i915 unit")
        wrapper = workspace / "native-tools/bin/nbmake-amd64"
        if str(tree) not in wrapper.read_text() or str(obj) not in wrapper.read_text():
            raise RuntimeError("make wrapper points outside the isolated stage")
        state["units"] = [relative.as_posix() for relative in units]
        run([str(wrapper), "-C", str(obj), "-j2", *[relative.stem + ".d" for relative in units]])
        run([str(wrapper), "-C", str(obj), "-j2", *[relative.stem + ".o" for relative in units]])
        state["artifacts"] = {}
        for relative in units:
            artifact = obj / (relative.stem + ".o")
            data = artifact.read_bytes()
            if not data:
                raise RuntimeError("empty native object: " + artifact.name)
            state["artifacts"][artifact.name] = {"bytes": len(data), "sha256": sha(data)}
        state["state"] = "PASSED"
        state["limitation"] = "bounded NetBSD backport objects; full Linux i915/DRM/TTM and hardware acceptance remain open"
    except Exception as error:
        state["state"] = "FAILED"
        state["error"] = str(error)
        save()
        raise
    save()
    print("HP_I915_BACKPORT_11_OBJECTS_PASS", flush=True)

if __name__ == "__main__":
    main()
