#!/usr/bin/env python3
"""Validate G08 Cherryview/eDP source trace patch on exact frozen NetBSD intel_dp.c.

Usage:
  python3 -B tests/test_i915_netbsd_g08_chv_trace_patch_source.py \
      --netbsd-intel-dp /path/to/pinned/NetBSD/src/sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c

This is a source-only test, never a NetBSD kernel compile or physical boot.
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
PATCH = ROOT / "patches/0039-netbsd11-i915-chv-edp-aux-phase-trace.patch"
FROZEN_SHA256 = "7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141"
PHASES = {
    "G08.A1": "AUX_INIT",
    "G08.A2": "EDP_DPCD",
    "G08.C1": "CHV_PHY",
    "G08.C2": "CHV_PLL",
    "G08.P1": "EDP_PANEL",
    "G08.L1": "LINK_TRAIN",
    "G08.L2": "LINK_STOP",
}
GUARD = re.compile(
    r'#ifdef __NetBSD__\n'
    r'\tprintf\("\[I915 G08\.[A-Z][12]\] [^"\n]+\\n"(?:, has_dpcd)?\);\n'
    r'#endif\n'
)


def command(*args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True,
                            text=True, timeout=15, check=False)
    if result.returncode:
        raise AssertionError(
            "command failed: " + repr(args) + ": " + result.stderr[-500:]
        )


def test(source_file):
    original = source_file.read_bytes()
    if hashlib.sha256(original).hexdigest() != FROZEN_SHA256:
        raise AssertionError("NetBSD intel_dp.c drift: exact frozen SHA256 required")
    patch = PATCH.read_bytes()
    if (not patch.startswith(("--" + "- a/" + REL + "\n+++ b/" + REL + "\n").encode())
            or patch.count(b"+\tprintf(") != 14):
        raise AssertionError("unexpected i915 G08 patch target or message count")
    with tempfile.TemporaryDirectory(prefix="hp-i915-g08-trace-") as tmp:
        root = Path(tmp)
        target = root / REL
        target.parent.mkdir(parents=True)
        target.write_bytes(original)
        command("git", "apply", "--check", str(PATCH), cwd=root)
        command("git", "apply", str(PATCH), cwd=root)
        changed = target.read_bytes()
        decoded = changed.decode("utf-8")
        clean, removed = GUARD.subn("", decoded)
        if removed != 14 or clean.encode("utf-8") != original:
            raise AssertionError("modified native driver flow or missing guarded traces")
        entries = []
        for tag, label, edge, extra in re.findall(
            r'\tprintf\("\[I915 (G08\.[A-Z][12])\] ([A-Z_]+)'
            r' (BEGIN|END)( success=%d)?\\n"(?:, has_dpcd)?\);',
            decoded,
        ):
            if tag not in PHASES or label != PHASES[tag]:
                raise AssertionError("unknown phase/label in kernel trace")
            if bool(extra) != (tag == "G08.A2" and edge == "END"):
                raise AssertionError("incorrect DPCD result marker")
            entries.append((tag, edge))
        if len(entries) != 14 or Counter(entries) != Counter(
                {(phase, edge): 1 for phase in PHASES for edge in ("BEGIN", "END")}):
            raise AssertionError("incomplete, repeated or unpaired i915 trace")
        # The frozen Cherryview PCI display path does call intel_enable_dp,
        # so the panel/link markers represent that real hardware sequence.
        if ("chv_pre_enable_dp(struct intel_encoder *encoder" not in decoded
                or "intel_enable_dp(encoder, pipe_config, conn_state);" not in decoded):
            raise AssertionError("Cherryview pre-enable path was not preserved")
        refused = subprocess.run(["git", "apply", "--check", str(PATCH)],
                                 cwd=root, capture_output=True, text=True)
        if refused.returncode == 0:
            raise AssertionError("duplicate patch application unexpectedly allowed")
        if source_file.read_bytes() != original:
            raise AssertionError("read-only pinned NetBSD source changed")
    print("NETBSD_I915_G08_CHV_EDP_7_PHASES_14_GUARDED_TRACES_PASS")
    print("Limit: source-only patch, not native NetBSD kernel/link/boot")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-intel-dp", type=Path, required=True)
    test(parser.parse_args().netbsd_intel_dp)
