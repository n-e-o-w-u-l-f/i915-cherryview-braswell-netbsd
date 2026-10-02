#!/usr/bin/env python3
"""Pin the DRM registration failure assumptions behind i915 candidate 0008.

Source-only contract test: this checks which callbacks can run if the older
NetBSD drm_dev_register() returns an error, then verifies that the candidate
retains the pinned Linux i915 rollback sequence. This is NOT a native NetBSD
object build, a dynamic DRM rollback test or hardware verification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import runpy
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_I915 = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"
NETBSD_DRM = "sys/external/bsd/drm2/dist/drm/drm_drv.c"
NETBSD_CONNECTOR = "sys/external/bsd/drm2/dist/drm/drm_connector.c"
LINUX_I915 = "drivers/gpu/drm/i915/i915_driver.c"


def pinned_file(tree: Path, revision: str, relative: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != revision:
        raise RuntimeError(f"{tree}: expected {revision}; got {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative], text=True
    )
    if (tree / relative).read_text() != committed:
        raise RuntimeError(f"dirty pinned input: {relative}")
    return committed


def section(text: str, start: str, stop: str) -> str:
    if text.count(start) != 1:
        raise AssertionError(f"ambiguous or missing section: {start}")
    i = text.index(start)
    j = text.index(stop, i)
    return text[i:j]


def ordered(text: str, *needles: str) -> None:
    positions = [text.index(needle) for needle in needles]
    assert positions == sorted(positions), "ownership order changed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-tree", type=Path, required=True)
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    args = parser.parse_args()

    linux = pinned_file(args.linux_tree, LINUX_PIN, LINUX_I915)
    netbsd = pinned_file(args.netbsd_tree, NETBSD_PIN, NETBSD_I915)
    core = pinned_file(args.netbsd_tree, NETBSD_PIN, NETBSD_DRM)
    connector = pinned_file(args.netbsd_tree, NETBSD_PIN, NETBSD_CONNECTOR)

    driver = section(netbsd, "static struct drm_driver driver = {", "\n};")
    assert re.search(r"(?m)^\s*\.load\s*=", driver) is None
    assert "DRIVER_MODESET" in driver
    assert "DRIVER_LEGACY" not in driver

    minor = section(core, "static int drm_minor_register(", "static void drm_minor_unregister(")
    assert "#ifndef __NetBSD__" in minor
    assert "ret = device_add(minor->kdev);" in minor
    assert "return 0;" in minor

    compat = section(core, "static int create_compat_control_link(", "static void remove_compat_control_link(")
    assert "if (!name)\n\t\treturn -ENOMEM;" in compat
    assert "#ifdef __NetBSD__" in compat
    assert "ret = 0;" in compat

    registration = section(core, "int drm_dev_register(", "EXPORT_SYMBOL(drm_dev_register);")
    ordered(registration,
            "ret = drm_minor_register(dev, DRM_MINOR_RENDER);",
            "ret = drm_minor_register(dev, DRM_MINOR_PRIMARY);",
            "ret = create_compat_control_link(dev);",
            "dev->registered = true;",
            "if (dev->driver->load)",
            "drm_modeset_register_all(dev);")
    ordered(registration, "err_minors:", "remove_compat_control_link(dev);",
            "drm_minor_unregister(dev, DRM_MINOR_PRIMARY);",
            "drm_minor_unregister(dev, DRM_MINOR_RENDER);")
    assert "return ret;" in registration

    unregister = section(core, "void drm_dev_unregister(", "EXPORT_SYMBOL(drm_dev_unregister);")
    assert "if (drm_core_check_feature(dev, DRIVER_LEGACY))" in unregister
    assert "drm_modeset_unregister_all(dev);" in unregister
    assert "drm_minor_unregister(dev, DRM_MINOR_PRIMARY);" in unregister
    assert "drm_minor_unregister(dev, DRM_MINOR_RENDER);" in unregister

    connector_unregister = section(
        connector, "void drm_connector_unregister(", "EXPORT_SYMBOL(drm_connector_unregister);")
    assert "connector->registration_state != DRM_CONNECTOR_REGISTERED" in connector_unregister

    linux_register = section(
        linux, "static int i915_driver_register(", "/**\n * i915_driver_unregister")
    ordered(linux_register,
            "i915_gem_driver_register(dev_priv);",
            "i915_pmu_register(dev_priv);",
            "ret = drm_dev_register(&dev_priv->drm, 0);",
            "drm_dev_unregister(&dev_priv->drm);",
            "i915_pmu_unregister(dev_priv);",
            "i915_gem_driver_unregister(dev_priv);")
    netbsd_register = section(
        netbsd, "static void i915_driver_register(", "/**\n * i915_driver_unregister")
    assert "I915_WRITE(vgtif_reg(display_ready), VGT_DRV_DISPLAY_READY);" in netbsd_register

    generator = runpy.run_path(
        str(Path(__file__).resolve().parents[1] /
            "tools/generate_register_failure_patch.py")
    )
    transformed = generator["transform"](netbsd)
    patched = section(
        transformed, "static int i915_driver_register(", "/**\n * i915_driver_unregister")
    ordered(patched,
            "i915_gem_driver_register(dev_priv);",
            "i915_pmu_register(dev_priv);",
            "ret = drm_dev_register(dev, 0);",
            "drm_dev_unregister(dev);",
            "i915_pmu_unregister(dev_priv);",
            "i915_gem_driver_unregister(dev_priv);",
            "return ret;")
    probe = section(transformed, "int i915_driver_probe(", "void i915_driver_remove(")
    assert "drm_atomic_helper_shutdown(&dev_priv->drm);" not in probe
    assert probe.count("out_cleanup_memory:") == 1
    assert probe.count("i915_gem_driver_release(dev_priv);") == 1

    print("I915_PINNED_DRM_REGISTRATION_SOURCE_CONTRACT_OK")


if __name__ == "__main__":
    main()
