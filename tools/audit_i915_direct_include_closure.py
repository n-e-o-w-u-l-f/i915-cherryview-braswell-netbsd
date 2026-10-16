#!/usr/bin/env python3
"""Read-only pinned i915 direct-include audit; NOT a semantic or ABI test."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
PREFIX = "external/bsd/drm2/dist/drm/i915/"
INCLUDE = re.compile(r'(?m)^\s*#\s*include\s*([<"])([^">]+)[">]')
SHARED_PREFIXES = ("linux/", "drm/", "uapi/")
NETBSD_DIRS = ("include", "dist/include", "dist/include/uapi",
               "dist/drm/i915", "i915drm")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def active_paths(filelist: Path) -> list[str]:
    rows = []
    for line in filelist.read_text().splitlines():
        fields = line.split()
        if (len(fields) != 3 or fields[0] != "file"
                or not fields[1].startswith(PREFIX)
                or fields[2] != "i915drmkms"):
            raise ValueError("unexpected pinned i915 filelist row: " + line)
        rel = fields[1][len(PREFIX):]
        path = Path(rel)
        if (path.is_absolute() or any(p in (".", "..") for p in path.parts)
                or path.suffix != ".c"):
            raise ValueError("unsafe C source path: " + rel)
        rows.append(rel)
    if len(rows) != len(set(rows)):
        raise ValueError("duplicate active i915 translation unit")
    return rows


def coverage_rows(path: Path) -> dict[str, str]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = {"linux_source", "structural_class", "netbsd_evidence",
                    "semantic_state"}
        if set(reader.fieldnames or ()) != expected:
            raise ValueError("unexpected structural-coverage table headers")
        result = {}
        for row in reader:
            name = row["linux_source"]
            if name in result:
                raise ValueError("duplicate structural coverage unit: " + name)
            result[name] = row["structural_class"]
    return result


def audit(filelist: Path, linux: Path, netbsd: Path, coverage: Path,
          expected_units: int = 323) -> dict:
    paths = active_paths(filelist)
    structural = coverage_rows(coverage)
    if len(paths) != expected_units or set(paths) != set(structural):
        raise ValueError("active/structural 323-unit closure mismatch")
    linux = linux.resolve(strict=True)
    netbsd = netbsd.resolve(strict=True)
    include_roots = [netbsd / d for d in NETBSD_DIRS]
    if not linux.is_dir() or not include_roots[0].is_dir():
        raise ValueError("incomplete reference include roots")
    usage = defaultdict(list)
    quoted = set()
    rows = []
    for rel in paths:
        unit = (linux / rel).resolve(strict=True)
        if not unit.is_relative_to(linux) or not unit.is_file():
            raise ValueError("Linux source resolves outside pinned stage: " + rel)
        body = unit.read_bytes()
        includes = set(INCLUDE.findall(body.decode("utf-8", errors="replace")))
        shared = sorted({name for _, name in includes
                         if name.startswith(SHARED_PREFIXES)})
        local = sorted({name for delim, name in includes
                        if delim == '"' and not name.startswith(SHARED_PREFIXES)})
        quoted.update(local)
        present = [name for name in shared
                   if any((root / name).is_file() for root in include_roots)]
        unmatched = [name for name in shared if name not in present]
        for name in shared:
            usage[name].append(rel)
        rows.append({
            "linux_source": rel,
            "linux_source_sha256": sha(body),
            "structural_class": structural[rel],
            "direct_shared_headers": shared,
            "exact_path_present_in_netbsd": present,
            "exact_path_unmatched_netbsd": unmatched,
            "quoted_local_headers": local,
            "semantic_parity": "UNVERIFIED",
        })
    matched = sorted(n for n in usage if any(
        (root / n).is_file() for root in include_roots))
    missing = sorted((n for n in usage if n not in matched),
                     key=lambda n: (-len(usage[n]), n))
    return {
        "schema": "i915-netbsd-direct-include-audit/v1",
        "reference_linux_pin_declared": LINUX_PIN,
        "reference_netbsd_pin_declared": NETBSD_PIN,
        "root_content_revision_verified": False,
        "filelist_sha256": sha(filelist.read_bytes()),
        "coverage_sha256": sha(coverage.read_bytes()),
        "summary": {
            "active_units": len(rows),
            "structural_classes": dict(sorted(Counter(
                row["structural_class"] for row in rows).items())),
            "unique_shared_direct_includes": len(usage),
            "netbsd_exact_header_matches": len(matched),
            "netbsd_exact_header_unmatched": len(missing),
            "units_with_unmatched_direct_include": sum(bool(
                row["exact_path_unmatched_netbsd"]) for row in rows),
            "unique_quoted_local_includes": len(quoted),
        },
        "unmatched_headers": [
            {"header": name, "user_count": len(usage[name]), "users": usage[name]}
            for name in missing
        ],
        "rows": rows,
        "limitations": (
            "Lexical direct #include only, even in inactive CPP branches. "
            "No transitive closure, Kconfig, semantic/API parity, ABI, "
            "symbol definitions, compile, kernel link, or DRM/KMS hardware "
            "acceptance. Missing exact header path in selected DRM roots "
            "does not imply a missing function. Pins are declared inputs, "
            "not verified git provenance of the materialized root."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--filelist", required=True, type=Path)
    p.add_argument("--linux-i915", required=True, type=Path)
    p.add_argument("--netbsd-drm2", required=True, type=Path)
    p.add_argument("--structural", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--expected-units", type=int, default=323)
    args = p.parse_args()
    report = audit(args.filelist, args.linux_i915, args.netbsd_drm2,
                   args.structural, args.expected_units)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "summary": report["summary"],
        "top_unmatched": [{"header": row["header"],
                           "user_count": row["user_count"]}
                          for row in report["unmatched_headers"][:15]],
        "report_sha256": sha(args.out.read_bytes())
    }, indent=2))


if __name__ == "__main__":
    main()
