#!/usr/bin/env python3
"""Exercise real transformed NetBSD i915_driver_register with fault injection.

The probe unwind is also checked by source anchor/order assertions. This is a
host-only isolated C test, not a NetBSD object build or whole-driver parity.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / "tools/generate_register_failure_patch.py"))

PRELUDE = r"""
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>

struct drm_device { int dummy; };
struct drm_i915_private {
    struct drm_device drm;
    int gt;
    int runtime_pm;
};
static int events[64], count, registration_error, display, vgpu;
static void event(int n) { assert(count < 64); events[count++] = n; }
static int mock_register(struct drm_device *d, int flags)
{ (void)d; (void)flags; event(4); return registration_error; }

#define i915_gem_driver_register(...) event(1)
#define i915_pmu_register(...) event(2)
#define intel_vgpu_active(...) (vgpu)
#define I915_WRITE(...) event(3)
#define drm_dev_register(d, flags) mock_register((d), (flags))
#define DRM_ERROR(...) ((void)0)
#define drm_dev_unregister(...) event(5)
#define i915_pmu_unregister(...) event(6)
#define i915_gem_driver_unregister(...) event(7)
#define i915_debugfs_register(...) event(8)
#define i915_setup_sysfs(...) event(9)
#define i915_perf_register(...) event(10)
#define HAS_DISPLAY(...) (display)
#define INTEL_DISPLAY_ENABLED(...) (display)
#define intel_opregion_register(...) event(11)
#define acpi_video_register(...) event(12)
#define intel_gt_driver_register(...) event(13)
#define intel_audio_init(...) event(14)
#define intel_fbdev_initial_config_async(...) event(15)
#define drm_kms_helper_poll_init(...) event(16)
#define intel_power_domains_enable(...) event(17)
#define intel_runtime_pm_enable(...) event(18)

