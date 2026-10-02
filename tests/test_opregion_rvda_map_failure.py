#!/usr/bin/env python3
"""Strict actual-NetBSD-source host C test for failed RVDA mapping (0010).

Uses the real transformed intel_opregion_setup() RVDA branch, extracted from
the pinned NetBSD source; models ACPI mapping, validation and unmapping.
Checks generated-patch bytes and composition with optional-ASLE candidate
0009. Not a NetBSD kernel-object build or a live HP test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import resource
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(
    ROOT / "tools/generate_opregion_rvda_map_failure_patch.py"
))

PRELUDE = r"""
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#define __NetBSD__ 1
#define OPREGION_SIZE 8192
#define DRM_DEBUG_KMS(...) ((void)0)
#define WARN_ON(expr) ((void)(expr))
typedef uintptr_t resource_size_t;
typedef unsigned int u32;
struct opregion_header { struct { unsigned int major, minor; } over; };
struct opregion_asle { resource_size_t rvda; size_t rvds; };
struct intel_opregion {
    struct opregion_header *header;
    struct opregion_asle *asle;
    void *rvda;
    const void *vbt;
    size_t vbt_size;
};
static int mapping_succeeds, valid_vbt, map_calls, unmap_calls, check_calls;
static void *AcpiOsMapMemory(resource_size_t where, size_t length)
{
    assert(where >= OPREGION_SIZE && length == 4096);
    map_calls++;
    return mapping_succeeds ? (void *)(uintptr_t)0x5000 : NULL;
}
static void AcpiOsUnmapMemory(void *address, size_t length)
{
    assert(address != NULL && length == 4096);
    unmap_calls++;
}
static int intel_bios_is_valid_vbt(const void *vbt, size_t length)
{
    assert(length == 4096);
    check_calls++;
    return vbt != NULL && valid_vbt;
}
"""

MAIN = r"""
static void reset(void)
{
    map_calls = unmap_calls = check_calls = 0;
    mapping_succeeds = valid_vbt = 0;
}
int main(void)
{
    struct opregion_header header = { .over = {2, 1} };
    struct opregion_asle asle = {.rvda = 0x9000, .rvds = 4096};
    struct intel_opregion op = {.header = &header, .asle = &asle};

    reset();
    op.asle = NULL;
    assert(run_rvda(&op, 0x1000) == 0);
    assert(map_calls == 0 && unmap_calls == 0 && check_calls == 0);

    reset();
    op.asle = &asle;
    asle.rvda = 0;
    assert(run_rvda(&op, 0x1000) == 0);
    assert(map_calls == 0 && unmap_calls == 0 && check_calls == 0);

    reset();
    asle.rvda = 0x9000;
    assert(run_rvda(&op, 0x1000) == 0);
    assert(map_calls == 1 && check_calls == 1 && unmap_calls == 0);
    assert(op.rvda == NULL && op.vbt == NULL);

    reset();
    mapping_succeeds = 1;
    assert(run_rvda(&op, 0x1000) == 0);
    assert(map_calls == 1 && check_calls == 1 && unmap_calls == 1);
    assert(op.rvda == NULL && op.vbt == NULL);

    reset();
    mapping_succeeds = valid_vbt = 1;
    assert(run_rvda(&op, 0x1000) == 1);
    assert(map_calls == 1 && check_calls == 1 && unmap_calls == 0);
    assert(op.rvda == (void *)(uintptr_t)0x5000);
    assert(op.vbt == op.rvda && op.vbt_size == asle.rvds);

    puts("I915_RVDA_MAP_FAILURE_HOST_C_OK");
    return 0;
}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path,
                        help="optional real unpublished six-edit overlay")
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--opregion-patch", type=Path, required=True,
                        help="candidate 0009 optional-ASLE cleanup")
    args = parser.parse_args()

    original = TOOL["pinned_source"](args.netbsd_tree)
    modified = TOOL["transform"](original)
    start_anchor = "\tif (opregion->header->over.major >= 2 && opregion->asle &&"
    end_anchor = "\n\tvbt = base + OPREGION_VBT_OFFSET;"
    if original.count(start_anchor) != 1 or original.count(end_anchor) != 1:
        raise RuntimeError("RVDA branch boundaries changed")
    start = modified.index(start_anchor)
    end = modified.index(end_anchor, start)
    branch = modified[start:end]
    if branch.count("if (opregion->rvda)") != 1:
        raise RuntimeError("RVDA map-failure cleanup guard missing")
    wrapper = (
        "static int run_rvda(struct intel_opregion *opregion, u32 asls)\n"
        "{\n"
        "\tconst void *vbt = NULL;\n"
        "\tu32 vbt_size = 0;\n"
        + branch +
        "\n\treturn 0;\n"
        "out:\n"
        "\treturn 1;\n"
        "}\n"
    )

    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        generated = tmp / "regenerated-0010.patch"
        TOOL["generate"](args.netbsd_tree, generated)
        if generated.read_bytes() != args.patch.read_bytes():
            raise AssertionError("candidate 0010 differs from pinned generator")
        print("I915_RVDA_0010_GENERATOR_BYTE_MATCH_OK")

        c = tmp / "test.c"
        exe = tmp / "test"
        c.write_text(PRELUDE + "\n" + wrapper + "\n" + MAIN)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
             str(c), "-o", str(exe)],
            check=True,
        )
        subprocess.run([str(exe)], check=True)

        # Negative control: the unpatched *same* pinned RVDA source
        # must attempt to unmap NULL on the map-failure branch.
        original_start = original.index(start_anchor)
        original_end = original.index(end_anchor, original_start)
        before = original[original_start:original_end]
        if before.count("if (opregion->rvda)") != 0 or wrapper.count(branch) != 1:
            raise RuntimeError("negative control no longer models the unpatched branch")
        unpatched = tmp / "negative_control.c"
        unpatched_exe = tmp / "negative_control"
        unpatched.write_text(PRELUDE + "\n" + wrapper.replace(branch, before, 1)
                             + "\n" + MAIN)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fsanitize=undefined", "-fno-omit-frame-pointer",
             str(unpatched), "-o", str(unpatched_exe)],
            check=True,
        )

        def no_core_dump() -> None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        failed = subprocess.run(
            [str(unpatched_exe)], check=False, capture_output=True, text=True,
            preexec_fn=no_core_dump,
        )
        if failed.returncode == 0 or "address != NULL" not in failed.stderr:
            raise AssertionError("unpatched branch did not fail on NULL unmap")
        print("I915_RVDA_0010_UNPATCHED_NEGATIVE_CONTROL_OK")

        relative = Path(TOOL["REL"])
        target = tmp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(original)
        for patch in (args.patch, args.opregion_patch):
            subprocess.run(
                ["git", "-C", str(tmp), "apply", str(patch)],
                check=True,
            )
        combined = target.read_text()
        assert "if (opregion->rvda)\n\t\t\t\tAcpiOsUnmapMemory(" in combined
        assert "opregion->rvda ? opregion->asle->rvds : 0;" in combined
        print("I915_RVDA_0009_0010_COMBINED_APPLY_OK")

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("overlay-tree must be distinct from frozen reference")
        targets.append(args.overlay_tree)
    for tree in targets:
        for patch in (args.patch, args.opregion_patch):
            subprocess.run(
                ["git", "-C", str(tree), "apply", "--check", str(patch)],
                check=True,
            )
    print("I915_RVDA_0010_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"))


if __name__ == "__main__":
    main()
