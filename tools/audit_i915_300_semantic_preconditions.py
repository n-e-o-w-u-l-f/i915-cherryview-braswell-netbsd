#!/usr/bin/env python3
"""Audit all 300 *open* i915 source units against immutable Linux/NetBSD trees.

This checks source identity, target owner existence and selected objects,
candidate symbol overlap where frozen Linux text is locally available,
and records what full semantic work remains. Source discovery/regex matching
is NEVER a substitute for complete CHV reachability, API, DMA, IRQ,
power-sequence, error-unwind, ABI and hardware acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess

NETBSD_DIST = "sys/external/bsd/drm2/dist/drm/i915"
NETBSD_GLUE = "sys/external/bsd/drm2/i915drm"
LINUX_FROZEN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_FROZEN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_ROOT_NAMES = {
    "display/intel_backlight.c": "display/intel_panel.c",
    "display/intel_dp_aux.c": "display/intel_dp.c",
    "display/intel_pps.c": "display/intel_dp.c",
    "display/intel_display_power_well.c": "display/intel_display_power.c",
    "display/intel_vblank.c": "i915_irq.c",
    "display/vlv_sideband.c": "intel_sideband.c",
    "gt/intel_ggtt_fencing.c": "i915_gem_fence_reg.c",
}
REVIEW_GATES = (
    "linux_original_source_read",
    "chv_pci_reachability_verified",
    "all_chv_reachable_functions_reviewed",
    "native_drm_abi_and_type_contract_verified",
    "dma_gem_ttm_memory_lifetime_verified",
    "irq_lock_scheduling_context_verified",
    "pm_firmware_and_register_order_verified",
    "allocation_failure_and_detach_unwind_verified",
    "dependency_build_object_link_verified",
    "native_netbsd_compile_or_explicit_chv_inapplicability_verified",
)
FUNC = re.compile(
    r"(?ms)^[\t ]*(?:[A-Za-z_][\w\s\*\(\),\[\]<>]*?\s+)?"
    r"([a-z_][A-Za-z0-9_]*)\s*\((.{0,700}?)\)\s*\{"
)
BAN = {"if", "while", "for", "switch", "return", "sizeof", "typeof", "do"}


def need(cond: bool, message: str):
    if not cond:
        raise ValueError("I915_300_SOURCE_GATE_REFUSED: " + message)


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def funcs(text: str) -> list[str]:
    return sorted({
        m.group(1) for m in FUNC.finditer(text)
        if m.group(1) not in BAN
    })


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux-reference", type=Path, required=True)
    ap.add_argument("--netbsd-reference", type=Path, required=True)
    ap.add_argument("--blob-crosswalk", type=Path, required=True)
    ap.add_argument("--netbsd-root", type=Path, required=True)
    ap.add_argument("--linux-snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    x = ap.parse_args()
    l, n, w = (read_json(p) for p in (
        x.linux_reference, x.netbsd_reference, x.blob_crosswalk
    ))
    need(l["linux_pin"] == LINUX_FROZEN, "unexpected Linux frozen commit")
    need(n["netbsd_pin"] == NETBSD_FROZEN, "unexpected NetBSD frozen commit")
    need(w["linux_pin"] == LINUX_FROZEN and
         w["netbsd_pin"] == NETBSD_FROZEN, "crosswalk pin mismatch")
    need(l["unreviewed"] == 300 and len(l["rows"]) == 300, "not 300 rows")
    need(len(w["rows"]) == 300 and
         [v["linux_source"] for v in l["rows"]] ==
         [v["linux_source"] for v in w["rows"]],
         "crosswalk keys/order changed")
    need(n["c_source_count"] == 264, "NetBSD frozen C owner count changed")
    native = x.netbsd_root / NETBSD_DIST
    all_native = {}
    for f in n["files"]:
        candidate = native / f["path"]
        need(candidate.is_file() and not candidate.is_symlink(),
             "NetBSD source missing/symlink " + f["path"])
        data = candidate.read_bytes()
        need(blob(data) == f["blob"],
             "NetBSD frozen source SHA mismatch " + f["path"])
        if f["path"].endswith(".c"):
            all_native[f["path"]] = funcs(data.decode(errors="replace"))
    need(len(all_native) == 264, "native C source inventory drift")
    # Build owner selection is distinct from mere existence in tree.
    selected = set()
    for p in (
        x.netbsd_root / NETBSD_GLUE / "files.i915drmkms",
        x.netbsd_root / "sys/external/bsd/drm2/drm/files.drmkms",
    ):
        need(p.is_file(), "native build filelist absent")
        for line in p.read_text().splitlines():
            fields = line.strip().split()
            if fields and fields[0] == "file" and len(fields) >= 2:
                if fields[1].startswith("external/bsd/drm2/dist/drm/i915/"):
                    selected.add(fields[1].split("dist/drm/i915/", 1)[1])
    index = defaultdict(set)
    for rel, functions in all_native.items():
        for name in functions:
            index[name].add(rel)

    out = []
    summary = Counter()
    observed_linux = 0
    for lr, cr in zip(l["rows"], w["rows"]):
        rel = lr["linux_source"]
        need(rel == cr["linux_source"], "index mismatch")
        label = cr["pinned_source_status"]
        source_file = x.linux_snapshot / rel
        source_available = source_file.is_file() and not source_file.is_symlink()
        linux_functions = []
        matched_functions = []
        if source_available:
            raw = source_file.read_bytes()
            need(blob(raw) == lr["linux_blob"],
                 "available Linux original blob mismatch " + rel)
            linux_functions = funcs(raw.decode(errors="replace"))
            matched_functions = [fn for fn in linux_functions if fn in index]
            observed_linux += 1
        owner = LINUX_ROOT_NAMES.get(rel)
        if not owner:
            if lr["netbsd_evidence"].startswith("dist:"):
                owner = lr["netbsd_evidence"].split(":", 1)[1].split(",", 1)[0]
            elif lr["netbsd_evidence"].startswith("glue:"):
                owner = None
            elif cr["netbsd_same_path_blob"] is not None:
                owner = rel
        has_owner = owner in all_native if owner else False
        owner_selected = owner in selected if has_owner else False
        if label == "IDENTICAL_SOURCE_BLOB":
            need(cr["netbsd_same_path_blob"] == lr["linux_blob"],
                 "false claimed identical source")
        if label == "DIFFERENT_SOURCE_BLOB":
            need(cr["netbsd_same_path_blob"] != lr["linux_blob"],
                 "false claimed different source")
        summary[label] += 1
        if source_available:
            summary["LINUX_CONTENT_PINNED_AND_READ"] += 1
        if has_owner:
            summary["NATIVE_OWNER_SOURCE_PRESENT"] += 1
        if owner_selected:
            summary["OWNER_BUILD_SELECTED"] += 1
        # Every gate defaults to OPEN. Never auto-accept source-parity
        # from matching names; only immutable Linux original has evidence.
        gates = {g: "EVIDENCE_READ_NOT_SEMANTICALLY_REVIEWED"
                 if g == "linux_original_source_read" and source_available
                 else "OPEN" for g in REVIEW_GATES}
        out.append({
            "linux_source": rel,
            "linux_blob": lr["linux_blob"],
            "netbsd_same_path_blob": cr["netbsd_same_path_blob"],
            "source_identity": label,
            "netbsd_owner_candidate": owner,
            "netbsd_owner_present": has_owner,
            "netbsd_owner_build_selected": owner_selected,
            "linux_content_available_and_git_verified": source_available,
            "linux_candidate_function_count": len(linux_functions)
              if source_available else None,
            "native_candidate_function_name_matches": len(matched_functions)
              if source_available else None,
            "native_function_matches": matched_functions
              if source_available else [],
            "semantic_gates": gates,
            "semantic_state": "UNREVIEWED",
            "accepted_for_kernel": False,
        })
    need(len(out) == 300, "not all 300 checked")
    need(sum(a["semantic_state"] == "UNREVIEWED" for a in out) == 300,
         "false completion")
    result = {
        "schema": "hp-i915-300-semantic-preconditions/v1",
        "status": "PRECONDITION_INVENTORY_ONLY_NOT_SEMANTIC_ACCEPTANCE",
        "linux_pin": LINUX_FROZEN,
        "netbsd_pin": NETBSD_FROZEN,
        "total": 300,
        "native_c_blobs_pin_verified": 264,
        "linux_originals_content_verified": observed_linux,
        "summary": dict(sorted(summary.items())),
        "semantics_verified_and_accepted": 0,
        "rows": out,
        "caution": ("Every row remains open. This program verifies source "
                    "identity, native owner/selection and candidate names; "
                    "full per-function CHV control-flow, side effects, "
                    "ABI and failure-unwind comparison has not run on "
                    "missing Linux source content or HP hardware."),
    }
    x.out.parent.mkdir(parents=True, exist_ok=True)
    x.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "total": 300,
        "netbsd_c_blobs_verified": 264,
        "linux_source_read": observed_linux,
        "summary": result["summary"],
        "semantic_verified": result["semantics_verified_and_accepted"],
        "out": str(x.out),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
