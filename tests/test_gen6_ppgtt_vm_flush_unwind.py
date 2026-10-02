#!/usr/bin/env python3
"""Pin Gen6 PPGTT creation error rollback to actual NetBSD resource ownership.

Compile actual pinned gen6_ppgtt_create() error labels with candidate 0017
in a strict C11/ASan/UBSan isolated harness. Cover page-directory failure,
scratch allocation failure, VMA allocation failure and the successful path.
The unpatched negative control must leave VM/flush resources initialized
when freeing the object. Check published generator byte identity and genuine
frozen/optional distinct overlay git apply --check. Not a native kernel build.
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
    str(ROOT / "tools/generate_gen6_ppgtt_vm_init_unwind_patch.py")
)
NETBSD_PPGTT_INIT = "sys/external/bsd/drm2/dist/drm/i915/gt/intel_ppgtt.c"
NETBSD_VM = "sys/external/bsd/drm2/dist/drm/i915/gt/intel_gtt.c"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
LINUX_GEN6 = "drivers/gpu/drm/i915/gt/gen6_ppgtt.c"

PRELUDE = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

struct i915_address_space { int top; };
struct i915_page_directory { int lock; };
struct i915_ppgtt {
    struct i915_address_space vm;
    struct i915_page_directory *pd;
};
struct gen6_ppgtt { struct i915_ppgtt base; int flush, pin_mutex; };
static struct gen6_ppgtt *current_ppgtt;
static int events[9], count;
static int vm_alive, flush_alive, pin_alive, pd_alive, scratch_alive;
static void event(int id)
{
    assert(count < 9);
    events[count++] = id;
}
static void free_scratch(struct i915_address_space *vm)
{
    assert(vm == &current_ppgtt->base.vm && scratch_alive);
    scratch_alive = 0;
    event(1);
}
static void spin_lock_destroy(void *lock)
{
    assert(lock == &current_ppgtt->base.pd->lock && pd_alive);
    event(2);
}
static void kfree(void *pointer)
{
    if (pointer == current_ppgtt->base.pd) {
        assert(pd_alive);
        pd_alive = 0;
        event(3);
    } else {
        assert(pointer == current_ppgtt && !vm_alive &&
               !flush_alive && !pin_alive && !pd_alive &&
               !scratch_alive);
        event(7);
    }
}
static void mutex_destroy(int *mutex)
{
    if (mutex == &current_ppgtt->flush) {
        assert(flush_alive);
        flush_alive = 0;
        event(4);
    } else {
        assert(mutex == &current_ppgtt->pin_mutex && pin_alive);
        pin_alive = 0;
        event(5);
    }
}
static void i915_address_space_fini(struct i915_address_space *vm)
{
    assert(vm == &current_ppgtt->base.vm && vm_alive &&
           !flush_alive && !pin_alive && !pd_alive && !scratch_alive);
    vm_alive = 0;
    event(6);
}
#define ERR_PTR(err) ((struct i915_ppgtt *)(intptr_t)(err))
"""

MAIN = r"""
static void reset(int stage)
{
    count = 0;
    vm_alive = flush_alive = pin_alive = 1;
    pd_alive = (stage >= 1);
    scratch_alive = (stage == 2);
}
static void check(const int *expected, size_t size)
{
    assert((size_t)count == size);
    for (size_t i = 0; i < size; ++i)
        assert(events[i] == expected[i]);
}
#define CHECK(...) do { \
    const int expected[] = {__VA_ARGS__}; \
    check(expected, sizeof(expected) / sizeof(expected[0])); \
} while (0)
int main(void)
{
    struct i915_page_directory directory = {0};
    struct gen6_ppgtt ppgtt = {
        .base = {.vm = {.top = 1}, .pd = &directory}
    };
    current_ppgtt = &ppgtt;

    reset(0);
    assert(run_gen6_error(&ppgtt, 0) == ERR_PTR(-ENOMEM));
    CHECK(4,5,6,7);

    reset(1);
    assert(run_gen6_error(&ppgtt, 1) == ERR_PTR(-ENOMEM));
    CHECK(2,3,4,5,6,7);

    reset(2);
    assert(run_gen6_error(&ppgtt, 2) == ERR_PTR(-ENOMEM));
    CHECK(1,2,3,4,5,6,7);

    reset(3);
    assert(run_gen6_error(&ppgtt, 3) == &ppgtt.base);
    assert(count == 0 && vm_alive && flush_alive && pin_alive);
    puts("I915_0017_GEN6_PPGTT_UNWIND_C11_FOUR_CASES_OK");
    return 0;
}
"""

NEGATIVE_MAIN = MAIN.replace(
    "int main(void)\n{",
    "int main(void)\n{\n    (void)i915_address_space_fini;\n",
)


def pinned_file(tree: Path, pin: str, relative: str) -> str:
    actual = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if actual != pin:
        raise RuntimeError("unexpected reference revision: " + actual)
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative], text=True,
    )
    if (tree / relative).read_text() != committed:
        raise RuntimeError("dirty pinned source: " + relative)
    return committed


def gen6_error_fragment(source: str) -> str:
    start = source.index("struct i915_ppgtt *gen6_ppgtt_create(")
    first = source.index("err_scratch:\n", start)
    end = source.index("\n}\n", first)
    return source[first:end] + "\n}\n"


