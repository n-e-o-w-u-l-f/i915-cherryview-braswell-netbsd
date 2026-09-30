#!/usr/bin/env python3
"""Generate NetBSD files.i915drmkms entries from pinned Linux i915 Makefile."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"

CONFIG = {
    "CONFIG_ACPI": "y",
    "CONFIG_COMPAT": "y",
    "CONFIG_PERF_EVENTS": "y",
    "CONFIG_X86": "y",
    "CONFIG_HWMON": "y",
    "CONFIG_DRM_I915_PXP": "y",
    "CONFIG_DRM_I915_CAPTURE_ERROR": "y",
    "CONFIG_DRM_I915": "y",
    "CONFIG_DRM_FBDEV_EMULATION": "y",
}


def git_head(tree: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True
        )
        return p.stdout.strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--make", default=None,
        help="GNU make executable; auto-detects gmake then make")
    ap.add_argument("--allow-unverified-linux-head", action="store_true")
    args = ap.parse_args()

    linux = args.linux_tree.resolve()
    i915 = linux / "drivers/gpu/drm/i915"
    if not (i915 / "Makefile").is_file():
        raise SystemExit(f"missing {i915 / 'Makefile'}")

    head = git_head(linux)
    if head and head != LINUX_PIN and not args.allow_unverified_linux_head:
        raise SystemExit(
            f"refusing Linux HEAD {head}; expected pinned {LINUX_PIN}"
        )

    make = args.make or shutil.which("gmake") or shutil.which("make")
    if not make:
        raise SystemExit("GNU make not found")

    wrapper = """show-i915-y:
\t@printf '%s\\n' $(i915-y)
include Makefile
"""
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="i915-make-", delete=False
    ) as tf:
        tf.write(wrapper)
        wrapper_path = Path(tf.name)

    env = os.environ.copy()
    env.update(CONFIG)
    env["src"] = "."

    try:
        p = subprocess.run(
            [make, "-s", "-f", str(wrapper_path), "show-i915-y"],
            cwd=i915, env=env, text=True, capture_output=True
        )
    finally:
        wrapper_path.unlink(missing_ok=True)

    if p.returncode != 0:
        raise SystemExit(
            f"make failed rc={p.returncode}\n{p.stdout}\n{p.stderr}"
        )

    objects = sorted(set(x for x in p.stdout.split() if x.endswith(".o")))
    sources = [x[:-2] + ".c" for x in objects]

    missing = [x for x in sources if not (i915 / x).is_file()]
    if missing:
        raise SystemExit("active source files missing: " + ", ".join(missing))

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(
        f"file\texternal/bsd/drm2/dist/drm/i915/{src}\ti915drmkms\n"
        for src in sources
    ))

    meta = {
        "linux_pin": LINUX_PIN,
        "linux_head_observed": head,
        "make": make,
        "config": CONFIG,
        "active_object_count": len(objects),
        "active_source_count": len(sources),
        "sources": sources,
    }
    meta_path = out.with_suffix(out.suffix + ".json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    print(json.dumps({
        "active_source_count": len(sources),
        "output": str(out),
        "metadata": str(meta_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
