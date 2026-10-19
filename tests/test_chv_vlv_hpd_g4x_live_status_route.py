#!/usr/bin/env python3
"""VLV/CHV HPD source-owner routing on pinned NetBSD, separate 0044 patch.

Source-only test against NetBSD frozen DP/IRQ C; no physical HP HPD test.
Inclusion of G4X IRQ masks proves consistency with source interrupt owner,
not automatically any specific HP-ACPI/HPD pad electrical configuration.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

NETBSD_DP_BLOB = "1dd8858b2d331906190258c8602af55966ff986c"
NETBSD_IRQ_BLOB = "73f8deec8404481c4e457bb72631456b3b11ff69"
NETBSD_REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"


def fail(message: str):
    raise AssertionError("I915_CHV_HPD_ROUTE_REFUSED: " + message)


def sha(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\x00" + raw
    ).hexdigest()


def function(code: str, symbol: str) -> str:
    match = re.search(
        r"(?m)^(?:static\s+)?(?:bool|u32|void)\s+"
        + re.escape(symbol) + r"\([^)]*\)\s*\{",
        code,
    )
    if not match:
        fail("function not found " + symbol)
    end = code.find("\n}\n", match.end())
    if end < 0:
        fail("function not delimited " + symbol)
    return code[match.start():end + 3]


def audit(dp: str, irq: str) -> None:
    connected = function(dp, "__intel_digital_port_connected")
    generic = function(dp, "g4x_digital_port_connected")
    bdw = function(dp, "bdw_digital_port_connected")
    hpda = function(irq, "i9xx_hpd_irq_ack")
    hpdi = function(irq, "i9xx_hpd_irq_handler")

    branch = "if ((IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) &&"
    expected = (branch + "\n\t    (encoder->hpd_pin == HPD_PORT_B ||"\n                 "\n\t     encoder->hpd_pin == HPD_PORT_C ||"\n                 "\n\t     encoder->hpd_pin == HPD_PORT_D))"\n                 "\n\t\treturn g4x_digital_port_connected(encoder);")
    if connected.count(expected) != 1:
        fail("VLV/CHV route not selecting G4X live status")
    if not (connected.index("if (HAS_GMCH(dev_priv))") <
            connected.index(expected) <
            connected.index("if (INTEL_PCH_TYPE(dev_priv) >= PCH_ICP)") <
            connected.index("IS_GEN(dev_priv, 8)") <
            connected.index("IS_GEN(dev_priv, 7)")):
        fail("platform precedence allows VLV/CHV through wrong BDW/IVB route")
    for pin, status in (
        ("HPD_PORT_B", "PORTB_HOTPLUG_LIVE_STATUS_G4X"),
        ("HPD_PORT_C", "PORTC_HOTPLUG_LIVE_STATUS_G4X"),
        ("HPD_PORT_D", "PORTD_HOTPLUG_LIVE_STATUS_G4X"),
    ):
        if (f"case {pin}:" not in generic or status not in generic):
            fail("G4X HPD pin mapping missing " + pin)
    if "return I915_READ(PORT_HOTPLUG_STAT) & bit;" not in generic:
        fail("G4X live-status register owner changed")
    if "I915_READ(GEN8_DE_PORT_ISR) & GEN8_PORT_DP_A_HOTPLUG" not in bdw:
        fail("Broadwell route semantics changed: re-evaluate comparison")
    for code in (hpda, hpdi):
        if "IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)" not in code and not re.search(
            r"IS_VALLEYVIEW\(dev_priv\)\s*\|\|\s*IS_CHERRYVIEW\(dev_priv\)", code
        ):
            fail("IRQ G4X VLV/CHV dispatch is no longer proven")
    if "PORT_HOTPLUG_STAT" not in hpda or "HOTPLUG_INT_STATUS_G4X" not in hpda:
        fail("IRQ acknowledgment register/mask differs from HPD route")
    if "hpd_status_g4x" not in hpdi:
        fail("IRQ handler not using G4X per-pin status owner")


def command(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        fail("scratch patch tool: " + result.stderr[-400:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-dp", type=Path, required=True)
    ap.add_argument("--netbsd-irq", type=Path, required=True)
    ap.add_argument("--patch", type=Path, required=True)
    a = ap.parse_args()
    rawdp, rawirq = a.netbsd_dp.read_bytes(), a.netbsd_irq.read_bytes()
    if sha(rawdp) != NETBSD_DP_BLOB or sha(rawirq) != NETBSD_IRQ_BLOB:
        fail("source must be byte-exact frozen NetBSD 11 C")
    baseline = function(rawdp.decode(), "__intel_digital_port_connected")
    if "if ((IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv))" in baseline:
        fail("baseline no longer missing platform branch")

    with tempfile.TemporaryDirectory(prefix="chv-hpd-0044-") as tmp:
        root = Path(tmp)
        target = root / NETBSD_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(rawdp)
        patch = str(a.patch.resolve(strict=True))
        command(["git", "apply", "--check", patch], root)
        command(["git", "apply", patch], root)
        altered = target.read_text()
        audit(altered, rawirq.decode())
        print("CHV_HPD_G4X_PINNED_SOURCE_PATCH_PASS")
        branch = "if ((IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) &&"
        mutations = (
            ("chv_missing", branch,
             "if ((IS_VALLEYVIEW(dev_priv) || IS_BROADWELL(dev_priv)) &&"),
            ("vlv_missing", branch,
             "if ((IS_CHERRYVIEW(dev_priv)) &&"),
            ("both_missing", branch,
             "if ((IS_BROADWELL(dev_priv)) &&"),
            ("wrong_provider", "return g4x_digital_port_connected(encoder);\n\n\tif (INTEL_PCH_TYPE(dev_priv) >= PCH_ICP)",
             "return bdw_digital_port_connected(encoder);\n\n\tif (INTEL_PCH_TYPE(dev_priv) >= PCH_ICP)"),
            ("wrong_vlv_irq_mask", "IS_VALLEYVIEW(dev_priv) || IS_CHERRYVIEW(dev_priv)) &&",
             "IS_BROADWELL(dev_priv) || IS_CHERRYVIEW(dev_priv)) &&"),
            ("wrong_pin_A_capture", "encoder->hpd_pin == HPD_PORT_D))",\n             "encoder->hpd_pin == HPD_PORT_A))"),\n            ("wrong_irq_ack_reg", "I915_READ(PORT_HOTPLUG_STAT) & hotplug_status_mask",
             "I915_READ(GEN8_DE_PORT_ISR) & hotplug_status_mask"),
        )
        for label, before, after in mutations:
            if label.startswith("wrong_irq"):
                src = rawirq.decode()
                if src.count(before) != 1:
                    fail("nonunique IRQ mutation " + label)
                try:
                    audit(altered, src.replace(before, after, 1))
                except AssertionError as ex:
                    if "I915_CHV_HPD_ROUTE_REFUSED" not in str(ex):
                        raise
                else:
                    fail("unsafe IRQ mutation accepted " + label)
                continue
            c = function(altered, "__intel_digital_port_connected")
            if c.count(before) != 1:
                fail("nonunique DP mutation " + label)
            bad = altered.replace(c, c.replace(before, after, 1), 1)
            try:
                audit(bad, rawirq.decode())
            except AssertionError as ex:
                if "I915_CHV_HPD_ROUTE_REFUSED" not in str(ex):
                    raise
            else:
                fail("unsafe DP mutation accepted " + label)
        print("CHV_HPD_G4X_SEVEN_SOURCE_MUTATIONS_REFUSED")
        command(["git", "apply", "--reverse", patch], root)
        if target.read_bytes() != rawdp:
            fail("byte-exact rollback failed")
        print("CHV_HPD_G4X_SOURCE_REVERSE_PASS")
    print("LIMIT: CHV source irq/display route only; HPD pin, runtime lock/PM, "
          "native compilation and physical external DP NOT VERIFIED.")


if __name__ == "__main__":
    main()
