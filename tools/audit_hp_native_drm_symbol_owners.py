#!/usr/bin/env python3
"""Audit missing symbols after the three-object native DRM partial link on HP.

Read-only source and ELF inspection. The report identifies actual native
object providers and candidate C source definitions. Text matches remain
candidates; they are not proof of ABI or functional DRM/KMS integration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
# Stage, linked object and provider objects are selected explicitly by
# the HP owner; an obsolete build workspace is never silently assumed.


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(args: list[str]) -> list[str]:
    p = subprocess.run(args, text=True, capture_output=True, timeout=80)
    if p.returncode != 0:
        raise RuntimeError("native symbol reader failed: " + p.stderr[-800:])
    return p.stdout.splitlines()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--stage-root", type=Path, required=True,
                    help="verified HP tree containing native sources and nm")
    ap.add_argument("--linked-object", type=Path, required=True,
                    help="actual three-object NetBSD ld -r output to inspect")
    ap.add_argument("--provider-dir", type=Path, action="append", required=True,
                    help="directory of previously compiled native .o files; repeatable")
    args = ap.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        ap.error("native binary inspection is on HP NetBSD only")
    if os.geteuid() == 0:
        ap.error("non-root workspace only")
    out = args.output.resolve()
    if (out.exists() or out.parent != WORK.resolve() or
            not out.name.startswith("i915-drm-owners-")):
        ap.error("create a new i915-drm-owners-* report beside checkouts")
    stage = args.stage_root.resolve(strict=True)
    native = stage / "netbsd-full-linux/sys/external/bsd/drm2"
    nm = stage / "full-linux-tools/bin/x86_64--netbsd-nm"
    src = args.linked_object.resolve(strict=True)
    directories = [item.resolve(strict=True) for item in args.provider_dir]
    if (not stage.is_dir() or not native.is_dir() or not nm.is_file() or
            not os.access(nm, os.X_OK) or not src.is_file() or
            src.suffix != ".o" or WORK.resolve() not in src.parents):
        ap.error("HP source, native nm or owner linked object missing/invalid")
    if any(not p.is_dir() or (stage not in p.parents and
               WORK.resolve() not in p.parents and p != stage)
           for p in directories):
        ap.error("provider directories must be under explicit stage or owner workspace")

    undefined = set()
    for line in symbols([str(nm), "-u", str(src)]):
        m = re.search(r"\bU\s+([A-Za-z_][\w.$@]*)\s*$", line)
        if m:
            undefined.add(m.group(1))

    objects = sorted({obj for p in directories for obj in p.glob("*.o")
                      if obj.is_file()})
    if not objects:
        ap.error("no native provider objects found in selected directories")
    definitions: dict[str, list[str]] = {symbol: [] for symbol in undefined}
    for obj in objects:
        for line in symbols([str(nm), "-g", "--defined-only", str(obj)]):
            m = re.search(r"\b[TDBRWAVGC]\s+([A-Za-z_][\w.$@]*)\s*$", line)
            if m and m.group(1) in definitions:
                definitions[m.group(1)].append(str(obj))

    candidates: dict[str, list[str]] = {symbol: [] for symbol in undefined}
    all_c = sorted(native.rglob("*.c"))
    for c in all_c:
        code = c.read_text(errors="replace")
        present = [sym for sym in undefined if sym in code]
        for sym in present:
            # This is a C-text source owner candidate only, not an
            # executable/linked symbol guarantee: macro effects and conditional
            # compilation are deliberately not guessed away.
            pattern = r"(?m)^[A-Za-z_][\w\s*]*(?:\*\s*)?\b" + re.escape(sym) + r"\s*\([^;{}]{0,1000}\)\s*\{"
            if re.search(pattern, code):
                candidates[sym].append(str(c.relative_to(native)))
    out.mkdir(mode=0o700)
    report = {
        "state": "SOURCE_OWNER_CANDIDATE_AUDIT_COMPLETE",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "source_stage_root": str(stage),
        "linked_object": str(src),
        "native_nm": str(nm),
        "provider_directories": [str(p) for p in directories],
        "relocatable_object_sha256": digest(src),
        "undefined_symbol_count": len(undefined),
        "existing_object_files_checked": len(objects),
        "drm_source_C_files_checked": len(all_c),
        "defined_by_existing_objects": {
            k: v for k, v in sorted(definitions.items()) if v
        },
        "drm_source_definition_candidates": {
            k: v for k, v in sorted(candidates.items()) if v
        },
        "not_defined_in_scanned_existing_objects": sorted(
            k for k, v in definitions.items() if not v
        ),
        "no_obvious_drm_source_definition": sorted(
            k for k, v in candidates.items() if not v
        ),
        "limitations": (
            "This maps unresolved imports of only three partially linked "
            "objects, not the final full i915/DRM/TTM kernel link. Regex-only "
            "C definition candidates require review, and complete system "
            "kernel providers are outside the DRM source-only candidate index."
        ),
    }
    (out / "status.json").write_text(json.dumps(report, indent=2) + "\n")
    print("HP_I915_DRM_UNRESOLVED", len(undefined),
          "OBJECT_PROVIDERS", len(report["defined_by_existing_objects"]),
          "SOURCE_CANDIDATES", len(report["drm_source_definition_candidates"]),
          "REPORT", out, flush=True)
    for sym in ("drm_minor_acquire", "drm_guarantee_initialized",
                "drm_ioctl", "linux_pid_system_init",
                "linux_file_native_view"):
        print("SYMBOL", sym,
              "obj", report["defined_by_existing_objects"].get(sym, []),
              "source", report["drm_source_definition_candidates"].get(sym, []),
              flush=True)


if __name__ == "__main__":
    main()
