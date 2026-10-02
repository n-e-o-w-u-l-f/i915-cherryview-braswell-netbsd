#!/usr/bin/env python3
"""Pinned eDP fixed-mode and failed-connector EDID cleanup regression.

Extracts actual NetBSD intel_edp_init_connector() fallback/error C fragments,
compiles them with strict host C11/ASan/UBSan and proves that the unpatched
missing-mode path incorrectly succeeds (negative control). Also compares the
published candidate 0011 byte-for-byte against the Python pinned generator,
checks Linux's missing-mode decision and the NetBSD EDID ownership convention,
and executes git apply --check against each supplied genuine worktree.

This is host-isolated source verification, not native NetBSD compilation or
a diagnosis of the HP's historical black-screen failure.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import resource
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / "tools/generate_edp_fixed_mode_patch.py"))
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
LINUX_DP = "drivers/gpu/drm/i915/display/intel_dp.c"
NETBSD_CONNECTOR = "sys/external/bsd/drm2/dist/drm/i915/display/intel_connector.c"
NETBSD_PANEL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_panel.c"

PRELUDE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

struct drm_display_mode { int hdisplay; };
struct drm_device { struct { int mutex; } mode_config; };
struct intel_connector { void *edid; };
struct intel_dp { int panel_vdd_work; };
typedef int intel_wakeref_t;

static struct drm_display_mode edid_mode = {1366};
static struct drm_display_mode vbt_mode = {1024};
static struct drm_device drm;
static struct intel_dp dp;
static int vbt_available, vbt_calls, unlocks, messages, canceled;
static int vdd_off_calls, frees;
static void *last_freed;

static struct drm_display_mode *
intel_panel_vbt_fixed_mode(struct intel_connector *connector)
{
    assert(connector != NULL);
    vbt_calls++;
    return vbt_available ? &vbt_mode : NULL;
}
static void mutex_unlock(int *lock)
{
    assert(lock == &drm.mode_config.mutex);
    unlocks++;
}
static void cancel_delayed_work_sync(int *work)
{
    assert(work == &dp.panel_vdd_work);
    canceled++;
}
static void edp_panel_vdd_off_sync(struct intel_dp *intel_dp)
{
    assert(intel_dp == &dp);
    vdd_off_calls++;
}
static void kfree(void *pointer)
{
    assert(pointer != NULL);
    frees++;
    last_freed = pointer;
}
#define DRM_INFO(...) (messages++)
#define IS_ERR_OR_NULL(pointer) \
    ((pointer) == NULL || (uintptr_t)(pointer) >= UINTPTR_MAX - 4095)
#define with_pps_lock(intel_dp, wakeref) \
    for (int pps_once = ((void)(intel_dp), (void)(wakeref), 1); \
         pps_once; pps_once = 0)
"""

MAIN = r"""
static void reset(void)
{
    vbt_available = vbt_calls = unlocks = messages = canceled = 0;
    vdd_off_calls = frees = 0;
    last_freed = NULL;
}

int main(void)
{
    struct intel_connector connector = {0};
    void *edid = (void *)(uintptr_t)0x5000;
    void *invalid_edid = (void *)(intptr_t)-2;

    reset();
    connector.edid = edid;
    assert(run_edp(&connector, true, false));
    assert(connector.edid == edid);
    assert(unlocks == 1 && vbt_calls == 0);
    assert(messages == 0 && canceled == 0 && frees == 0);

    reset();
    vbt_available = 1;
    connector.edid = invalid_edid;
    assert(run_edp(&connector, false, false));
    assert(vbt_calls == 1 && unlocks == 1);
    assert(messages == 0 && canceled == 0 && frees == 0);

    reset();
    connector.edid = edid;
    assert(!run_edp(&connector, false, false));
    assert(vbt_calls == 1 && unlocks == 1 && messages == 1);
    assert(canceled == 1 && vdd_off_calls == 1);
    assert(frees == 1 && last_freed == edid && connector.edid == NULL);

    reset();
    connector.edid = invalid_edid;
    assert(!run_edp(&connector, false, false));
    assert(messages == 1 && canceled == 1 && vdd_off_calls == 1);
    assert(frees == 0 && connector.edid == NULL);

    reset();
    connector.edid = NULL;
    assert(!run_edp(&connector, false, false));
    assert(messages == 1 && canceled == 1 && vdd_off_calls == 1);
    assert(frees == 0 && connector.edid == NULL);

    reset();
    connector.edid = NULL;
    assert(!run_edp(&connector, false, true));
    assert(vbt_calls == 0 && unlocks == 0);
    assert(messages == 0 && canceled == 1 && vdd_off_calls == 1);

    puts("I915_EDP_FIXED_MODE_HOST_C_OK");
    return 0;
}
"""

