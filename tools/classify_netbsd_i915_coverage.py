#!/usr/bin/env python3
"""Classify pinned Linux i915 active units against the NetBSD i915 build.

This is a structural coverage classifier, not a semantic parity validator.
It deliberately leaves unmatched or merely-present files unresolved.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def linux_active_sources(filelist: Path) -> list[str]:
    sources = []
    for raw in filelist.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        path = fields[1]
        marker = "external/bsd/drm2/dist/drm/i915/"
        if marker not in path:
            raise RuntimeError(f"unexpected Linux filelist path: {path}")
        sources.append(path.split(marker, 1)[1])
    return sources


def netbsd_active_sources(netbsd: Path) -> tuple[set[str], dict[str, list[dict]]]:
    files = netbsd / "sys/external/bsd/drm2/i915drm/files.i915drmkms"
    exact_dist: set[str] = set()
    by_basename: dict[str, list[dict]] = {}
    for raw in files.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("file\t"):
            continue
        path = line.split()[1]
        if "/i915/" in path:
            rel = path.split("/i915/", 1)[1]
            exact_dist.add(rel)
            kind = "dist"
        elif "/i915drm/" in path:
            rel = path.split("/i915drm/", 1)[1]
            kind = "glue"
        else:
            continue
        by_basename.setdefault(Path(rel).name, []).append({
            "kind": kind,
            "path": rel,
        })
    return exact_dist, by_basename


def present_sources(netbsd: Path) -> dict[str, list[dict]]:
    roots = (
        ("dist", netbsd / "sys/external/bsd/drm2/dist/drm/i915"),
        ("glue", netbsd / "sys/external/bsd/drm2/i915drm"),
    )
    present: dict[str, list[dict]] = {}
    for kind, root in roots:
        for path in root.rglob("*.c"):
            rel = str(path.relative_to(root))
            present.setdefault(path.name, []).append({
                "kind": kind,
                "path": rel,
            })
    return present


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux-filelist", type=Path, required=True)
    ap.add_argument("--netbsd-tree", type=Path, required=True)
    ap.add_argument("--linux-pin", required=True)
    ap.add_argument("--netbsd-pin", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    active = linux_active_sources(args.linux_filelist)
    exact, built_by_base = netbsd_active_sources(args.netbsd_tree)
    present = present_sources(args.netbsd_tree)

    rows = []
    for rel in active:
        name = Path(rel).name
        if rel in exact:
            cls = "EXACT_ACTIVE_DIST"
            evidence = [{"kind": "dist", "path": rel}]
        elif name in built_by_base:
            cls = "ACTIVE_OVERRIDE_OR_MOVED"
            evidence = built_by_base[name]
        elif name in present:
            cls = "PRESENT_NOT_BUILT"
            evidence = present[name]
        else:
            cls = "UNRESOLVED_NO_BASENAME"
            evidence = []

        rows.append({
            "linux_source": rel,
            "structural_class": cls,
            "netbsd_evidence": evidence,
            "semantic_state": "UNREVIEWED",
        })

    summary = Counter(row["structural_class"] for row in rows)
    result = {
        "schema": "neowulf-i915-structural-coverage/v1",
        "linux_pin": args.linux_pin,
        "netbsd_pin": args.netbsd_pin,
        "linux_active_count": len(active),
        "summary": dict(sorted(summary.items())),
        "rows": rows,
        "warning": (
            "Structural presence is not parity. Each row still requires "
            "semantic/lifecycle/API review before PORTED/ADAPTED/"
            "REFERENCE-INAPPLICABLE classification."
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "linux_active_count": len(active),
        "summary": result["summary"],
        "output": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
