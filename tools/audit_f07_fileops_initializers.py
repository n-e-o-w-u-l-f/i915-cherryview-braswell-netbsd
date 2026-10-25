#!/usr/bin/env python3
"""Read-only census of direct NetBSD struct fileops initializers.

Run only against an independently available clean NetBSD/src checkout pinned
at PIN. This checks *initializer source shape*, not compile/link or field ABI.
Regex recognition is intentionally conservative and reports an incomplete
coverage warning for macro-expanded/array/attributed initializers.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
DRM_CDEVSW_SHA = "eba6fc5b25c6be53c8a51b0649f6c827c3b46d55"
DECL = re.compile(r"\bstruct\s+fileops\s+([A-Za-z_]\w*)\s*=\s*\{", re.M)
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def scan(text: str) -> list[tuple[str, bool, int]]:
    """Find ordinary named initializers and check their first actual token."""
    cleaned = COMMENT.sub(lambda m: "\n" * m.group().count("\n"), text)
    found = []
    for match in DECL.finditer(cleaned):
        rest = cleaned[match.end():].lstrip()
        found.append((match.group(1), rest.startswith("."),
                      cleaned.count("\n", 0, match.start()) + 1))
    return found


def git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(root), *args],
                       text=True, capture_output=True, timeout=90, check=False)
    if p.returncode:
        raise RuntimeError("git " + " ".join(args) + ": " + p.stderr.strip()[:350])
    return p.stdout.strip()


def census(root: Path) -> tuple[int, int, int]:
    if not (root / ".git").exists():
        raise ValueError("requires a real independent NetBSD Git checkout")
    if git(root, "rev-parse", "HEAD") != PIN:
        raise ValueError("wrong NetBSD source revision")
    if git(root, "status", "--porcelain=v1"):
        raise ValueError("NetBSD source tree is not clean")
    drm = root / "sys/external/bsd/drm2/drm/drm_cdevsw.c"
    if drm.is_symlink() or not drm.is_file():
        raise ValueError("missing pinned in-tree DRM source")
    if git(root, "hash-object", str(drm)) != DRM_CDEVSW_SHA:
        raise ValueError("in-tree DRM source blob mismatch")
    paths = git(root, "grep", "-l", "struct fileops", "--", "sys").splitlines()
    count = positional = 0
    for p in paths:
        path = root / p
        if not path.is_file() or path.is_symlink():
            raise ValueError("unsafe/unreadable source path " + p)
        for name, designated, line in scan(path.read_text(encoding="utf-8", errors="replace")):
            count += 1
            if not designated:
                positional += 1
            print(f"{'DESIGNATED' if designated else 'REVIEW_POSITIONAL'} {p}:{line} {name}")
    print(f"F07_FILEOPS_CENSUS scanned={len(paths)} initializers={count} positional={positional}")
    print("LIMITATION: ordinary direct named initializers only; macro/array/attribute and selected module ABI unresolved")
    return len(paths), count, positional


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--netbsd-root", required=True, type=Path)
    args = ap.parse_args()
    try:
        _, _, bad = census(args.netbsd_root.resolve())
        return int(bad != 0)
    except (ValueError, RuntimeError, OSError) as e:
        print("F07_FILEOPS_GATE_BLOCKED:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
