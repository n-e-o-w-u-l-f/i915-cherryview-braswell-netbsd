#!/usr/bin/env python3
"""Pinned Cherryview DISPLAY_PHY_CONTROL shadow / power-well sync gate.

Candidate 0015 is the byte-identical, existing Legion staged
chv-phy-powerwell-sync.patch. Frozen Linux builds the PHY_CONTROL shadow
in chv_phy_control_init(), defers the write and registers
chv_pipe_power_well_sync_hw() as the pipe power-well .sync_hw callback.
Frozen NetBSD writes during init and uses the noop callback.

Check exact frozen Linux/NetBSD source semantics and the exact result of
real git apply to a disposable file. The optional distinct Legion overlay
already includes 0015 and must reverse-apply cleanly; never modify it.
Host-only C callback test is NOT a NetBSD object build/HP runtime proof.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile
from sanitizer_support import run_sanitized

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_display_power.c"
LINUX_POWER = "drivers/gpu/drm/i915/display/intel_display_power.c"
LINUX_WELLS = "drivers/gpu/drm/i915/display/intel_display_power_well.c"

OLD_SYNC = (
    "static const struct i915_power_well_ops chv_pipe_power_well_ops = {\n"
    "\t.sync_hw = i9xx_power_well_sync_hw_noop,\n"
)
NEW_SYNC = OLD_SYNC.replace(
    "i9xx_power_well_sync_hw_noop", "chv_pipe_power_well_sync_hw"
)
FUNCTION_INSERT = (
    "static void chv_pipe_power_well_sync_hw(struct drm_i915_private *dev_priv,\n"
    "\t\t\t\t\tstruct i915_power_well *power_well)\n"
    "{\n"
    "\tI915_WRITE(DISPLAY_PHY_CONTROL, dev_priv->chv_phy_control);\n"
    "}\n\n"
)
FUNCTION_AFTER = "static void chv_pipe_power_well_enable("
INIT_OLD = (
    "\tI915_WRITE(DISPLAY_PHY_CONTROL, dev_priv->chv_phy_control);\n\n"
    '\tDRM_DEBUG_KMS("Initial PHY_CONTROL=0x%08x\\n",\n'
    "\t\t      dev_priv->chv_phy_control);\n"
    "}\n"
)
INIT_NEW = (
    '\tDRM_DEBUG_KMS("Initial PHY_CONTROL=0x%08x\\n",\n'
    "\t\t      dev_priv->chv_phy_control);\n\n"
    "\t/* Defer application of initial phy_control to enabling the powerwell */\n"
    "}\n"
)

PRELUDE = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
struct drm_i915_private { u32 chv_phy_control; };
struct i915_power_well { int unused; };
#define DISPLAY_PHY_CONTROL 0x600d4u
static unsigned int writes;
static u32 last_register, last_value;
static void record_write(u32 reg, u32 value)
{
    writes++;
    last_register = reg;
    last_value = value;
}
#define I915_WRITE(reg, value) record_write((reg), (value))
"""
MAIN = r"""
int main(void)
{
    struct drm_i915_private i915 = { .chv_phy_control = 0x31415926u };
    struct i915_power_well power_well = {0};

    /* The init stage only prepares the shadow. The registered callback
       applies it exactly when the caller synchronizes the power well. */
    assert(writes == 0);
    chv_pipe_power_well_sync_hw(&i915, &power_well);
    assert(writes == 1 && last_register == DISPLAY_PHY_CONTROL);
    assert(last_value == 0x31415926u);

    i915.chv_phy_control = 0x55aa1234u;
    chv_pipe_power_well_sync_hw(&i915, &power_well);
    assert(writes == 2 && last_value == 0x55aa1234u);
    puts("I915_0015_PINNED_POWERWELL_SYNC_HOST_C_OK");
    return 0;
}
"""


def pinned(tree: Path, sha: str, rel: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != sha:
        raise RuntimeError(f"wrong pinned revision for {tree}: {head}")
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + rel], text=True,
    )
    if (tree / rel).read_text() != committed:
        raise RuntimeError("dirty/missing pinned source: " + rel)
    return committed


def unique(source: str, before: str, after: str, description: str) -> str:
    if source.count(before) != 1:
        raise AssertionError("changed source anchor: " + description)
    return source.replace(before, after, 1)


def one_function(source: str, first: str) -> str:
    if source.count(first) != 1:
        raise AssertionError("missing/duplicate function " + first)
    start = source.index(first)
    return source[start:source.index("\n}\n", start) + 3]


