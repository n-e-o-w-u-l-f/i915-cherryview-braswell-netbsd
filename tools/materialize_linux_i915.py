#!/usr/bin/env python3
"""Materialize the pinned Linux i915 + DRM dependency source set.

This tool does not mutate a NetBSD source tree.  It creates a reproducible
staging tree and manifest that can then be consumed by NetBSD's canonical
DRM import tooling.
"""

from __future__ import annotations

import argparse
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
    if head and head != LINUX_PIN and not args.allow_unverified_linux_head:
        raise SystemExit(
            f"refusing Linux HEAD {head}; expected pinned {LINUX_PIN}"
        )

    required = linux / "drivers/gpu/drm/i915"
    if not required.is_dir():
        raise SystemExit(f"missing {required}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for rel in COPY_PATHS:
        copy_path(linux, out, rel)
    copy_top_level_drm(linux, out)

    files = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        files.append({
            "path": str(path.relative_to(out)),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })

    manifest = {
        "linux_pin": LINUX_PIN,
        "linux_head_observed": head,
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
