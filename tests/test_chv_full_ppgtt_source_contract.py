#!/usr/bin/env python3
"""Verify the staged Cherryview 32-bit full PPGTT against pinned Linux.

Frozen NetBSD 03d918f6 selects aliasing PPGTT for CHV. Pinned Linux
fd179f8a selects full 32-bit PPGTT and programs all four 3-level PDP
entries before the execlists request's usual invalidate. The optional,
genuine, separate NetBSD overlay must contain this Linux-derived
implementation, preserving the existing frozen sources unmodified.

Host SOURCE contract only. This does not certify C object compilation,
GPU ring execution, the complete memory-management port, or the HP display.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NET_ROOT = "sys/external/bsd/drm2/dist/drm/i915/"
LIN_ROOT = "drivers/gpu/drm/i915/"


def committed(tree: Path, sha: str, path: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != sha:
        raise RuntimeError("reference commit mismatch: " + path)
    source = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + path], text=True,
    )
    if (tree / path).read_text() != source:
        raise RuntimeError("frozen reference source is dirty: " + path)
    return source


def function(src: str, name: str) -> str:
    anchor = "static int " + name + "("
    if src.count(anchor) != 1:
        raise AssertionError("source function missing or non-unique: " + name)
    start = src.index(anchor)
    return src[start:src.index("\n}\n", start) + 3]


def chv_info(src: str) -> str:
    anchor = "static const struct intel_device_info chv_info = {"
    if src.count(anchor) != 1:
        raise AssertionError("CHV device info source drift")
    start = src.index(anchor)
    return src[start:src.index("\n};", start) + 3]


def normalized(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"\s+", "", src)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", required=True, type=Path)
    ap.add_argument("--linux-tree", required=True, type=Path)
    ap.add_argument("--overlay-tree", type=Path, default=None)
    args = ap.parse_args()
    net = args.netbsd_tree.resolve(strict=True)
    lin = args.linux_tree.resolve(strict=True)
    if net == lin:
        raise RuntimeError("NetBSD and Linux reference trees must differ")

    old_pci = committed(net, NETBSD_PIN, NET_ROOT + "i915_pci.c")
    old_lrc = committed(net, NETBSD_PIN, NET_ROOT + "gt/intel_lrc.c")
    gtt = committed(net, NETBSD_PIN, NET_ROOT + "gt/intel_gtt.h")
    regs = committed(net, NETBSD_PIN, NET_ROOT + "i915_reg.h")
    new_pci = committed(lin, LINUX_PIN, LIN_ROOT + "i915_pci.c")
    linux_lrc = committed(
        lin, LINUX_PIN, LIN_ROOT + "gt/intel_execlists_submission.c"
    )
    if ".ppgtt_type = INTEL_PPGTT_ALIASING," not in chv_info(old_pci):
        raise AssertionError("frozen NetBSD CHV PPGTT policy changed")
    if ".ppgtt_size = 32," not in chv_info(old_pci):
        raise AssertionError("frozen NetBSD CHV 32-bit aperture changed")
    if ".__runtime.ppgtt_type = INTEL_PPGTT_FULL," not in chv_info(new_pci):
        raise AssertionError("pinned Linux CHV full PPGTT policy changed")
    if ".__runtime.ppgtt_size = 32," not in chv_info(new_pci):
        raise AssertionError("pinned Linux CHV PPGTT aperture changed")
    assert "emit_pdps(" not in old_lrc
    for symbol in (
        "i915_page_dir_dma_addr(", "i915_vm_is_4lvl(",
        "i915_vm_to_ppgtt(", "GEN8_3LVL_PDPES",
    ):
        if symbol not in gtt:
            raise AssertionError("missing NetBSD PPGTT helper: " + symbol)
    for reg in ("GEN8_RING_PDP_UDW(", "GEN8_RING_PDP_LDW("):
        if reg not in regs:
            raise AssertionError("NetBSD ring-PDP register macro missing: " + reg)
    if re.search(r"(?m)^#define\s+GEN8_3LVL_PDPES\s+4(?:\s|$)",
                 gtt) is None:
        raise AssertionError("pinned four-PDP-entry contract changed")

    upstream_pdp = normalized(function(linux_lrc, "emit_pdps"))
    upstream_alloc = normalized(
        function(linux_lrc, "execlists_request_alloc")
    )
    if upstream_pdp.count("intel_ring_advance(rq,cs);") != 3:
        raise AssertionError("pinned Linux ring-advance sequence changed")
    duplicate_final = (
        "intel_ring_advance(rq,cs);"
        "intel_ring_advance(rq,cs);return0;"
    )
    if upstream_pdp.count(duplicate_final) != 1:
        raise AssertionError("pinned Linux's redundant final advance changed")
    expected_pdp = upstream_pdp.replace(
        duplicate_final, "intel_ring_advance(rq,cs);return0;", 1
    )
    if "if(!i915_vm_is_4lvl(request->context->vm))" not in upstream_alloc:
        raise AssertionError("Linux 3-level PDP request gate missing")
    if "emit_pdps(request)" not in upstream_alloc:
        raise AssertionError("Linux 3-level PDP emission missing")
    if normalized(function(old_lrc, "execlists_request_alloc")) == upstream_alloc:
        raise AssertionError("frozen NetBSD is unexpectedly already equivalent")
    assert ((1 << 32) - 1) >> 32 == 0
    assert ((1 << 48) - 1) >> 32 != 0
    print("I915_CHV_PPGTT_PINNED_LINUX_NETBSD_REFERENCE_CONTRACT_OK",
          flush=True)

    if args.overlay_tree is None:
        print("I915_CHV_PPGTT_OVERLAY_UNVERIFIED_FROZEN_ONLY", flush=True)
        return

    overlay = args.overlay_tree.resolve(strict=True)
    if overlay in (net, lin):
        raise RuntimeError("actual staged overlay must be a distinct tree")
    if subprocess.check_output(
        ["git", "-C", str(overlay), "rev-parse", "HEAD"], text=True,
    ).strip() != NETBSD_PIN:
        raise RuntimeError("staged overlay NetBSD base has changed")
    modified_pci = (overlay / NET_ROOT / "i915_pci.c").read_text()
    modified_lrc = (overlay / NET_ROOT / "gt/intel_lrc.c").read_text()
    if ".ppgtt_type = INTEL_PPGTT_FULL," not in chv_info(modified_pci):
        raise AssertionError("genuine overlay lacks full CHV PPGTT")
    if ".ppgtt_size = 32," not in chv_info(modified_pci):
        raise AssertionError("staged CHV PPGTT aperture changed")
    if normalized(function(modified_lrc, "emit_pdps")) != expected_pdp:
        raise AssertionError("staged PDP ring sequence diverges from Linux")
    if normalized(function(modified_lrc, "execlists_request_alloc")) != (
        upstream_alloc
    ):
        raise AssertionError("staged execlists PDP decision diverges from Linux")
    print("I915_CHV_PPGTT_GENUINE_OVERLAY_LINUX_SEQUENCE_MATCH_OK",
          flush=True)
    print("LIMITATION: source equivalence only; native compile, ring execution, "
          "full DRM/TTM integration and HP display NOT VERIFIED", flush=True)


if __name__ == "__main__":
    main()
