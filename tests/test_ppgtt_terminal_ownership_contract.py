#!/usr/bin/env python3
"""Pinned NetBSD PPGTT creation-error vs successful VM terminal ownership.

Candidates 0016/0017 add direct VM finalization at the *creation error*
labels, before freeing the not-yet-published PPGTT. The *successful*
PPGTT follows vm->cleanup -> i915_address_space_fini -> kfree through
__i915_vm_release(), scheduled only after i915_vm_put. This regression
locks the two disjoint lifetimes and the scratch partial-failure
ownership without treating an isolated host-C test as native build proof.

All source inputs must match pinned NetBSD exactly. An optional real
six-edit overlay may differ elsewhere but must carry unmodified Gen6/
Gen8 PPGTT and VM teardown sources before applying candidates 0016/17.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
G6 = runpy.run_path(str(ROOT / "tools/generate_gen6_ppgtt_vm_init_unwind_patch.py"))
G8 = runpy.run_path(str(ROOT / "tools/generate_gen8_ppgtt_vm_init_unwind_patch.py"))
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
PREFIX = "sys/external/bsd/drm2/dist/drm/i915/gt/"
VM = PREFIX + "intel_gtt.c"
PPGTT = PREFIX + "intel_ppgtt.c"


def pinned(tree: Path, relative: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != PIN:
        raise RuntimeError(f"wrong NetBSD source revision: {head}")
    source = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative],
        text=True,
    )
    if (tree / relative).read_text() != source:
        raise RuntimeError(f"dirty/missing pinned file: {relative}")
    return source


def unique_function(source: str, start: str, stop: str) -> str:
    if source.count(start) != 1:
        raise AssertionError("missing/ambiguous function start: " + start)
    begin = source.index(start)
    end = source.find(stop, begin + len(start))
    if end < 0:
        raise AssertionError("missing function end after: " + start)
    return source[begin:end]


def ordered(src: str, *markers: str) -> None:
    positions = [src.index(marker) for marker in markers]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise AssertionError("PPGTT lifecycle resource order changed: " +
                             ", ".join(markers))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path)
    args = parser.parse_args()

    gen8 = G8["pinned_source"](args.netbsd_tree)
    gen6 = G6["pinned_source"](args.netbsd_tree)
    vm = pinned(args.netbsd_tree, VM)
    init = pinned(args.netbsd_tree, PPGTT)
    if args.overlay_tree is not None:
        overlay = args.overlay_tree.resolve(strict=True)
        if overlay == args.netbsd_tree.resolve():
            raise RuntimeError("overlay must be a distinct NetBSD worktree")
        head = subprocess.check_output(
            ["git", "-C", str(overlay), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        if head != PIN:
            raise RuntimeError("overlay NetBSD base mismatch")
        for name, expected in (
            (G8["REL"], gen8), (G6["REL"], gen6),
            (VM, vm), (PPGTT, init),
        ):
            if (overlay / name).read_text() != expected:
                raise AssertionError(
                    "genuine overlay changed PPGTT lifecycle contract: " + name
                )

    vm_init = unique_function(vm, "void i915_address_space_init(",
                              "void clear_pages(")
    vm_fini = unique_function(vm, "void i915_address_space_fini(",
                              "static void __i915_vm_release(")
    vm_release = unique_function(vm, "static void __i915_vm_release(",
                                 "void i915_vm_release(")
    ref_release = unique_function(vm, "void i915_vm_release(",
                                  "void i915_address_space_init(")
    assert "mutex_init(&vm->mutex);" in vm_init
    assert "drm_mm_init(&vm->mm, 0, vm->total);" in vm_init
    ordered(vm_fini, "drm_mm_takedown(&vm->mm);",
            "mutex_destroy(&vm->mutex);")
    ordered(vm_release, "vm->cleanup(vm);",
            "i915_address_space_fini(vm);", "kfree(vm);")
    assert vm_release.count("i915_address_space_fini(vm);") == 1
    assert ref_release.count("queue_rcu_work(vm->i915->wq, &vm->rcu);") == 1

    init_ppgtt = unique_function(init, "void ppgtt_init(", "\n}\n")
    assert "i915_address_space_init(&ppgtt->vm, VM_CLASS_PPGTT);" in init_ppgtt

    original_8 = unique_function(gen8, "struct i915_ppgtt *gen8_ppgtt_create(",
                                 "\n}\n")
    modified_8 = unique_function(
        G8["transform"](gen8), "struct i915_ppgtt *gen8_ppgtt_create(",
        "\n}\n",
    )
    original_6 = unique_function(gen6, "struct i915_ppgtt *gen6_ppgtt_create(",
                                 "\n}\n")
    modified_6 = unique_function(
        G6["transform"](gen6), "struct i915_ppgtt *gen6_ppgtt_create(",
        "\n}\n",
    )
    ordered(original_8, "ppgtt_init(ppgtt, gt);",
            "err = gen8_init_scratch(&ppgtt->vm);",
            "ppgtt->vm.cleanup = gen8_ppgtt_cleanup;",
            "return ppgtt;", "err_free_pd:\n")
    ordered(modified_8, "err_free_pd:\n", "err_free_scratch:\n",
            "err_free:\n", "i915_address_space_fini(&ppgtt->vm);",
            "kfree(ppgtt);")
    assert modified_8.count("i915_address_space_fini(&ppgtt->vm);") == 1
    assert original_8.count("i915_address_space_fini(&ppgtt->vm);") == 0
    assert "i915_vm_put(" not in modified_8

    ordered(original_6, "mutex_init(&ppgtt->flush);",
            "mutex_init(&ppgtt->pin_mutex);",
            "ppgtt_init(&ppgtt->base, gt);",
            "ppgtt->base.vm.cleanup = gen6_ppgtt_cleanup;",
            "return &ppgtt->base;", "err_scratch:\n")
    ordered(modified_6, "err_scratch:\n", "err_pd:\n",
            "err_free:\n", "mutex_destroy(&ppgtt->flush);",
            "mutex_destroy(&ppgtt->pin_mutex);",
            "i915_address_space_fini(&ppgtt->base.vm);", "kfree(ppgtt);")
    assert modified_6.count("i915_address_space_fini(&ppgtt->base.vm);") == 1
    assert original_6.count("i915_address_space_fini(&ppgtt->base.vm);") == 0
    assert "i915_vm_put(" not in modified_6

    cleanup8 = unique_function(gen8, "static void gen8_ppgtt_cleanup(",
                               "static u64 __gen8_ppgtt_clear(")
    cleanup6 = unique_function(gen6, "static void gen6_ppgtt_cleanup(",
                               "static int pd_vma_set_pages(")
    ordered(cleanup8, "__gen8_ppgtt_cleanup(", "free_scratch(vm);")
    ordered(cleanup6, "gen6_ppgtt_free_pd(ppgtt);", "free_scratch(vm);",
            "mutex_destroy(&ppgtt->flush);",
            "mutex_destroy(&ppgtt->pin_mutex);",
            "spin_lock_destroy(&ppgtt->base.pd->lock);",
            "kfree(ppgtt->base.pd);")
    assert "i915_address_space_fini(" not in cleanup8
    assert "i915_address_space_fini(" not in cleanup6
    print("I915_PPGTT_SUCCESS_VS_CREATE_ERROR_TERMINAL_OWNERSHIP_OK")
    print("LIMITATION: pinned source contract only, not a C runtime test, "
          "NetBSD build or HP hardware validation")


if __name__ == "__main__":
    main()
