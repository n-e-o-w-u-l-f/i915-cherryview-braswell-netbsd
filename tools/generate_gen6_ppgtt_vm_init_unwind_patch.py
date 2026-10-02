#!/usr/bin/env python3
"""Pinned NetBSD Gen6 PPGTT creation-failure VM/flush-mutex cleanup, 0017.

Gen6 creation initializes flush and pin mutexes before ppgtt_init(), which
calls i915_address_space_init() and allocates DRM-MM/VM-mutex state. All
subsequent error exits funnel through err_free, currently destroying only
pin_mutex before freeing the object. After the existing partial scratch/PD
unwind, also destroy flush and finalize the initialized VM. Match the
resource ownership order of the successful NetBSD cleanup path.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/gt/gen6_ppgtt.c"
OLD = ("err_free:\n\tmutex_destroy(&ppgtt->pin_mutex);\n"
       "\tkfree(ppgtt);\n\treturn ERR_PTR(err);\n")
NEW = ("err_free:\n\tmutex_destroy(&ppgtt->flush);\n"
       "\tmutex_destroy(&ppgtt->pin_mutex);\n"
       "\ti915_address_space_fini(&ppgtt->base.vm);\n"
       "\tkfree(ppgtt);\n\treturn ERR_PTR(err);\n")


def pinned_source(tree: Path) -> str:
    sha = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if sha != NETBSD_PIN:
        raise RuntimeError(f"unexpected frozen NetBSD revision: {sha}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True,
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("frozen Gen6 PPGTT source is dirty")
    return committed


def transform(src: str) -> str:
    start = src.index("struct i915_ppgtt *gen6_ppgtt_create(")
    function = src[start:]
    if function.count(OLD) != 1 or function.count(NEW) != 0:
        raise RuntimeError("Gen6 PPGTT error-path source anchor changed")
    before = function[:function.index(OLD)]
    markers = (
        "mutex_init(&ppgtt->flush);",
        "mutex_init(&ppgtt->pin_mutex);",
        "ppgtt_init(&ppgtt->base, gt);",
        "goto err_free;",
        "goto err_pd;",
        "goto err_scratch;",
        "err_scratch:",
        "err_pd:",
        "return &ppgtt->base;",
    )
    if any(m not in before for m in markers):
        raise RuntimeError("Gen6 PPGTT resource ownership changed")
    return src[:start] + function.replace(OLD, NEW, 1)


def generate(tree: Path, output: Path) -> None:
    before = pinned_source(tree)
    after = transform(before)
    patch = "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if patch.count("+\tmutex_destroy(&ppgtt->flush);") != 1 or \
       patch.count("+\ti915_address_space_fini(&ppgtt->base.vm);") != 1:
        raise RuntimeError("missing Gen6 partial-init cleanup")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patch)
    print("I915_GEN6_PPGTT_VM_UNWIND_GENERATOR_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