NEGATIVE_MAIN = r"""
int main(void)
{
    struct intel_connector connector = {0};
    /* Original fragment has no DRM_INFO, retain the strict warning gate. */
    (void)messages;
    (void)kfree;
    /* With no EDID mode and no VBT, the original source returns true. */
    assert(!run_edp(&connector, false, false));
    return 0;
}
"""


def committed_source(tree: Path, pin: str, path: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != pin:
        raise RuntimeError(f"wrong pinned source revision: {head}")
    source = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + path], text=True
    )
    if (tree / path).read_text() != source:
        raise RuntimeError(f"dirty pinned source: {path}")
    return source


def connector_fragment(source: str) -> str:
    begin = source.index("static bool intel_edp_init_connector(")
    end = source.index("static void intel_dp_modeset_retry_work_fn(", begin)
    return source[begin:end]


def extracted_wrapper(function: str) -> str:
    begin = function.index("\t/* fallback to VBT if available for eDP */")
    after = function.index(
        "\tif (IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) {",
        begin,
    )
    failure = function.index("out_vdd_off:\n", after)
    fallback = function[begin:after]
    unwind = function[failure:]
    return (
        "static bool run_edp(struct intel_connector *intel_connector, "
        "bool has_edid_mode, bool force_dpcd_failure)\n"
        "{\n"
        "\tstruct drm_display_mode *fixed_mode = "
        "has_edid_mode ? &edid_mode : NULL;\n"
        "\tstruct drm_device *dev = &drm;\n"
        "\tstruct intel_dp *intel_dp = &dp;\n"
        "\tintel_wakeref_t wakeref = 0;\n"
        "\tif (force_dpcd_failure)\n"
        "\t\tgoto out_vdd_off;\n"
        + fallback +
        "\treturn true;\n\n"
        + unwind
    )


def build_run(source: str, tmp: Path, name: str, main: str,
              sanitizers: str) -> subprocess.CompletedProcess[str]:
    c = tmp / (name + ".c")
    exe = tmp / name
    c.write_text(PRELUDE + "\n" + source + "\n" + main)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=" + sanitizers, "-fno-omit-frame-pointer",
         str(c), "-o", str(exe)], check=True,
    )
    if name == "negative":
        def no_core_dump() -> None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return subprocess.run(
            [str(exe)], capture_output=True, text=True, check=False,
            preexec_fn=no_core_dump,
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
    linux = committed_source(args.linux_tree, LINUX_PIN, LINUX_DP)
    connector = committed_source(
        args.netbsd_tree, TOOL["NETBSD_PIN"], NETBSD_CONNECTOR
    )
    panel = committed_source(args.netbsd_tree, TOOL["NETBSD_PIN"], NETBSD_PANEL)
    assert "if (!intel_panel_preferred_fixed_mode(connector)) {" in linux
    assert "goto out_vdd_off;" in linux
    assert "if (!IS_ERR_OR_NULL(intel_connector->edid))" in connector
    assert "kfree(intel_connector->edid);" in connector
    assert "connector = kzalloc(sizeof(*connector), GFP_KERNEL);" in connector
    assert "if (!dev_priv->vbt.lfp_lvds_vbt_mode)" in panel

    original_fn = connector_fragment(original)
    revised_fn = connector_fragment(transformed)
    assert revised_fn.index("if (!fixed_mode) {") < revised_fn.index(
        "register_reboot_notifier(&intel_dp->edp_notifier);"
    )
    assert revised_fn.count("intel_connector->edid = NULL;") == 1
    assert revised_fn.index("edp_panel_vdd_off_sync(intel_dp);") < \
        revised_fn.index("if (!IS_ERR_OR_NULL(intel_connector->edid))") < \
        revised_fn.rindex("return false;")
    assert original_fn.count("intel_connector->edid = NULL;") == 0

    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        generated = tmp / "0011-regenerated.patch"
        TOOL["generate"](args.netbsd_tree, generated)
        if generated.read_bytes() != args.patch.read_bytes():
            raise AssertionError("candidate 0011 differs from pinned generator")
        print("I915_0011_GENERATOR_BYTE_MATCH_OK", flush=True)

        passed = build_run(
            extracted_wrapper(revised_fn), tmp, "positive", MAIN,
            "address,undefined",
        )
        print(passed.stdout.strip(), flush=True)
        failed = build_run(
            extracted_wrapper(original_fn), tmp, "negative", NEGATIVE_MAIN,
            "undefined",
        )
        if failed.returncode == 0 or "Assertion" not in failed.stderr:
            raise AssertionError("original eDP no-fixed-mode path did not fail")
        print("I915_0011_UNPATCHED_NEGATIVE_CONTROL_OK", flush=True)

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("overlay must differ from frozen NetBSD source")
        targets.append(args.overlay_tree)
    for tree in targets:
        subprocess.run(
            ["git", "-C", str(tree), "apply", "--check", str(args.patch)],
            check=True,
        )
    print("I915_0011_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"),
          flush=True)


if __name__ == "__main__":
    main()