def transform(original: str) -> str:
    if "static void chv_pipe_power_well_sync_hw(" in original:
        raise AssertionError("unexpected callback already present in frozen source")
    changed = unique(original, FUNCTION_AFTER, FUNCTION_INSERT + FUNCTION_AFTER,
                     "callback insertion before pipe power-well enable")
    changed = unique(changed, OLD_SYNC, NEW_SYNC,
                     "Cherryview power-well sync callback")
    begin = "static void chv_phy_control_init("
    end = "static void vlv_cmnlane_wa("
    init = changed[changed.index(begin):changed.index(end, changed.index(begin))]
    if init.count(INIT_OLD) != 1:
        raise AssertionError("old PHY_CONTROL write is not in init")
    return changed.replace(init, init.replace(INIT_OLD, INIT_NEW, 1), 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--linux-tree", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path, default=None)
    args = parser.parse_args()

    frozen = pinned(args.netbsd_tree, NETBSD_PIN, NETBSD_REL)
    l_power = pinned(args.linux_tree, LINUX_PIN, LINUX_POWER)
    l_wells = pinned(args.linux_tree, LINUX_PIN, LINUX_WELLS)
    l_init = one_function(l_power, "static void chv_phy_control_init(")
    l_sync = one_function(l_wells, "static void chv_pipe_power_well_sync_hw(")
    assert "display->power.chv_phy_control =" in l_init
    assert "DISPLAY_PHY_CONTROL" in l_init
    assert "intel_de_write(display, DISPLAY_PHY_CONTROL," not in l_init
    assert "Defer application of initial phy_control to enabling the powerwell" in l_init
    assert "intel_de_write(display, DISPLAY_PHY_CONTROL," in l_sync
    assert "display->power.chv_phy_control);" in l_sync
    l_ops = l_wells[l_wells.index("const struct i915_power_well_ops chv_pipe_power_well_ops = {"):]
    assert ".sync_hw = chv_pipe_power_well_sync_hw," in l_ops.split("};", 1)[0]

    revised = transform(frozen)
    init = one_function(revised, "static void chv_phy_control_init(")
    assert "I915_WRITE(DISPLAY_PHY_CONTROL, dev_priv->chv_phy_control);" not in init
    assert "Defer application of initial phy_control to enabling the powerwell" in init
    ops = revised[revised.index(
        "static const struct i915_power_well_ops chv_pipe_power_well_ops = {"):]
    assert ".sync_hw = chv_pipe_power_well_sync_hw," in ops.split("};", 1)[0]
    callback = one_function(revised, "static void chv_pipe_power_well_sync_hw(")
    assert callback.count("I915_WRITE(DISPLAY_PHY_CONTROL, dev_priv->chv_phy_control);") == 1

    patch = args.patch.resolve(strict=True)
    subprocess.run(
        ["git", "-C", str(args.netbsd_tree), "apply", "--check", str(patch)],
        check=True,
    )
    with tempfile.TemporaryDirectory() as name:
        scratch = Path(name)
        output = scratch / NETBSD_REL
        output.parent.mkdir(parents=True)
        output.write_text(frozen)
        subprocess.run(["git", "-C", str(scratch), "apply", str(patch)],
                       check=True)
        if output.read_text() != revised:
            raise AssertionError("0015 published patch differs from pinned source transform")
        print("I915_0015_FROZEN_EXACT_PATCH_TRANSFORM_OK", flush=True)

        source = scratch / "sync_test.c"
        binary = scratch / "sync_test"
        source.write_text(PRELUDE + "\n" + callback + "\n" + MAIN)
        # power_well is an unused framework callback argument in BOTH
        # pinned NetBSD/Linux implementations; keep all other warnings fatal.
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-pedantic", "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer", str(source), "-o", str(binary),
        ], check=True)
        run_sanitized(binary)

    if args.overlay_tree is not None:
        overlay = args.overlay_tree.resolve(strict=True)
        if overlay == args.netbsd_tree.resolve():
            raise RuntimeError("overlay must be a distinct genuine NetBSD checkout")
        if (overlay / NETBSD_REL).read_text() != revised:
            raise AssertionError("existing staged power-well file differs from 0015")
        subprocess.run(["git", "-C", str(overlay),
                        "apply", "--reverse", "--check", str(patch)], check=True)
        print("I915_0015_EXISTING_OVERLAY_REVERSE_APPLY_OK", flush=True)
    else:
        print("I915_0015_FROZEN_ONLY_OVERLAY_UNVERIFIED", flush=True)


if __name__ == "__main__":
    main()
