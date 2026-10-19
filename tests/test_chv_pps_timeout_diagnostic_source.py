#!/usr/bin/env python3
"""Frozen Linux/NetBSD PPS timeout diagnostic parity; source-only check.

Checks patch 0041 against real pinned C. A source test does not prove eDP
hardware timing, native NetBSD compilation or all-323 semantic closure.
"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import tempfile

NETBSD_SHA = "7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141"
LINUX_SHA = "f1f9c08347630a7ff9f7e5c9fb3e527d3db6ae81320b31519843b0ec0cc92866"
PATCH_SHA = "4eda6344f97d6e9a5d5c3677150878f9b008c376f9a387799c0bc3c82c3eeb45"
SOURCE_PATH = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
ORIGINAL = r'''	if (intel_de_wait_for_register(dev_priv, pp_stat_reg,
				       mask, value, 5000))
		DRM_ERROR("Panel status timeout: status %08x control %08x\n",
				I915_READ(pp_stat_reg),
				I915_READ(pp_ctrl_reg));

	DRM_DEBUG_KMS("Wait complete\n");'''
CORRECTED = r'''	if (intel_de_wait_for_register(dev_priv, pp_stat_reg,
				       mask, value, 5000)) {
		DRM_ERROR("Panel status timeout: status %08x control %08x\n",
				I915_READ(pp_stat_reg),
				I915_READ(pp_ctrl_reg));
		return;
	}

	DRM_DEBUG_KMS("Wait complete\n");'''


def require(ok, msg):
    if not ok:
        raise AssertionError("CHV_PPS_TIMEOUT_REFUSED: " + msg)


def function(source, name):
    tag = "static void " + name + "("
    require(source.count(tag) == 1, "function owner ambiguous: " + name)
    start = source.index(tag)
    brace = source.index("{", start)
    level = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            level += 1
        elif source[i] == "}":
            level -= 1
            if level == 0:
                return source[start:i+1]
    raise AssertionError("CHV_PPS_TIMEOUT_REFUSED: malformed function body")


def check(orig, linux, fixed):
    old = function(orig, "wait_panel_status")
    new = function(fixed, "wait_panel_status")
    upstream = function(linux, "wait_panel_status")
    require(old.count(ORIGINAL) == 1, "frozen NetBSD wait code changed")
    require(new.count(CORRECTED) == 1, "timeout must return before success")
    require(fixed == orig.replace(ORIGINAL, CORRECTED, 1),
            "patch touched C outside exact diagnosis-only change")
    require("poll_timeout_us(" in upstream and
            "10 * 1000, 5000 * 1000, true" in upstream,
            "pinned Linux poll interval or 5-second deadline changed")
    failed = upstream.index("if (ret) {")
    upstream_timeout = upstream.index("panel status timeout", failed)
    upstream_return = upstream.index("return;", upstream_timeout)
    upstream_success = upstream.index("Wait complete", upstream_return)
    require(failed < upstream_timeout < upstream_return < upstream_success,
            "Linux timeout/early-return source order changed")
    require("mask, value, 5000" in new and
            "DRM_DEBUG_KMS(\"Wait complete" in new,
            "NetBSD timeout budget or success logging changed")
    require("lockdep_assert_held(&dev_priv->pps_mutex)" in new,
            "NetBSD panel mutex ownership changed")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--netbsd", type=Path, required=True)
    a.add_argument("--linux", type=Path, required=True)
    a.add_argument("--patch", type=Path, required=True)
    opt = a.parse_args()
    sources = ((opt.netbsd, NETBSD_SHA), (opt.linux, LINUX_SHA),
               (opt.patch, PATCH_SHA))
    for p, expected in sources:
        require(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == expected,
                "frozen source/patch SHA mismatch: " + str(p))
    orig, linux = opt.netbsd.read_text(), opt.linux.read_text()
    with tempfile.TemporaryDirectory(prefix="chv-pps-frozen-") as d:
        root = Path(d)
        target = root / SOURCE_PATH
        target.parent.mkdir(parents=True)
        target.write_text(orig)
        for args in (["git", "apply", "--check", str(opt.patch)],
                     ["git", "apply", str(opt.patch)]):
            ret = subprocess.run(args, cwd=root, capture_output=True,
                                 text=True, timeout=15)
            require(ret.returncode == 0, ret.stderr)
        fixed = target.read_text()
        check(orig, linux, fixed)
        require(subprocess.run(
            ["git", "apply", "--reverse", "--check", str(opt.patch)],
            cwd=root, capture_output=True, timeout=15).returncode == 0,
            "patch cannot be reversed")
        require(subprocess.run(
            ["git", "apply", "--reverse", str(opt.patch)],
            cwd=root, capture_output=True, timeout=15).returncode == 0,
            "patch reverse failed")
        require(target.read_text() == orig, "original did not roundtrip")
        require(subprocess.run(
            ["git", "apply", "--reverse", "--check", str(opt.patch)],
            cwd=root, capture_output=True, timeout=15).returncode != 0,
            "duplicate reverse unexpectedly accepted")
    cases = (
        ("false_return_removed", CORRECTED.replace("\t\treturn;\n", "", 1)),
        ("false_error_removed", CORRECTED.replace(
            "DRM_ERROR(\"Panel status timeout", "DRM_DEBUG_KMS(\"Panel status timeout", 1)),
        ("wrong_timeout", CORRECTED.replace("mask, value, 5000", "mask, value, 500")),
        ("false_success_removed", CORRECTED.replace(
            'DRM_DEBUG_KMS("Wait complete\\n");', 'DRM_DEBUG_KMS("Maybe done\\n");')),
        ("false_mutex_removed", fixed.replace(
            "lockdep_assert_held(&dev_priv->pps_mutex);", "")),
    )
    for label, changed in cases:
        if label == "false_mutex_removed":
            mutant = changed
        else:
            mutant = fixed.replace(CORRECTED, changed, 1)
        require(mutant != fixed, "mutation does not alter source: " + label)
        try:
            check(orig, linux, mutant)
        except AssertionError:
            continue
        raise AssertionError("CHV_PPS_TIMEOUT_REFUSED: mutation passed " + label)
    print("CHV_PPS_TIMEOUT_FROZEN_NETBSD_LINUX_5_NEGATIVE_TESTS_PASS")
    print("Only diagnostic early-return parity; native HP C, panel hardware "
          "and complete 323 semantics NOT_VERIFIED")


if __name__ == "__main__":
    main()