def error_wrapper(source: str) -> str:
    return (
        "static struct i915_ppgtt *run_gen6_error("
        "struct gen6_ppgtt *ppgtt, int stage)\n"
        "{\n"
        "\tint err = -ENOMEM;\n"
        "\tif (stage == 0)\n\t\tgoto err_free;\n"
        "\tif (stage == 1)\n\t\tgoto err_pd;\n"
        "\tif (stage == 2)\n\t\tgoto err_scratch;\n"
        "\treturn &ppgtt->base;\n\n"
        + gen6_error_fragment(source)
    )


def compile_and_run(tmp: Path, label: str, source: str, main: str,
                    sanitizer: str, negative: bool) -> subprocess.CompletedProcess[str]:
    c = tmp / (label + ".c")
    exe = tmp / label
    c.write_text(PRELUDE + "\n" + source + "\n" + main)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=" + sanitizer, "-fno-omit-frame-pointer",
         str(c), "-o", str(exe)],
        check=True,
    )
    if negative:
        def no_core() -> None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return subprocess.run(
            [str(exe)], check=False, capture_output=True, text=True,
            preexec_fn=no_core,
        )
    return subprocess.run(
        [str(exe)], check=True, capture_output=True, text=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--linux-tree", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path, default=None)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()

    original = TOOL["pinned_source"](args.netbsd_tree)
    patched = TOOL["transform"](original)
    ppgtt = pinned_file(args.netbsd_tree, TOOL["NETBSD_PIN"],
                        NETBSD_PPGTT_INIT)
    vm = pinned_file(args.netbsd_tree, TOOL["NETBSD_PIN"], NETBSD_VM)
    linux = pinned_file(args.linux_tree, LINUX_PIN, LINUX_GEN6)
    assert "i915_address_space_init(&ppgtt->vm, VM_CLASS_PPGTT);" in ppgtt
    # Failed scratch setup already tears down its own partial resources;
    # jumping to err_scratch would release the same scratch storage twice.
    scratch_start = original.index("static int gen6_ppgtt_init_scratch(")
    scratch_end = original.index("static void gen6_ppgtt_free_pd(", scratch_start)
    scratch = original[scratch_start:scratch_end]
    assert ("ret = setup_scratch_page(vm, __GFP_HIGHMEM);\n"
            "\tif (ret)\n\t\treturn ret;") in scratch
    assert ("if (unlikely(setup_page_dma(vm, px_base(&vm->scratch[1])))) {\n"
            "\t\tcleanup_scratch_page(vm);\n"
            "\t\treturn -ENOMEM;\n\t}") in scratch
    create = original[original.index("struct i915_ppgtt *gen6_ppgtt_create("):]
    assert ("err = gen6_ppgtt_init_scratch(ppgtt);\n"
            "\tif (err)\n\t\tgoto err_pd;") in create
    assert ("err = PTR_ERR(ppgtt->vma);\n"
            "\t\tgoto err_scratch;") in create
    assert ("err_scratch:\n\tfree_scratch(&ppgtt->base.vm);\n"
            "err_pd:") in create
    assert "drm_mm_init(&vm->mm, 0, vm->total);" in vm
    assert "mutex_init(&vm->mutex);" in vm
    fini = vm[vm.index("void i915_address_space_fini("):
              vm.index("static void __i915_vm_release(")]
    assert "drm_mm_takedown(&vm->mm);" in fini
    assert "mutex_destroy(&vm->mutex);" in fini
    assert "err_put:\n\ti915_vm_put(&ppgtt->base.vm);" in linux
    init = original[original.index("struct i915_ppgtt *gen6_ppgtt_create("):]
    assert init.index("mutex_init(&ppgtt->flush);") < init.index(
        "mutex_init(&ppgtt->pin_mutex);"
    ) < init.index("ppgtt_init(&ppgtt->base, gt);")
    assert init.count("goto err_free;") == 1
    assert original.count("i915_address_space_fini(&ppgtt->base.vm);") == 0
    assert patched.count("i915_address_space_fini(&ppgtt->base.vm);") == 1

    with tempfile.TemporaryDirectory() as root:
        tmp = Path(root)
        generated = tmp / "0017-regenerated.patch"
        TOOL["generate"](args.netbsd_tree, generated)
        if generated.read_bytes() != args.patch.read_bytes():
            raise AssertionError("0017 candidate differs from frozen generator")
        print("I915_0017_GENERATOR_BYTE_MATCH_OK", flush=True)
        passed = compile_and_run(
            tmp, "positive", error_wrapper(patched),
            MAIN, "address,undefined", False,
        )
        print(passed.stdout.strip(), flush=True)
        negative = compile_and_run(
            tmp, "negative", error_wrapper(original),
            NEGATIVE_MAIN, "undefined", True,
        )
        if negative.returncode == 0 or "Assertion" not in negative.stderr:
            raise AssertionError("unpatched Gen6 VM/flush leak not detected")
        print("I915_0017_UNPATCHED_NEGATIVE_CONTROL_OK", flush=True)

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("overlay must be distinct from frozen NetBSD")
        targets.append(args.overlay_tree)
    for tree in targets:
        subprocess.run(
            ["git", "-C", str(tree), "apply", "--check", str(args.patch)],
            check=True,
        )
    print("I915_0017_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"))


if __name__ == "__main__":
    main()
