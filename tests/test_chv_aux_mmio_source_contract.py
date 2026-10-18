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


def macro_value(text: str, name: str, expected: int) -> int:
    match = re.search(r"(?m)^#define\s+" + re.escape(name) +
                      r"\s+(?:\(\s*DISPLAY_MMIO_BASE\(dev_priv\)\s*\+\s*)?"
                      r"(0x[0-9a-fA-F]+)", text)
    check(match is not None, "missing MMIO macro: " + name)
    observed = int(match[1], 16)
    check(observed == expected, "offset mismatch: " + name)
    return observed


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
    netbsd_base = macro_value(n_reg, "VLV_DISPLAY_BASE", 0x180000)
    linux_base = macro_value(l_defs, "VLV_DISPLAY_BASE", 0x180000)
    offsets = {}
    for text, tag in ((n_reg, "NetBSD"), (l_reg, "Linux")):
        offsets[tag] = {}
        for name, expected in (
            ("_DPA_AUX_CH_CTL", 0x64010),
            ("_DPB_AUX_CH_CTL", 0x64110),
            ("_DPA_AUX_CH_DATA1", 0x64014),
            ("_DPB_AUX_CH_DATA1", 0x64114),
        ):
            offsets[tag][name] = macro_value(text, name, expected)
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
    # Compute independently from each pinned source's macro operands,
    # rather than comparing the same hard-coded address expression.
    for port_index in (1, 2, 3):  # AUX B, C, D
        for data_index in range(-1, 5):  # -1 denotes AUX channel control
            name_a = "_DPA_AUX_CH_CTL" if data_index == -1 else "_DPA_AUX_CH_DATA1"
            name_b = "_DPB_AUX_CH_CTL" if data_index == -1 else "_DPB_AUX_CH_DATA1"
            values = []
            for owner, base in (("Linux", linux_base), ("NetBSD", netbsd_base)):
                owner_offsets = offsets[owner]
                low, high = owner_offsets[name_a], owner_offsets[name_b]
                addr = base + low + (high - low) * port_index
                if data_index >= 0:
                    addr += 4 * data_index
                values.append(addr)
            check(values[0] == values[1],
                  "AUX MMIO mismatch: port=" + str(port_index) +
                  " data=" + str(data_index))


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
        if label == "CHV_OFFSET":
            # VLV and CHV each declare this property. Mutate the CHV
            # record, not the earlier VLV entry (a prior false negative).
            prefix, sep, tail = changed[key].partition(
                "static const struct intel_device_info chv_info = {")
            check(bool(sep) and before in tail.split("};", 1)[0],
                  "CHV mutation must target the CHV declaration")
            changed[key] = prefix + sep + tail.replace(before, after, 1)
        elif label == "LINUX_CHV_DISPATCH":
            # Earlier AUX helper code also mentions Cherryview; only the
            # actual intel_dp_aux_init dispatch is relevant to this test.
            prefix, sep, tail = changed[key].partition(
                "void intel_dp_aux_init(struct intel_dp *intel_dp)")
            check(bool(sep) and before in function(changed[key], "intel_dp_aux_init"),
                  "Linux CHV dispatch mutation missed initializer")
            changed[key] = prefix + sep + tail.replace(before, after, 1)
        else:
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
