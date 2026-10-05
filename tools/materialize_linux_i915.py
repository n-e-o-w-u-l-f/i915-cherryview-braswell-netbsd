#!/usr/bin/env python3
"""Materialize the pinned Linux i915 + DRM dependency source set.

This tool does not mutate a NetBSD source tree.  It creates a reproducible
staging tree and manifest that can then be consumed by NetBSD's canonical
DRM import tooling.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"

COPY_PATHS = (
    "drivers/gpu/drm/i915",
    "drivers/gpu/drm/display",
    "drivers/gpu/drm/ttm",
    "include/drm",
    "include/uapi/drm",
)

TOP_LEVEL_DRM_PATTERNS = ("*.c", "*.h", "Makefile", "Kconfig")


def git_head(tree: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True
        )
        return p.stdout.strip()
    except Exception:
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_path(src_root: Path, dst_root: Path, rel: str) -> None:
    src = src_root / rel
    dst = dst_root / rel
    if not src.exists():
        raise FileNotFoundError(rel)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_top_level_drm(src_root: Path, dst_root: Path) -> None:
    src = src_root / "drivers/gpu/drm"
    dst = dst_root / "drivers/gpu/drm"
    dst.mkdir(parents=True, exist_ok=True)
    for pattern in TOP_LEVEL_DRM_PATTERNS:
        for item in src.glob(pattern):
            if item.is_file():
                shutil.copy2(item, dst / item.name)


def verify_netbsd_tools(netbsd: Path) -> dict[str, bool]:
    paths = {
        "prepare_import": netbsd / "sys/external/bsd/drm2/prepare-import.sh",
        "drm2netbsd": netbsd / "sys/external/bsd/drm2/drm/drm2netbsd",
        "i915drmkms2netbsd":
            netbsd / "sys/external/bsd/drm2/i915drm/i915drmkms2netbsd",
    }
    return {name: path.is_file() for name, path in paths.items()}


def verify_sources(linux: Path, head: str | None) -> dict[str, str] | None:
    """Verify the whole selected input before creating any output."""
    for rel in COPY_PATHS:
        if not (linux / rel).is_dir():
            raise SystemExit(f"missing reference directory {rel}; expand sparse checkout first")
    if head is None:
        return None  # Only the explicit unverified-input option can reach here.
    entries = subprocess.check_output(
        ["git", "-C", str(linux), "ls-tree", "-rz", "HEAD", "--", *COPY_PATHS]
    ).split(b"\0")
    top = subprocess.check_output(
        ["git", "-C", str(linux), "ls-tree", "-z", "HEAD:drivers/gpu/drm"]
    ).split(b"\0")
    for entry in top:
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        if metadata.split()[1] == b"blob" and any(
                fnmatch.fnmatch(name.decode(), pattern) for pattern in TOP_LEVEL_DRM_PATTERNS):
            entries.append(metadata + b"\tdrivers/gpu/drm/" + name)
    expected_files = {}
    for entry in entries:
        if not entry:
            continue
        metadata, relative = entry.split(b"\t", 1)
        mode, kind, expected = metadata.split()
        name = relative.decode()
        source = linux / name
        if kind != b"blob" or mode not in (b"100644", b"100755") or not source.is_file():
            raise SystemExit(f"missing or unsupported reference file {name}")
        data = source.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected.decode():
            raise SystemExit(f"dirty reference file {name}")
        expected_files[name] = expected.decode()
    dirty = subprocess.check_output(
        ["git", "-C", str(linux), "status", "--porcelain=v1", "--untracked-files=all", "--", *COPY_PATHS]
    )
    if dirty.strip():
        raise SystemExit("uncommitted files in selected reference paths")
    return expected_files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--netbsd-tree", type=Path)
    ap.add_argument("--allow-unverified-linux-head", action="store_true")
    args = ap.parse_args()

    linux = args.linux_tree.resolve()
    out = args.out.resolve()

    head = git_head(linux)
    if head != LINUX_PIN and not args.allow_unverified_linux_head:
        raise SystemExit(
            f"refusing Linux HEAD {head}; expected pinned {LINUX_PIN}"
        )

    if out.exists():
        raise SystemExit(f"output already exists; preserve/reconcile it and choose a new path: {out}")
    references = [linux]
    if args.netbsd_tree:
        references.append(args.netbsd_tree.resolve())
    if any(out == tree or tree in out.parents or out in tree.parents for tree in references):
        raise SystemExit("output overlaps a reference tree")
    expected_files = verify_sources(linux, head)
    out.mkdir(parents=True)

    for rel in COPY_PATHS:
        copy_path(linux, out, rel)
    copy_top_level_drm(linux, out)

    files = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        data = path.read_bytes()
        name = str(path.relative_to(out))
        if expected_files is not None:
            actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if expected_files.get(name) != actual:
                raise SystemExit(f"copied source differs from verified Git input: {name}")
        files.append({
            "path": name,
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    if expected_files is not None and {entry["path"] for entry in files} != set(expected_files):
        raise SystemExit("copied source set differs from verified Git input")

    manifest = {
        "linux_pin": LINUX_PIN,
        "linux_head_observed": head,
        "linux_head_verified": head == LINUX_PIN,
        "netbsd_pin": NETBSD_PIN,
        "i915_file_count": sum(
            1 for p in (out / "drivers/gpu/drm/i915").rglob("*")
            if p.is_file()
        ),
        "total_file_count": len(files),
        "files": files,
    }

    if args.netbsd_tree:
        netbsd = args.netbsd_tree.resolve()
        manifest["netbsd_head_observed"] = git_head(netbsd)
        manifest["netbsd_import_tools"] = verify_netbsd_tools(netbsd)

    (out / "PORT-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )

    print(json.dumps({
        "linux_pin": manifest["linux_pin"],
        "i915_file_count": manifest["i915_file_count"],
        "total_file_count": manifest["total_file_count"],
        "manifest": str(out / "PORT-MANIFEST.json"),
        "netbsd_import_tools": manifest.get("netbsd_import_tools"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
