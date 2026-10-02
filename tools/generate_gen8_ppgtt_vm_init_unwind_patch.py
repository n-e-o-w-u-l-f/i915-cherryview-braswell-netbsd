#!/usr/bin/env python3
"""Generate candidate 0016 from pinned NetBSD Gen8 PPGTT init error paths.

ppgtt_init() calls i915_address_space_init(), which initializes drm_mm and
vm->mutex. The existing gen8_ppgtt_create() error labels release DMA pages,
scratch and the ppgtt object but omit i915_address_space_fini(). The normal
successful path eventually calls cleanup plus fini through i915_vm_release().
The error path cannot use that deferred release because vm.cleanup is only
installed on success; call fini synchronously after partial DMA cleanup.

The patch is limited to the failed initialization of NetBSD's imported Gen8
PPGTT code. It does not change hardware registers, the successful path, or
the original preserved Legion worktree.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/gt/gen8_ppgtt.c"
OLD = "err_free:\n\tkfree(ppgtt);\n\treturn ERR_PTR(err);\n"
NEW = ("err_free:\n\ti915_address_space_fini(&ppgtt->vm);\n"
       "\tkfree(ppgtt);\n\treturn ERR_PTR(err);\n")


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError(f"wrong frozen NetBSD revision: {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True,
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("frozen gen8_ppgtt.c source is dirty")
    return committed


def transform(original: str) -> str:
    start = original.index("struct i915_ppgtt *gen8_ppgtt_create(")
    section = original[start:]
    if section.count(OLD) != 1 or section.count(NEW) != 0:
        raise RuntimeError("gen8_ppgtt_create error label changed")
    before_error = section[:section.index(OLD)]
    checks = (
        "ppgtt_init(ppgtt, gt);",
        "err = gen8_init_scratch(&ppgtt->vm);",
        "goto err_free;",
        "goto err_free_scratch;",
        "goto err_free_pd;",
        "ppgtt->vm.cleanup = gen8_ppgtt_cleanup;",
        "err_free_pd:",
        "err_free_scratch:",
    )
    if any(term not in before_error for term in checks):
        raise RuntimeError("Gen8 PPGTT initialization or cleanup order changed")
    return original[:start] + section.replace(OLD, NEW, 1)


def generate(tree: Path, output: Path) -> None:
    original = pinned_source(tree)
    revised = transform(original)
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        revised.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if diff.count("+\ti915_address_space_fini(&ppgtt->vm);\n") != 1:
        raise RuntimeError("missing or duplicated VM-finalization fix")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(diff)
    print("I915_GEN8_PPGTT_VM_UNWIND_GENERATOR_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
