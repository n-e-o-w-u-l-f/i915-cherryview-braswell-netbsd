#!/usr/bin/env python3
"""Conservatively classify structural i915 gaps by function overlap.

This tool does not claim semantic parity from matching function names. It
reduces the review queue into target-inapplicable, all-functions-present,
partial-overlap, and no-overlap candidates using frozen Linux/NetBSD trees.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

FUNC_RE = re.compile(
    r"(?ms)^[\t ]*(?:[A-Za-z_][\w\s\*\(\),\[\]<>]*?\s+)?"
    r"([a-z_][A-Za-z0-9_]*)\s*\((.{0,700}?)\)\s*\{"
)
FUNC_BAN = {"if", "for", "while", "switch", "return", "sizeof", "typeof", "do"}


def functions(text: str) -> list[str]:
    out: list[str] = []
    for match in FUNC_RE.finditer(text):
        name = match.group(1)
        if name not in FUNC_BAN and name not in out:
            out.append(name)
    return out


def inapplicable_sources(doc: Path) -> set[str]:
    text = doc.read_text(encoding="utf-8")
    marker = "## Classified implementation modules"
    if marker not in text:
        raise RuntimeError(f"missing classification section in {doc}")
    section = text.split(marker, 1)[1]
    tick = chr(96)
    result = set()
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("- " + tick) or not line.endswith(tick):
            continue
        item = line[3:-1]
        if item.endswith(".c") and "/" in item:
            result.add(item)
    if not result:
        raise RuntimeError(f"no classified .c paths in {doc}")
    return result


def netbsd_function_index(netbsd: Path) -> dict[str, set[str]]:
    roots = (
        netbsd / "sys/external/bsd/drm2/dist/drm/i915",
        netbsd / "sys/external/bsd/drm2/i915drm",
    )
    index: dict[str, set[str]] = {}
    base = netbsd / "sys/external/bsd/drm2"
    for root in roots:
        for path in root.rglob("*.c"):
            text = path.read_text(errors="ignore")
            rel = str(path.relative_to(base))
            for name in functions(text):
                index.setdefault(name, set()).add(rel)
    return index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--structural", type=Path, required=True)
    ap.add_argument("--linux-i915", type=Path, required=True)
    ap.add_argument("--netbsd-tree", type=Path, required=True)
    ap.add_argument("--inapplicable-doc", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    structural = json.loads(args.structural.read_text())
    inapp = inapplicable_sources(args.inapplicable_doc)
    index = netbsd_function_index(args.netbsd_tree)

    rows = []
    for row in structural["rows"]:
        if row["structural_class"] != "UNRESOLVED_NO_BASENAME":
            continue

        rel = row["linux_source"]
        source = args.linux_i915 / rel
        funcs = functions(source.read_text(errors="ignore"))
        hits = [name for name in funcs if name in index]

        if rel in inapp:
            cls = "REFERENCE_INAPPLICABLE_CHV"
        elif funcs and len(hits) == len(funcs):
            cls = "ALL_FUNCTIONS_PRESENT_ELSEWHERE"
        elif hits:
            cls = "PARTIAL_FUNCTION_OVERLAP"
        else:
            cls = "NO_FUNCTION_OVERLAP"

        evidence = {name: sorted(index[name]) for name in hits}
        rows.append({
            "linux_source": rel,
            "candidate_class": cls,
            "function_count": len(funcs),
            "matching_function_count": len(hits),
            "match_ratio": round(len(hits) / len(funcs), 3) if funcs else None,
            "matching_functions": hits,
            "netbsd_function_evidence": evidence,
        })

    summary = Counter(r["candidate_class"] for r in rows)
    result = {
        "schema": "neowulf-i915-semantic-candidates/v1",
        "linux_pin": structural["linux_pin"],
        "netbsd_pin": structural["netbsd_pin"],
        "unresolved_structural_input": len(rows),
        "summary": dict(sorted(summary.items())),
        "rows": rows,
        "warning": (
            "Function-name overlap is review evidence only. "
            "It never establishes semantic parity by itself."
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "unresolved_structural_input": len(rows),
        "summary": result["summary"],
        "output": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
