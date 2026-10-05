#!/usr/bin/env python3
"""Compile/test the actual pinned NetBSD OpRegion unregister C with candidate 0009.

The test assembles a disposable isolated C translation unit from the exact
frozen NetBSD function, replacing only the candidate's one source line.
It is a host-only ASan/UBSan test; it does not build a NetBSD kernel object.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile
from sanitizer_support import run_sanitized

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c"
OLD = "\tsize_t rvds = opregion->asle->rvds;"
NEW = "\tsize_t rvds = opregion->rvda ? opregion->asle->rvds : 0;"

PRELUDE = r"""
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#define __NetBSD__ 1
#define PCI_D1 1
#define OPREGION_SIZE 8192
struct opregion_asle { size_t rvds; };
struct intel_opregion {
    void *header, *acpi, *swsci, *vbt, *lid_state, *rvda;
    void *vbt_firmware, *acpi_notifier;
    struct opregion_asle *asle;
};
struct drm_i915_private { struct intel_opregion opregion; };
static int suspend_calls, notifier_calls, unmap_calls, free_calls;
static void *unmap_addr[4];
static size_t unmap_size[4];
static void intel_opregion_suspend(struct drm_i915_private *i915, int state)
{ (void)i915; assert(state == PCI_D1); suspend_calls++; }
static void acpidisp_deregister_notify(void *handle)
{ assert(handle != NULL); notifier_calls++; }
static void AcpiOsUnmapMemory(void *addr, size_t length)
{
    assert(addr != NULL && unmap_calls < 4);
    unmap_addr[unmap_calls] = addr;
    unmap_size[unmap_calls++] = length;
}
static void kfree(void *p)
{ assert(p != NULL); free_calls++; }
"""

MAIN = r"""
static void reset(void)
{
    suspend_calls = notifier_calls = unmap_calls = free_calls = 0;
    for (int i = 0; i < 4; ++i) {
        unmap_addr[i] = NULL;
        unmap_size[i] = 0;
    }
}
int main(void)
{
    struct drm_i915_private i915 = {0};
    struct opregion_asle asle = {.rvds = 32768};

    reset();
    intel_opregion_unregister(&i915);
    assert(suspend_calls == 1 && unmap_calls == 0 && notifier_calls == 0);

    reset();
    i915.opregion.header = (void *)(uintptr_t)0x1000;
    i915.opregion.acpi_notifier = (void *)(uintptr_t)0x2000;
    i915.opregion.vbt_firmware = (void *)(uintptr_t)0x3000;
    intel_opregion_unregister(&i915);
    assert(suspend_calls == 1 && notifier_calls == 1 && free_calls == 1);
    assert(unmap_calls == 1 && unmap_size[0] == OPREGION_SIZE);
    assert(i915.opregion.header == NULL && i915.opregion.asle == NULL);

    reset();
    i915.opregion.header = (void *)(uintptr_t)0x1000;
    i915.opregion.asle = &asle;
    intel_opregion_unregister(&i915);
    assert(suspend_calls == 1 && unmap_calls == 1);
    assert(unmap_size[0] == OPREGION_SIZE);

    reset();
    i915.opregion.header = (void *)(uintptr_t)0x1000;
    i915.opregion.asle = &asle;
    i915.opregion.rvda = (void *)(uintptr_t)0x4000;
    intel_opregion_unregister(&i915);
    assert(suspend_calls == 1 && unmap_calls == 2);
    assert(unmap_addr[0] == (void *)(uintptr_t)0x1000);
    assert(unmap_size[0] == OPREGION_SIZE);
    assert(unmap_addr[1] == (void *)(uintptr_t)0x4000);
    assert(unmap_size[1] == asle.rvds);
    assert(i915.opregion.rvda == NULL && i915.opregion.asle == NULL);
    puts("OPREGION_UNREGISTER_HOST_C_OK");
    return 0;
}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()

    tree = args.netbsd_tree
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError(f"frozen NetBSD commit mismatch: {head}")
    baseline = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True
    )
    if (tree / REL).read_text() != baseline:
        raise RuntimeError("pinned NetBSD OpRegion file is dirty")
    patch = args.patch.read_text()
    if patch.count("-" + OLD + "\n") != 1 or patch.count("+" + NEW + "\n") != 1:
        raise RuntimeError("candidate 0009 no longer matches the known delta")
    if baseline.count(OLD) != 1:
        raise RuntimeError("NetBSD unregister source anchor changed")
    if baseline.count("if (opregion->header->over.major >= 2 && opregion->asle &&") != 1:
        raise RuntimeError("RVDA-to-ASLE ownership invariant changed")

    start = baseline.index("void intel_opregion_unregister(struct drm_i915_private *i915)")
    end = baseline.index("\n}\n", start) + 3
    original = baseline[start:end]
    if original.count(OLD) != 1 or original.count(NEW) != 0:
        raise RuntimeError("candidate no longer applies inside actual function")
    function = original.replace(OLD, NEW, 1)

    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        c = tmp / "opregion_test.c"
        exe = tmp / "opregion_test"
        c.write_text(PRELUDE + function + MAIN)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
             str(c), "-o", str(exe)],
            check=True,
        )
        run_sanitized(exe)
    subprocess.run(
        ["git", "-C", str(tree), "apply", "--check", str(args.patch)],
        check=True,
    )
    print("OPREGION_0009_PATCH_CHECK_OK")


if __name__ == "__main__":
    main()
