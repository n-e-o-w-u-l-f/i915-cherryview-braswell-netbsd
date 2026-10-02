#!/usr/bin/env python3
"""Pin the Cherryview pipe->PHY->IOSF routing equivalence.

NetBSD's older sideband DPIO API accepts a PIPE and derives DPIO_PHY(pipe).
Pinned Linux's Cherryview DPIO callers explicitly pass the digital PORT's
PHY. Both select the same PHY for the *permitted* NetBSD B/C/D port-pipe
pairs because the encoder pipe masks constrain those pairs. Reject any
change to that contract before considering a hardware-visible port of
the newer Linux PHY API. This is a source-level check, not a hardware test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_ROOT = "sys/external/bsd/drm2/dist/drm/i915/"
NETBSD_FILES = {
    "driver": NETBSD_ROOT + "i915_drv.c",
    "registers": NETBSD_ROOT + "i915_reg.h",
    "sideband": NETBSD_ROOT + "intel_sideband.c",
    "display": NETBSD_ROOT + "display/intel_display.h",
    "types": NETBSD_ROOT + "display/intel_display_types.h",
    "dp": NETBSD_ROOT + "display/intel_dp.c",
    "hdmi": NETBSD_ROOT + "display/intel_hdmi.c",
    "dpio": NETBSD_ROOT + "display/intel_dpio_phy.c",
}
LINUX_DPIO = "drivers/gpu/drm/i915/display/intel_dpio_phy.c"


def pinned_file(tree: Path, commit: str, relative: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != commit:
        raise RuntimeError("unexpected pinned reference commit: " + str(tree))
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative], text=True
    )
    if (tree / relative).read_text() != committed:
        raise RuntimeError("dirty/missing pinned source: " + relative)
    return committed


def section(source: str, first: str, following: str) -> str:
    if source.count(first) != 1:
        raise AssertionError("non-unique/missing source boundary: " + first)
    start = source.index(first)
    end = source.index(following, start + len(first))
    return source[start:end]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--linux-tree", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        key: pinned_file(args.netbsd_tree, NETBSD_PIN, path)
        for key, path in NETBSD_FILES.items()
    }
    linux = pinned_file(args.linux_tree, LINUX_PIN, LINUX_DPIO)

    # Real pinned NetBSD enums: A=0, B=1, C=2.
    if re.search(r"enum pipe \{\s*INVALID_PIPE = -1,\s*"
                 r"PIPE_A = 0,\s*PIPE_B,\s*PIPE_C,", sources["display"]) is None:
        raise AssertionError("NetBSD pipe values/ordering changed")

    # NetBSD sideband DPIO API derives the hardware PHY from CRTC pipe:
    # DPIO_PHY(A)=0, DPIO_PHY(B)=0, DPIO_PHY(C)=1.
    if re.search(r"(?m)^#define DPIO_PHY\(pipe\)\s+\(\(pipe\) >> 1\)\s*$",
                 sources["registers"]) is None:
        raise AssertionError("pinned DPIO_PHY(pipe) encoding changed")
    sideband = section(sources["sideband"], "u32 vlv_dpio_read(",
                       "u32 vlv_flisdsi_read(")
    if sideband.count("i915->dpio_phy_iosf_port[DPIO_PHY(pipe)]") != 2:
        raise AssertionError("DPIO read/write no longer use pipe-derived PHY")
    if "vlv_sideband_rw(i915, DPIO_DEVFN, port, SB_MRD_NP" not in sideband:
        raise AssertionError("DPIO read IOSF destination changed")
    if "vlv_sideband_rw(i915, DPIO_DEVFN, port, SB_MWR_NP" not in sideband:
        raise AssertionError("DPIO write IOSF destination changed")

    # Both PHYs must map to the correct Cherryview IOSF ports.
    init = section(sources["driver"], "static void intel_init_dpio(",
                   "static int i915_workqueues_init(")
    assert "DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO_2;" in init
    assert "DPIO_PHY_IOSF_PORT(DPIO_PHY1) = IOSF_PORT_DPIO;" in init

    # Port B and C use PHY0, D uses PHY1. Port A is NOT part of
    # this B/C/D Cherryview mapping and is not inferred here.
    mapping = section(sources["types"],
                      "static inline enum dpio_phy\nvlv_dport_to_phy(",
                      "static inline enum dpio_channel\nvlv_pipe_to_channel(")
    for required in (
        "case PORT_B:\n\tcase PORT_C:\n\t\treturn DPIO_PHY0;",
        "case PORT_D:\n\t\treturn DPIO_PHY1;",
    ):
        if required not in mapping:
            raise AssertionError("physical port->PHY mapping changed")

    # Both DP and HDMI must restrict the permissible port/pipe
    # combinations. The routing equivalence relies on this.
    mask = (
        "if (IS_CHERRYVIEW(dev_priv)) {\n"
        "\t\tif (port == PORT_D)\n"
        "\t\t\tintel_encoder->pipe_mask = BIT(PIPE_C);\n"
        "\t\telse\n"
        "\t\t\tintel_encoder->pipe_mask = BIT(PIPE_A) | BIT(PIPE_B);\n"
        "\t} else {\n"
        "\t\tintel_encoder->pipe_mask = ~0;\n"
        "\t}"
    )
    for connector in ("dp", "hdmi"):
        if sources[connector].count(mask) != 1:
            raise AssertionError(
                "Cherryview " + connector + " port/pipe mask changed"
            )

    net_phy = section(sources["dpio"],
                      "void chv_phy_pre_pll_enable(",
                      "void chv_phy_post_pll_disable(")
    linux_phy = section(linux, "void chv_phy_pre_pll_enable(",
                        "void chv_phy_post_pll_disable(")
    if "vlv_dpio_read(dev_priv, pipe," not in net_phy:
        raise AssertionError("NetBSD PHY access no longer pipe-derived")
    if "enum dpio_phy phy = vlv_dig_port_to_phy(dig_port);" not in linux_phy:
        raise AssertionError("Linux PHY access no longer port-derived")
    if "vlv_dpio_read(display, phy," not in linux_phy:
        raise AssertionError("Linux PHY-based read convention changed")

    port_phy = {"B": 0, "C": 0, "D": 1}
    valid = {"B": (0, 1), "C": (0, 1), "D": (2,)}
    for port, pipes in valid.items():
        for pipe in pipes:
            if (pipe >> 1) != port_phy[port]:
                raise AssertionError(
                    f"mismatched IOSF PHY: port {port} / pipe {pipe}"
                )
    # These INVALID pairs demonstrate why a wider pipe mask would be
    # unsafe without converting *all* affected DPIO calls to PHY-based.
    assert (2 >> 1) != port_phy["B"]
    assert (0 >> 1) != port_phy["D"]
    print("I915_CHV_DPIO_PINNED_PORT_PIPE_PHY_ROUTE_CONTRACT_OK")
    print("LIMITATION: valid B/C/D connectors only; source-only, "
          "not target-OS compilation, native register access or HP output")


if __name__ == "__main__":
    main()
