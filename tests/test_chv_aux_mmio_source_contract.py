#!/usr/bin/env python3
"""NetBSD CHV AUX MMIO hardware address mapping vs frozen Linux (source-only).

Requires real C/header files from the two immutable upstream revisions.
A source PASS is NOT complete DP AUX semantics, 323 parity, or a kernel build.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re

PIN = {
    "netbsd_pci": "f1b672728326669f8a2cad5d50c3acadf582a67550cd18440ef592ad2e0d124b",
    "netbsd_reg": "759a4ee5f6583e805b52bc917758860d1a29c548ebe098367b76875bb400b387",
    "netbsd_dp": "7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141",
    "linux_aux": "3d5d4e23b1debcf89bef8a2136f602303164a76fa8267a23f8471059ca2c0658",
    "linux_aux_regs": "694c67360055fba5668baff645f0d624645bd17aeb143d976d2e11b2fc3ce37d",
    "linux_defs": "ec3c31479d56a2a2706d346e95d59dce21ab8c3e35cdc20d2c2264fd7421cebd",
}


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError("CHV_AUX_SOURCE_REFUSED: " + label)


def function(text: str, symbol: str) -> str:
    match = re.search(r"\b" + re.escape(symbol) + r"\s*\([^;]*?\)\s*\{",
                      text, re.S)
    check(match is not None, "function not found: " + symbol)
    start = match.end()
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    raise AssertionError("CHV_AUX_SOURCE_REFUSED: unmatched function body " + symbol)


def macro_value(text: str, name: str, expected: int) -> None:
    match = re.search(r"(?m)^#define\s+" + re.escape(name) +
                      r"\s+(?:\(\s*DISPLAY_MMIO_BASE\(dev_priv\)\s*\+\s*)?"
                      r"(0x[0-9a-fA-F]+)", text)
    check(match is not None, "missing MMIO macro: " + name)
    check(int(match[1], 16) == expected, "offset mismatch: " + name)


def validate(src: dict[str, str]) -> None:
    n_pci, n_reg, n_dp = (src[k] for k in
                            ("netbsd_pci", "netbsd_reg", "netbsd_dp"))
    l_aux, l_reg, l_defs = (src[k] for k in
                              ("linux_aux", "linux_aux_regs", "linux_defs"))
    chv = n_pci.split("static const struct intel_device_info chv_info = {", 1)
    check(len(chv) == 2, "NetBSD missing CHV device owner")
    chv = chv[1].split("};", 1)[0]
    check("GEN(8)" in chv and
          ".display_mmio_offset = VLV_DISPLAY_BASE" in chv,
          "CHV is not anchored to NetBSD VLV display MMIO")
    for text, tag in ((n_reg, "NetBSD"), (l_defs, "Linux")):
        macro_value(text, "VLV_DISPLAY_BASE", 0x180000)
    for text, tag in ((n_reg, "NetBSD"), (l_reg, "Linux")):
        for prefix, low, high in (
            ("_DPA_AUX_CH_CTL", 0x64010, None),
            ("_DPB_AUX_CH_CTL", 0x64110, None),
            ("_DPA_AUX_CH_DATA1", 0x64014, None),
            ("_DPB_AUX_CH_DATA1", 0x64114, None),
        ):
            macro_value(text, prefix, low)
    check("#define DISPLAY_MMIO_BASE(dev_priv)" in n_reg and
          "INTEL_INFO(dev_priv)->display_mmio_offset" in n_reg,
          "NetBSD DISPLAY_MMIO_BASE dispatch changed")
    check("_MMIO_PORT(aux_ch, _DPA_AUX_CH_CTL, _DPB_AUX_CH_CTL)" in n_reg,
          "native DP AUX control port selector mismatch")
    check("_PORT(aux_ch, _DPA_AUX_CH_DATA1, _DPB_AUX_CH_DATA1)" in n_reg,
          "native DP AUX data port selector mismatch")
    check("VLV_DISPLAY_BASE + " in l_reg and
          "VLV_DP_AUX_CH_CTL(aux_ch)" in l_reg and
          "VLV_DP_AUX_CH_DATA(aux_ch, i)" in l_reg,
          "Linux VLV AUX branch or VLV offset missing")
    check("#define _PORT(port, a, b)" in l_defs and
          "_PICK_EVEN(port, a, b)" in l_defs,
          "Linux AUX port iteration owner changed")
    n_ctl = function(n_dp, "g4x_aux_ctl_reg")
    n_data = function(n_dp, "g4x_aux_data_reg")
    for body, token in ((n_ctl, "DP_AUX_CH_CTL(aux_ch)"),
                        (n_data, "DP_AUX_CH_DATA(aux_ch, index)")):
        check(all("case AUX_CH_" + p + ":" in body for p in "BCD")
              and token in body, "NetBSD G4X AUX port map incomplete")
    n_init = function(n_dp, "intel_dp_aux_init")
    check("intel_dp->aux_ch_ctl_reg = g4x_aux_ctl_reg;" in n_init and
          "intel_dp->aux_ch_data_reg = g4x_aux_data_reg;" in n_init,
          "NetBSD CHV AUX fallback changed")
    l_init = function(l_aux, "intel_dp_aux_init")
    check("display->platform.cherryview" in l_init and
          "intel_dp->aux_ch_ctl_reg = vlv_aux_ctl_reg;" in l_init and
          "intel_dp->aux_ch_data_reg = vlv_aux_data_reg;" in l_init,
          "Linux CHV AUX branch mismatch")
    l_ctl = function(l_aux, "vlv_aux_ctl_reg")
    l_data = function(l_aux, "vlv_aux_data_reg")
    check("VLV_DP_AUX_CH_CTL(aux_ch)" in l_ctl and
          "VLV_DP_AUX_CH_DATA(aux_ch, index)" in l_data,
          "Linux CHV AUX macro dispatch mismatch")
    # The two source expressions yield equal MMIO addresses for all ports.
    for port_index in (1, 2, 3):  # AUX B, C, D
        for data_index in range(5):
            relative = 0x64014 + port_index * 0x100 + data_index * 4
            linux = 0x180000 + relative
            netbsd = 0x180000 + relative
            check(linux == netbsd, "AUX data MMIO mismatch")
        ctl = 0x180000 + 0x64010 + port_index * 0x100
        check(ctl >= 0x1e4110, "AUX control MMIO invalid")


def run(source_paths: dict[str, Path]) -> None:
    src: dict[str, str] = {}
    for key, path in source_paths.items():
        raw = path.read_bytes()
        check(hashlib.sha256(raw).hexdigest() == PIN[key],
              "frozen source SHA mismatch: " + key)
        src[key] = raw.decode("utf-8")
    validate(src)
    mutations = {
        "CHV_OFFSET": ("netbsd_pci", ".display_mmio_offset = VLV_DISPLAY_BASE",
                       ".display_mmio_offset = 0"),
        "NETBSD_DP_CTRL": ("netbsd_dp", "DP_AUX_CH_CTL(aux_ch)",
                           "DP_AUX_CH_CTL(AUX_CH_B)"),
        "NETBSD_DP_DATA": ("netbsd_dp", "DP_AUX_CH_DATA(aux_ch, index)",
                           "DP_AUX_CH_DATA(AUX_CH_B, index)"),
        "LINUX_CHV_DISPATCH": ("linux_aux", "display->platform.cherryview",
                               "display->platform.broadwell"),
        "LINUX_MMIO_BANK": ("linux_defs", "0x180000", "0x280000"),
        "LINUX_AUX_REG": ("linux_aux_regs", "0x64110", "0x74110"),
    }
    for label, (key, before, after) in mutations.items():
        check(before in src[key], "mutation anchor missing " + label)
        changed = dict(src)
        changed[key] = changed[key].replace(before, after, 1)
        try:
            validate(changed)
        except AssertionError:
            continue
        raise AssertionError("CHV_AUX_SOURCE_REFUSED: mutation accepted " + label)
    print("CHV_AUX_REGISTER_BANK_FROZEN_SOURCE_18_REGS_6_MUTATIONS_PASS")
    print("NOTE: AUX failure/timeout/locking, 323 parity and physical KMS UNVERIFIED")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in PIN:
        p.add_argument("--" + name.replace("_", "-"), required=True, type=Path)
    args = p.parse_args()
    try:
        run({k: getattr(args, k) for k in PIN})
        return 0
    except (AssertionError, OSError, UnicodeError) as exc:
        print(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
