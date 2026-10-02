#!/usr/bin/env python3
"""Generate scoped NetBSD i915 drm_dev_register failure-propagation patch.

Pinned Linux i915_driver_register returns the DRM registration error, calls
drm_dev_unregister, and reverses PMU/GEM registration. NetBSD's imported
version logs the failure and continues. This translates the known error
path while preserving the NetBSD split between modeset, GEM and HW phases.
Candidate 0009 (optional-ASLE RVDA cleanup) is a prerequisite: this failure
path must release the OpRegion mapping set up during i915_driver_hw_probe.
Generic probe/display parity and native object verification remain open.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != NETBSD_PIN:
        raise RuntimeError(f"wrong frozen NetBSD commit: {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True
    )
    if (tree / REL).read_text() != committed:
        raise RuntimeError("dirty pinned i915_drv.c: refuse generation")
    return committed


def exactly(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {source.count(old)}")
    return source.replace(old, new, 1)


def replace_between(source: str, start: str, stop: str, fn) -> str:
    if source.count(start) != 1 or source.count(stop) != 1:
        raise RuntimeError(f"missing/non-unique function boundary {start}")
    left = source.index(start)
    right = source.index(stop, left)
    return source[:left] + fn(source[left:right]) + source[right:]


def register_changes(body: str) -> str:
    body = exactly(body,
        "static void i915_driver_register(struct drm_i915_private *dev_priv)",
        "static int i915_driver_register(struct drm_i915_private *dev_priv)",
        "return type")
    body = exactly(body,
        "\tstruct drm_device *dev = &dev_priv->drm;\n",
        "\tstruct drm_device *dev = &dev_priv->drm;\n\tint ret;\n",
        "registration error variable")
    old = (
        "\tif (drm_dev_register(dev, 0) == 0) {\n"
        "\t\ti915_debugfs_register(dev_priv);\n"
        "\t\ti915_setup_sysfs(dev_priv);\n\n"
        "\t\t/* Depends on sysfs having been initialized */\n"
        "\t\ti915_perf_register(dev_priv);\n"
        "\t} else\n"
        "\t\tDRM_ERROR(\"Failed to register driver for userspace access!\\n\");\n"
    )
    new = (
        "\tret = drm_dev_register(dev, 0);\n"
        "\tif (ret) {\n"
        "\t\tDRM_ERROR(\"Failed to register driver for userspace access!\\n\");\n"
        "\t\tdrm_dev_unregister(dev);\n"
        "\t\ti915_pmu_unregister(dev_priv);\n"
        "\t\ti915_gem_driver_unregister(dev_priv);\n"
        "\t\treturn ret;\n"
        "\t}\n\n"
        "\ti915_debugfs_register(dev_priv);\n"
        "\ti915_setup_sysfs(dev_priv);\n\n"
        "\t/* Depends on sysfs having been initialized */\n"
        "\ti915_perf_register(dev_priv);\n"
    )
    body = exactly(body, old, new, "DRM registration failure")
    body = exactly(body,
        "\tintel_runtime_pm_enable(&dev_priv->runtime_pm);\n}\n",
        "\tintel_runtime_pm_enable(&dev_priv->runtime_pm);\n\n\treturn 0;\n}\n",
        "registration success result")
    return body


def probe_changes(body: str) -> str:
    body = exactly(body,
        "\ti915_driver_register(dev_priv);\n\n"
        "\tenable_rpm_wakeref_asserts(&dev_priv->runtime_pm);\n",
        "\tret = i915_driver_register(dev_priv);\n"
        "\tif (ret)\n"
        "\t\tgoto out_cleanup_registration;\n\n"
        "\tenable_rpm_wakeref_asserts(&dev_priv->runtime_pm);\n",
        "probe registration propagation")
    body = exactly(body,
        "out_cleanup_hw:\n\ti915_driver_hw_remove(dev_priv);\n",
        "out_cleanup_registration:\n"
        "\tintel_opregion_unregister(dev_priv);\n"
        "\ti915_gem_suspend(dev_priv);\n"
        "\ti915_gem_driver_remove(dev_priv);\n"
        "\ti915_gem_driver_release(dev_priv);\n"
        "\tintel_gvt_driver_remove(dev_priv);\n"
        "\ti915_driver_modeset_remove(dev_priv);\n"
        "\tintel_power_domains_driver_remove(dev_priv);\n"
        "out_cleanup_hw:\n\ti915_driver_hw_remove(dev_priv);\n",
        "post-modeset rollback")
    return body


def transform(source: str) -> str:
    source = replace_between(
        source,
        "static void i915_driver_register(struct drm_i915_private *dev_priv)",
        "/**\n * i915_driver_unregister",
        register_changes,
    )
    source = replace_between(
        source, "int i915_driver_probe(struct pci_dev *pdev,",
        "void i915_driver_remove(struct drm_i915_private *i915)",
        probe_changes,
    )
    return source


def generate(tree: Path, output: Path) -> None:
    original = pinned_source(tree)
    revised = transform(original)
    patch = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), revised.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if not patch or "out_cleanup_registration:" not in patch:
        raise RuntimeError("missing registration rollback patch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patch)
    print("I915_REGISTER_FAILURE_PATCH_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generate(args.netbsd_tree, args.out)


if __name__ == "__main__":
    main()
