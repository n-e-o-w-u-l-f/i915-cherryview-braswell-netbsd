#!/usr/bin/env python3
"""Pinned NetBSD Gen8 PPGTT creation-failure VM-finalization regression 0016.

Extract the actual gen8_ppgtt_create() error labels, compile C11/ASan/UBSan
fault-injection tests for the three failure stages and success bypass,
and prove the unmodified source fails the VM-finalization assertion.
Require byte-identical regeneration of the published patch and native
git apply --check on the frozen NetBSD checkout and optional distinct
real Legion six-edit overlay. This does NOT build the NetBSD kernel.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import resource
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(
    str(ROOT / "tools/generate_gen8_ppgtt_vm_init_unwind_patch.py")
)
PPGTT_INIT = "sys/external/bsd/drm2/dist/drm/i915/gt/intel_ppgtt.c"
GTT_VM = "sys/external/bsd/drm2/dist/drm/i915/gt/intel_gtt.c"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
LINUX_GEN8 = "drivers/gpu/drm/i915/gt/gen8_ppgtt.c"

PRELUDE = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

struct i915_address_space { int top; };
struct i915_ppgtt {
    struct i915_address_space vm;
    void *pd;
};
static struct i915_ppgtt *current_ppgtt;
static int events[8], event_count, vm_active, vm_finis;
static void note(int id)
{
    assert(event_count < 8);
    events[event_count++] = id;
}
static int gen8_pd_top_count(struct i915_address_space *vm)
{
    assert(vm == &current_ppgtt->vm);
    return 4;
}
static void __gen8_ppgtt_cleanup(struct i915_address_space *vm, void *pd,
                                 int count, int level)
{
    assert(vm == &current_ppgtt->vm && pd == current_ppgtt->pd);
    assert(count == 4 && level == 2 && vm_active);
    note(1);
}
static void free_scratch(struct i915_address_space *vm)
{
    assert(vm == &current_ppgtt->vm && vm_active);
    note(2);
}
static void i915_address_space_fini(struct i915_address_space *vm)
{
    assert(vm == &current_ppgtt->vm && vm_active && vm_finis == 0);
    vm_finis++;
    vm_active = 0;
    note(3);
}
static void kfree(void *p)
{
    assert(p == current_ppgtt && !vm_active);
    note(4);
}
#define ERR_PTR(err) ((struct i915_ppgtt *)(intptr_t)(err))
"""

MAIN = r"""
static void reset(void)
{
    event_count = vm_finis = 0;
    vm_active = 1;
}
static void check(const int *expected, size_t size)
{
    assert((size_t)event_count == size);
    for (size_t i = 0; i < size; ++i)
        assert(events[i] == expected[i]);
}
#define CHECK(...) do { \
    const int expected[] = {__VA_ARGS__}; \
    check(expected, sizeof(expected) / sizeof(expected[0])); \
} while (0)

int main(void)
{
    struct i915_ppgtt ppgtt = {.vm = {.top = 2},
                              .pd = (void *)(uintptr_t)0x5000};
    current_ppgtt = &ppgtt;

    reset();
    assert(run_gen8_error(&ppgtt, 0) == ERR_PTR(-ENOMEM));
    CHECK(3, 4);
    assert(vm_finis == 1 && vm_active == 0);

    reset();
    assert(run_gen8_error(&ppgtt, 1) == ERR_PTR(-ENOMEM));
    CHECK(2, 3, 4);
    assert(vm_finis == 1 && vm_active == 0);

    reset();
    assert(run_gen8_error(&ppgtt, 2) == ERR_PTR(-ENOMEM));
    CHECK(1, 2, 3, 4);
    assert(vm_finis == 1 && vm_active == 0);

    reset();
    assert(run_gen8_error(&ppgtt, 3) == &ppgtt);
    assert(event_count == 0 && vm_finis == 0 && vm_active == 1);

    puts("I915_0016_GEN8_PPGTT_VM_ROLLBACK_C11_FOUR_CASES_OK");
    return 0;
}
"""

NEGATIVE_MAIN = MAIN.replace(
    "int main(void)\n{",
    "int main(void)\n{\n    (void)i915_address_space_fini;\n",
)


