#!/usr/bin/env python3
"""Compile and exercise actual transformed NetBSD early-probe C with failure injection.

This is a host-isolated cleanup test, not a NetBSD object build or GPU test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "tools/generate_early_probe_unwind_patch.py"))

PRELUDE = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

struct drm_i915_private {
    int mmio_debug, uncore, irq_lock;
    struct { int lock; } gpu_error;
    int backlight_lock, sb_lock, sb_qos, av_mutex, pps_mutex, hdcp_comp_mutex;
    struct { int wm_mutex; } wm;
    int runtime_pm, wopcm, gt;
};
static struct {
    int mutex, spin, qos, wq, s0ix, gem, gt, uncore, debug;
} counts;
static int failure;
#define PM_QOS_CPU_DMA_LATENCY 1
#define PM_QOS_DEFAULT_VALUE 0
#define i915_inject_probe_failure(...) 0
#define intel_device_info_subplatform_init(...) ((void)0)
#define intel_uncore_mmio_debug_init_early(...) ((void)0)
#define intel_uncore_init_early(...) ((void)0)
#define spin_lock_init(...) ((void)0)
#define mutex_init(...) ((void)0)
#define pm_qos_add_request(...) ((void)0)
#define i915_memcpy_init_early(...) ((void)0)
#define intel_runtime_pm_init_early(...) ((void)0)
#define intel_wopcm_init_early(...) ((void)0)
#define intel_gt_init_early(...) ((void)0)
#define i915_gem_init_early(...) ((void)0)
#define intel_detect_pch(...) ((void)0)
#define intel_pm_setup(...) ((void)0)
#define intel_init_dpio(...) ((void)0)
#define intel_irq_init(...) ((void)0)
#define intel_init_display_hooks(...) ((void)0)
#define intel_init_clock_gating_hooks(...) ((void)0)
#define intel_init_audio_hooks(...) ((void)0)
#define intel_display_crc_init(...) ((void)0)
#define intel_detect_preproduction_hw(...) ((void)0)

static int mock_workqueues(void) { return failure == 1 ? -ENOMEM : 0; }
static int mock_s0ix(void) { return failure == 2 ? -ENOMEM : 0; }
static int mock_power(void) { return failure == 3 ? -EIO : 0; }
#define i915_workqueues_init(...) mock_workqueues()
#define vlv_alloc_s0ix_state(...) mock_s0ix()
#define intel_power_domains_init(...) mock_power()

#define i915_gem_cleanup_early(...) (counts.gem++)
#define intel_gt_driver_late_release(...) (counts.gt++)
#define vlv_free_s0ix_state(...) (counts.s0ix++)
#define i915_workqueues_cleanup(...) (counts.wq++)
#define pm_qos_remove_request(...) (counts.qos++)
#define mutex_destroy(...) (counts.mutex++)
#define spin_lock_destroy(...) (counts.spin++)
#define intel_uncore_fini_early(...) (counts.uncore++)
#define intel_uncore_mmio_debug_fini_early(...) (counts.debug++)
"""

MAIN = r"""
int main(void) {
    struct drm_i915_private priv = {0};
    int ret;

    failure = 1;
    ret = i915_driver_early_probe(&priv);
    assert(ret == -ENOMEM);
    assert(counts.wq == 0 && counts.s0ix == 0);
    assert(counts.gem == 0 && counts.gt == 0);
    assert(counts.qos == 1 && counts.mutex == 6 && counts.spin == 2);
    assert(counts.uncore == 1 && counts.debug == 1);

    memset(&counts, 0, sizeof(counts));
    failure = 2;
    ret = i915_driver_early_probe(&priv);
    assert(ret == -ENOMEM);
    assert(counts.wq == 1 && counts.s0ix == 0);
    assert(counts.gem == 0 && counts.gt == 0);
    assert(counts.qos == 1 && counts.mutex == 6 && counts.spin == 2);
    assert(counts.uncore == 1 && counts.debug == 1);

    memset(&counts, 0, sizeof(counts));
    failure = 3;
    ret = i915_driver_early_probe(&priv);
    assert(ret == -EIO);
    assert(counts.gem == 1 && counts.gt == 1 && counts.s0ix == 1);
    assert(counts.wq == 1 && counts.qos == 1);
    assert(counts.mutex == 6 && counts.spin == 2);
    assert(counts.uncore == 1 && counts.debug == 1);

    memset(&counts, 0, sizeof(counts));
    failure = 0;
    ret = i915_driver_early_probe(&priv);
    assert(ret == 0);
    assert(counts.qos == 0 && counts.mutex == 0 && counts.spin == 0);
    assert(counts.wq == 0 && counts.gem == 0);
    puts("EARLY_PROBE_UNWIND_TESTS_OK");
    return 0;
}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()

    original = MODULE["pinned_source"](args.netbsd_tree)
    revised = MODULE["transform"](original)
    assert revised != original
    assert revised.count("err_early:\n") == 1
    assert revised.count("pm_qos_remove_request(&dev_priv->sb_qos);") == (
        original.count("pm_qos_remove_request(&dev_priv->sb_qos);") + 1
    )
    start = revised.index("static int i915_driver_early_probe(")
    stop = revised.index("/**\n * i915_driver_late_release", start)
    function = revised[start:stop]
    source = PRELUDE + "\n" + function + "\n" + MAIN
    with tempfile.TemporaryDirectory() as directory:
        c = Path(directory) / "test.c"
        exe = Path(directory) / "test"
        c.write_text(source)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-pedantic", str(c), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)
    for tree in (args.netbsd_tree, args.overlay_tree):
        subprocess.run(["git", "-C", str(tree), "apply", "--check",
                        str(args.patch)], check=True)
    print("EARLY_PROBE_APPLY_CHECKS_OK")


if __name__ == "__main__":
    main()
