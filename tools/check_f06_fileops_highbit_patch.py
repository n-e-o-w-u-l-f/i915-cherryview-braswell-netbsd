#!/usr/bin/env python3
"""Dry-run *only* the F06 pinned NetBSD-11 FILE/DRM ABI candidate.

This tool NEVER applies a patch, builds a kernel, or changes a boot target.
Run against a separate exact pristine NetBSD/src checkout, NOT a live HP
kernel tree. The earlier HP F02 denied diagnostic remains out of scope.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

PINNED_NETBSD = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
FILE_BLOBS = {
    "sys/sys/file.h": "4938650485c3d6acf892a846b2f330d1fc53c424",
    "sys/sys/filedesc.h": "e94f711b756ef0a6e01a4f682e8ba70928058ea7",
    "sys/kern/kern_descrip.c": "56f87d84b4f3a077710f08f0bfd14708983a39a6",
    "sys/kern/sys_generic.c": "0894053933da09868b6ff80d34e00ddfca7cf96b",
}
PATCH = (
    Path(__file__).resolve().parents[1]
    / "patches/candidates/netbsd-11-drm-fileops-bridge-copyout-owned-highbit-guard-20261025.patch"
)


def run(*command: str) -> str:
    process = subprocess.run(
        command, text=True, capture_output=True, timeout=60, check=False
    )
    if process.returncode:
        raise RuntimeError(
            f"{command[0]} failed (exit {process.returncode}): "
            + (process.stderr or process.stdout).strip()[:800]
        )
    return process.stdout.strip()


def validate(root: Path, patch: Path) -> None:
    if not root.is_dir() or not (root / ".git").exists():
        raise ValueError("requires an existing independent NetBSD Git checkout")
    if not patch.is_file() or patch.is_symlink():
        raise ValueError("candidate patch must be a normal file")
    head = run("git", "-C", str(root), "rev-parse", "HEAD")
    if head != PINNED_NETBSD:
        raise ValueError("wrong NetBSD source pin: " + head)
    for path, blob in FILE_BLOBS.items():
        source_file = root / path
        if not source_file.is_file() or source_file.is_symlink():
            raise ValueError("missing or symlink NetBSD input: " + path)
        actual = run("git", "-C", str(root), "hash-object", str(source_file))
        if actual != blob:
            raise ValueError(f"modified or wrong NetBSD file {path}: {actual}")

    if run("git", "-C", str(root), "status", "--porcelain=v1"):
        raise ValueError("NetBSD checkout must be clean for reproducible gate")

    expected_sha = "2fca0c1dc147e595fe2e83c3f7e57f0306773199"
    if run("git", "hash-object", str(patch)) != expected_sha:
        raise ValueError("wrong or changed F06 patch Git blob")
    data = patch.read_text(encoding="utf-8")
    if not data.endswith("\n") or data.startswith("#"):
        raise ValueError("not a plain newline-terminated unified diff")
    headers = [
        line.split(" b/", 1)[0].removeprefix("diff --git a/")
        for line in data.splitlines()
        if line.startswith("diff --git a/")
    ]
    if headers != list(FILE_BLOBS):
        raise ValueError(f"unexpected changed paths or order: {headers!r}")
    if data.count("@@ -") != 6:
        raise ValueError("expected exactly six source hunks")

    run("git", "-C", str(root), "apply", "--check",
        "--whitespace=error", str(patch))
    counts = run("git", "-C", str(root), "apply", "--numstat", str(patch))
    lines = counts.splitlines()
    if len(lines) != 4 or sorted(line.split("\t")[-1] for line in lines) != sorted(FILE_BLOBS):
        raise ValueError("patch's changed-file set drifted")
    print("F06_NETBSD11_FILEOPS_PATCH_DRY_RUN_PASS 4_FILES_6_HUNKS")
    print(counts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netbsd-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, default=PATCH)
    args = parser.parse_args()
    try:
        validate(args.netbsd_root.resolve(), args.patch.resolve())
    except (ValueError, RuntimeError, OSError) as exc:
        print("F06_NETBSD11_FILEOPS_PATCH_GATE_FAIL", str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