def pinned_file(tree: Path, pin: str, relative: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != pin:
        raise RuntimeError(f"wrong pinned checkout: {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative], text=True,
    )
    if (tree / relative).read_text() != committed:
        raise RuntimeError(f"dirty/missing pinned source: {relative}")
    return committed


def failure_labels(src: str) -> str:
    start = src.index("struct i915_ppgtt *gen8_ppgtt_create(")
    failure = src.index("err_free_pd:\n", start)
    finish = src.index("\n}\n", failure)
    return src[failure:finish] + "\n}\n"


def wrapper(src: str) -> str:
    return (
        "static struct i915_ppgtt *run_gen8_error("
        "struct i915_ppgtt *ppgtt, int stage)\n"
        "{\n"
        "\tint err = -ENOMEM;\n"
        "\tif (stage == 0)\n\t\tgoto err_free;\n"
        "\tif (stage == 1)\n\t\tgoto err_free_scratch;\n"
        "\tif (stage == 2)\n\t\tgoto err_free_pd;\n"
        "\treturn ppgtt;\n\n"
        + failure_labels(src)
    )


def compile_and_run(tmp: Path, name: str, fragment: str, main: str,
                    sanitizer: str, negative: bool) -> subprocess.CompletedProcess[str]:
    c = tmp / (name + ".c")
    exe = tmp / name
    c.write_text(PRELUDE + "\n" + fragment + "\n" + main)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=" + sanitizer, "-fno-omit-frame-pointer",
         str(c), "-o", str(exe)],
        check=True,
    )
    if negative:
        def disable_core() -> None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return subprocess.run(
            [str(exe)], capture_output=True, text=True, check=False,
            preexec_fn=disable_core,
        )
    return subprocess.run(
        [str(exe)], capture_output=True, text=True, check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--linux-tree", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path, default=None)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()

    original = TOOL["pinned_source"](args.netbsd_tree)
    transformed = TOOL["transform"](original)
    init = pinned_file(args.netbsd_tree, TOOL["NETBSD_PIN"], PPGTT_INIT)
    vm = pinned_file(args.netbsd_tree, TOOL["NETBSD_PIN"], GTT_VM)
    linux = pinned_file(args.linux_tree, LINUX_PIN, LINUX_GEN8)

    # All failures occur after ppgtt_init initialized drm_mm and mutex.
    assert "i915_address_space_init(&ppgtt->vm, VM_CLASS_PPGTT);" in init
    # Partially allocated scratch must be freed internally exactly once.
    # The Gen8 creation error for that stage bypasses err_free_scratch.
    scratch_start = original.index("static int gen8_init_scratch(")
    scratch_end = original.index("static int gen8_preallocate_top_level_pdp(",
                                 scratch_start)
    scratch = original[scratch_start:scratch_end]
    assert ("ret = setup_scratch_page(vm, __GFP_HIGHMEM);\n"
            "\tif (ret)\n\t\treturn ret;") in scratch
    assert ("if (unlikely(setup_page_dma(vm, px_base(&vm->scratch[i]))))\n"
            "\t\t\tgoto free_scratch;") in scratch
    assert "free_scratch:\n\tfree_scratch(vm);\n\treturn -ENOMEM;" in scratch
    create = original[original.index("struct i915_ppgtt *gen8_ppgtt_create("):]
    assert ("err = gen8_init_scratch(&ppgtt->vm);\n"
            "\tif (err)\n\t\tgoto err_free;") in create
    assert ("err = PTR_ERR(ppgtt->pd);\n"
            "\t\tgoto err_free_scratch;") in create
    assert ("err_free_scratch:\n\tfree_scratch(&ppgtt->vm);\n"
            "err_free:") in create
    assert "drm_mm_init(&vm->mm, 0, vm->total);" in vm
    assert "mutex_init(&vm->mutex);" in vm
    fini = vm[vm.index("void i915_address_space_fini("):
              vm.index("static void __i915_vm_release(", 
                       vm.index("void i915_address_space_fini("))]
    assert "drm_mm_takedown(&vm->mm);" in fini
    assert "mutex_destroy(&vm->mutex);" in fini
    init_section = original[original.index("struct i915_ppgtt *gen8_ppgtt_create("):]
    assert init_section.index("ppgtt_init(ppgtt, gt);") < init_section.index(
        "err = gen8_init_scratch(&ppgtt->vm);"
    )
    assert init_section.index("err_free_scratch:\n") < \
        init_section.index("err_free:\n")
    assert init_section.index("ppgtt->vm.cleanup = gen8_ppgtt_cleanup;") < \
        init_section.index("return ppgtt;\n")
    assert "err_put:\n\ti915_vm_put(&ppgtt->vm);" in linux
    assert original.count("i915_address_space_fini(&ppgtt->vm);") == 0
    assert transformed.count("i915_address_space_fini(&ppgtt->vm);") == 1

    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        generated = tmp / "0016-regenerated.patch"
        TOOL["generate"](args.netbsd_tree, generated)
        if generated.read_bytes() != args.patch.read_bytes():
            raise AssertionError("candidate 0016 differs from source-pinned generator")
        print("I915_0016_GENERATOR_BYTE_MATCH_OK", flush=True)
        positive = compile_and_run(tmp, "positive", wrapper(transformed),
                                   MAIN, "address,undefined", False)
        print(positive.stdout.strip(), flush=True)
        negative = compile_and_run(tmp, "negative", wrapper(original),
                                   NEGATIVE_MAIN, "undefined", True)
        if negative.returncode == 0 or "Assertion" not in negative.stderr:
            raise AssertionError(
                "original Gen8 error path did not fail VM finalization gate"
            )
        print("I915_0016_UNPATCHED_NEGATIVE_CONTROL_OK", flush=True)

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("genuine overlay must differ from frozen tree")
        targets.append(args.overlay_tree)
    for tree in targets:
        subprocess.run(
            ["git", "-C", str(tree), "apply", "--check", str(args.patch)],
            check=True,
        )
    print("I915_0016_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"),
          flush=True)


if __name__ == "__main__":
    main()
