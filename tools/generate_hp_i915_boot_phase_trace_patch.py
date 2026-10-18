#!/usr/bin/env python3
"""Generate a pinned NetBSD-only i915 G01-G09 attach trace instrumentation patch.

This generates a PATCH FILE only; never changes the input source or HP kernel.
It instruments already existing call boundaries; it is not GPU/KMS functional
parity and cannot capture a non-dumpable pre-filesystem hard lockup to disk.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
REL = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"
PROBE = "int i915_driver_probe(struct pci_dev *pdev, const struct pci_device_id *ent)"
MODESET = "static int i915_driver_modeset_probe(struct drm_i915_private *i915)"

# Call boundaries in *this* frozen NetBSD source, not guessed linux-mainline
# functions. Later eDP/AUX, powerwell and wsdisplay substeps need their own
# verified owner instrumentation; these stage markers don't pretend otherwise.
PHASES = (
    ("probe", "G01", "pci_attach", "\tret = drm_pci_attach(&dev_priv->drm, pdev);\n", True),
    ("probe", "G02", "early_probe", "\tret = i915_driver_early_probe(dev_priv);\n", True),
    ("probe", "G03", "mmio_probe", "\tret = i915_driver_mmio_probe(dev_priv);\n", True),
    ("probe", "G04", "hardware_ggtt_probe", "\tret = i915_driver_hw_probe(dev_priv);\n", True),
    ("modeset", "G05", "bios_vbt_init", "\tintel_bios_init(i915);\n", False),
    ("modeset", "G06", "power_domains_init_hw", "\tintel_power_domains_init_hw(i915, false);\n", False),
    ("modeset", "G07", "irq_install", "\tret = intel_irq_install(i915);\n", True),
    ("modeset", "G08", "modeset_init", "\tret = intel_modeset_init(i915);\n", True),
    ("modeset", "G09", "fbdev_init", "\tret = intel_fbdev_init(&i915->drm);\n", True),
)


def function_bounds(source: str, signature: str) -> tuple[int, int]:
    if source.count(signature) != 1:
        raise RuntimeError("pinned NetBSD function signature changed: " + signature)
    start = source.index(signature)
    end = source.find("\n}\n", start)
    if end == -1:
        raise RuntimeError("pinned NetBSD function closing brace absent")
    return start, end + len("\n}\n")


def phase(source: str, marker: str, label: str,
          anchor: str, reports_rc: bool) -> str:
    if source.count(anchor) != 1:
        raise RuntimeError("expected exactly one call boundary " + marker)
    start = (
        '#ifdef __NetBSD__\n'
        '\tprintf("[I915 ' + marker + '] ' + label + ' BEGIN\\n");\n'
        '#endif\n'
    )
    if reports_rc:
        end = (
            '#ifdef __NetBSD__\n'
            '\tprintf("[I915 ' + marker + '] ' + label +
            ' END ret=%d\\n", ret);\n'
            '#endif\n'
        )
    else:
        end = (
            '#ifdef __NetBSD__\n'
            '\tprintf("[I915 ' + marker + '] ' + label + ' END\\n");\n'
            '#endif\n'
        )
    return source.replace(anchor, start + anchor + end, 1)


def transform(source: str) -> str:
    if "[I915 G01]" in source or "[I915 G09]" in source:
        raise RuntimeError("trace instrumentation already present")
    original = source
    for scope, signature in (("probe", PROBE), ("modeset", MODESET)):
        a, b = function_bounds(source, signature)
        body = source[a:b]
        for s, marker, label, anchor, with_ret in PHASES:
            if scope != s:
                continue
            if s == "probe" and marker == "G01":
                if body.count("#ifdef __NetBSD__\n\tret = drm_pci_attach") != 1:
                    raise RuntimeError("NetBSD-only pci_attach anchor absent")
            body = phase(body, marker, label, anchor, with_ret)
        source = source[:a] + body + source[b:]
    for _, marker, label, anchor, _ in PHASES:
        if source.count("[I915 " + marker + "]") != 2:
            raise RuntimeError("missing paired BEGIN/END marker " + marker)
        if source.count(anchor) != original.count(anchor):
            raise RuntimeError("source call count changed at " + marker)
    return source


def pinned_source(tree: Path) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN:
        raise RuntimeError("refusing non-frozen NetBSD revision " + head)
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + REL], text=True)
    if (tree / REL).read_text() != committed:
        raise RuntimeError("refusing dirty or missing pinned NetBSD i915_drv.c")
    return committed


def generate(tree: Path, output: Path) -> str:
    original = pinned_source(tree)
    changed = transform(original)
    patch = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        changed.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if not patch or patch.count("+\tprintf(") != 18:
        raise RuntimeError("expected nine paired i915 messages")
    if output.exists() or output.is_symlink():
        raise RuntimeError("refuse overwrite of existing patch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patch)
    return patch


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--netbsd-tree", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    result = generate(args.netbsd_tree, args.out)
    print("I915_PINNED_NETBSD_G01_G09_TRACE_PATCH_SOURCE_OK lines=" +
          str(len(result.splitlines())))


if __name__ == "__main__":
    main()