static void check(const int *expected, size_t size)
{
    size_t i;
    assert((size_t)count == size);
    for (i = 0; i < size; i++)
        assert(events[i] == expected[i]);
}
#define CHECK(...) do { \
    const int expected[] = {__VA_ARGS__}; \
    check(expected, sizeof(expected) / sizeof(expected[0])); \
} while (0)
"""

MAIN = r"""
int main(void)
{
    struct drm_i915_private i915 = {0};
    int ret;

    registration_error = -EIO;
    vgpu = 1;
    display = 1;
    ret = i915_driver_register(&i915);
    assert(ret == -EIO);
    CHECK(1, 2, 3, 4, 5, 6, 7);

    count = 0;
    registration_error = -ENOMEM;
    vgpu = 0;
    display = 0;
    ret = i915_driver_register(&i915);
    assert(ret == -ENOMEM);
    CHECK(1, 2, 4, 5, 6, 7);

    count = 0;
    registration_error = 0;
    ret = i915_driver_register(&i915);
    assert(ret == 0);
    CHECK(1, 2, 4, 8, 9, 10, 13, 14, 15, 17, 18);

    count = 0;
    vgpu = 1;
    display = 1;
    ret = i915_driver_register(&i915);
    assert(ret == 0);
    CHECK(1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18);
    puts("I915_REGISTER_HOST_C_TESTS_OK");
    return 0;
}
"""


def check_probe_unwind(source: str) -> None:
    probe = source.split("int i915_driver_probe(struct pci_dev *pdev,", 1)[1].split(
        "void i915_driver_remove(struct drm_i915_private *i915)", 1
    )[0]
    sequence = (
        "ret = i915_driver_register(dev_priv);",
        "if (ret)\n\t\tgoto out_cleanup_registration;",
        "out_cleanup_registration:",
        "intel_opregion_unregister(dev_priv);",
        "i915_gem_suspend(dev_priv);",
        "intel_gvt_driver_remove(dev_priv);",
        "i915_driver_modeset_remove(dev_priv);",
        "i915_reset_error_state(dev_priv);",
        "i915_gem_driver_remove(dev_priv);",
        "intel_power_domains_driver_remove(dev_priv);",
        "i915_driver_hw_remove(dev_priv);",
        "i915_gem_driver_release(dev_priv);",
        "goto out_cleanup_memory;",
        "out_cleanup_hw:\n\ti915_driver_hw_remove(dev_priv);",
        "out_cleanup_memory:",
        "intel_memory_regions_driver_release(dev_priv);",
        "i915_ggtt_driver_release(dev_priv);",
        "out_cleanup_mmio:",
        "i915_driver_mmio_release(dev_priv);",
        "out_runtime_pm_put:",
        "enable_rpm_wakeref_asserts(&dev_priv->runtime_pm);",
        "i915_driver_late_release(dev_priv);",
    )
    positions = [probe.index(s) for s in sequence]
    assert positions == sorted(positions), "probe rollback ordering changed"
    assert probe.count("out_cleanup_registration:") == 1
    assert probe.count("i915_driver_register(dev_priv);") == 1
    assert probe.count("i915_gem_driver_release(dev_priv);") == 1
    assert probe.count("out_cleanup_memory:") == 1
    # Modeset failure must skip registration-only GEM release and enter
    # the existing hardware cleanup path instead.
    assert "if (ret < 0)\n\t\tgoto out_cleanup_hw;" in probe
    print("I915_PROBE_UNWIND_ORDER_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path,
                        help="optional real unpublished six-edit overlay")
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--previous-patch", type=Path, required=True)
    parser.add_argument("--opregion-patch", type=Path, required=True)
    args = parser.parse_args()

    original = TOOL["pinned_source"](args.netbsd_tree)
    adapted = TOOL["transform"](original)
    check_probe_unwind(adapted)
    start = adapted.index(
        "static int i915_driver_register(struct drm_i915_private *dev_priv)"
    )
    stop = adapted.index("/**\n * i915_driver_unregister", start)
    function = adapted[start:stop]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        # Reject manually authored artifacts that drift from the canonical
        # pinned-source Python generator.
        generated = tmp / "regenerated-0008.patch"
        TOOL["generate"](args.netbsd_tree, generated)
        if generated.read_bytes() != args.patch.read_bytes():
            raise AssertionError("0008 generated artifact differs from candidate")
        print("I915_0008_GENERATOR_BYTE_MATCH_OK")

        c = tmp / "test.c"
        exe = tmp / "test"
        c.write_text(PRELUDE + "\n" + function + "\n" + MAIN)
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(c), "-o", str(exe)
        ], check=True)
        subprocess.run([str(exe)], check=True)

        # Integrate both patches in a disposable tree without touching
        # either the pinned source clone or the unpublished overlay.
        rel = Path(TOOL["REL"])
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(original)
        opregion_rel = Path(
            "sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c"
        )
        opregion_target = tmp / opregion_rel
        opregion_target.parent.mkdir(parents=True, exist_ok=True)
        opregion_original = subprocess.check_output(
            ["git", "-C", str(args.netbsd_tree), "show",
             "HEAD:" + str(opregion_rel)],
            text=True,
        )
        if (args.netbsd_tree / opregion_rel).read_text() != opregion_original:
            raise RuntimeError("dirty frozen OpRegion source")
        opregion_target.write_text(opregion_original)
        subprocess.run(
            ["git", "-C", str(tmp), "apply", str(args.previous_patch)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp), "apply", str(args.opregion_patch)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp), "apply", str(args.patch)],
            check=True,
        )
        combined = target.read_text()
        assert "err_early:\n" in combined
        assert "out_cleanup_registration:\n" in combined
        assert "intel_opregion_unregister(dev_priv);" in combined
        assert "opregion->rvda ? opregion->asle->rvds : 0;" in opregion_target.read_text()
        print("I915_0007_0009_0008_COMBINED_APPLY_OK")

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("overlay-tree must be distinct from frozen reference")
        targets.append(args.overlay_tree)
    for tree in targets:
        for patch in (args.opregion_patch, args.patch):
            subprocess.run(
                ["git", "-C", str(tree), "apply", "--check", str(patch)],
                check=True,
            )
    print("I915_REGISTER_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"))


if __name__ == "__main__":
    main()
