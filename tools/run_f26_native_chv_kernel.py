#!/usr/bin/env python3
"""F26: isolated 11-patch CHV/RTL clean-kernel build, ONLY on HP NetBSD 11.

Source and compilation gate, NOT a boot/installation/release tool.
F25 on Linux was a cross-build of only F19–F22; it is not HP acceptance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import platform
import socket
import subprocess
import sys

import run_f25_clean_netbsd_console_kernel as f25

BASE = "sys/external/bsd/drm2/dist/drm/i915/"
CONFIG = "F26_CHV_FULL_RTL_TEST"
# Exact original Git blobs from NetBSD/src@03d918f6..., including four F25 pins.
ORIGINAL = {
    **f25.ORIGINAL,
    BASE + "gt/intel_lrc.c": "ac348156cd0df207aa2746ccb2889a837d0821f7",
    BASE + "i915_pci.c": "45fa9b1c94035afb64b67dba88e008410d46e6cc",
    BASE + "display/intel_display_power.c": "b11bfb6dfc8d67877770c0820c23d6541188cd10",
    BASE + "display/intel_display.c": "faff25ecd0a1d57d47f862891810daf5299571a3",
    BASE + "i915_reg.h": "a070913dc965ebfb467b99da599e75dd03df61de",
    BASE + "display/intel_dp.c": "1dd8858b2d331906190258c8602af55966ff986c",
    BASE + "display/intel_hdmi.c": "49e1170ffec9e00ea1f8e67463d017b48029c13b",
    BASE + "i915_irq.c": "73f8deec8404481c4e457bb72631456b3b11ff69",
    BASE + "intel_sideband.c": "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed",
    BASE + "intel_sideband.h": "ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea",
    BASE + "display/intel_dpio_phy.c": "9029d10774992a62a3f2ac84bb8a37f724360442",
    BASE + "display/intel_display.h": "03e7f21e578248e80ae03510715dc97eb855ca6f",
    BASE + "gt/intel_rps.c": "d3faefcffe985725a0cee09a25f7d2270a35e5ea",
}
# Exact published patch Git blobs and expected native file paths.
# Superseded overlapping F14 GPLL and F16 DPIO variants are NOT included.
PATCHES = (
    ("patches/candidates/netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch",
     "d3ae4c62a723363843978f58fd352d1cc69c61cf",
     ("sys/external/bsd/drm2/drm/drmfb.c",)),
    ("patches/candidates/netbsd11-f20-x86-genfb-early-fallback-20261027.patch",
     "66954d17084b2902e2c091f477b1b0d20a6f8f41",
     ("sys/arch/x86/x86/consinit.c",)),
    ("patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch",
     "0b3501a4d4ed1a22f7ee213b5be7176578869677",
     ("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",)),
    ("patches/candidates/netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch",
     "68b6e0d5d7f0afff2eb4eaf15f890233ece4d628",
     ("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",
      "sys/external/bsd/drm2/i915drm/files.i915drmkms")),
    ("patches/0001-chv-full-ppgtt-linux-1c8ee8b-netbsd11.patch",
     "246e31ba0420c317562cfb1e8390942285602933",
     (BASE + "gt/intel_lrc.c", BASE + "i915_pci.c")),
    ("patches/0002-chv-defer-phy-control-powerwell-linux-1a2466fe-netbsd11.patch",
     "2d05ef456036954e556b492d818b1bca5831cc13",
     (BASE + "display/intel_display_power.c",)),
    ("patches/0003-vlv-chv-pipe-msa-misc-linux-c931ef00-netbsd11.patch",
     "970dcc521e0da558d8f55a28843ff718e7e2e242",
     (BASE + "display/intel_display.c", BASE + "i915_reg.h")),
    ("patches/0005-vlv-chv-dp-hdmi-audio-phase-linux-netbsd11.patch",
     "ced6c4ba9aac61c69e0220cb43add33cf2f0a43c",
     (BASE + "display/intel_dp.c", BASE + "display/intel_hdmi.c")),
    ("patches/0006-vlv-chv-display-error-irq-linux-netbsd11.patch",
     "32f48ec893dc288197a78e120de96265b79a6d1a",
     (BASE + "i915_reg.h", BASE + "i915_irq.c")),
    ("patches/candidates/netbsd-11-chv-dpio-signal-phy-consumer-20261026.patch",
     "690556c27aec65c5814126e99f445d860f55613d",
     (BASE + "intel_sideband.c", BASE + "intel_sideband.h",
      BASE + "display/intel_dpio_phy.c")),
    ("patches/candidates/netbsd-11-chv-gpll-rps-lock-order-20261026.patch",
     "620916dac6179e6514852d795a9cc78762a4a467",
     (BASE + "display/intel_display.c", BASE + "display/intel_display.h",
      BASE + "gt/intel_rps.c")),
)


def require_native_hp(system: str, release: str, machine: str,
                      hostname: str) -> None:
    if not (system == "NetBSD" and release.split(".")[0] == "11"
            and machine.lower() in {"amd64", "x86_64"}
            and hostname.split(".")[0].lower() == "hp-tpnw121"):
        raise RuntimeError("F26_HP_NETBSD11_ONLY: refusing cross-host kernel build")


def patch_paths(patch: Path) -> set[str]:
    result = subprocess.run(["git", "apply", "--numstat", str(patch)],
                            check=True, text=True, capture_output=True)
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            raise RuntimeError("malformed patch numstat")
        rel = Path(fields[2])
        if not fields[2] or rel.is_absolute() or ".." in rel.parts:
            raise RuntimeError("unsafe patch path")
        paths.add(fields[2])
    if not paths:
        raise RuntimeError("empty patch")
    return paths


def verify_manifest(stage: Path, project: Path) -> None:
    if f25.PIN != "03d918f6d0e81fa05b8f1160eca0628ad39988a6":
        raise RuntimeError("base NetBSD version drift")
    if len(PATCHES) != 11 or len(ORIGINAL) != 17:
        raise RuntimeError("expected 11 patches modifying exactly 17 native files")
    changed: set[str] = set()
    for name, gitblob, scope in PATCHES:
        patch = project / name
        if not patch.is_file() or f25.blob_id(patch.read_bytes()) != gitblob:
            raise RuntimeError("unverified patch Git blob: " + name)
        found = patch_paths(patch)
        if found != set(scope):
            raise RuntimeError("patch touched out-of-scope native files: " + name)
        changed.update(found)
    if changed != set(ORIGINAL):
        raise RuntimeError("unpinned original or unpatched declared source")
    for name, expected in ORIGINAL.items():
        file = stage / name
        if not file.is_file() or f25.blob_id(file.read_bytes()) != expected:
            raise RuntimeError("original NetBSD Git blob drift: " + name)


def configure_clean_builder() -> None:
    # F25's path join accepts absolute paths: this preserves all eleven
    # tested patch locations without relocating patches or changing F25.
    f25.PATCHES = [str(f25.ROOT / name) for name, _, _ in PATCHES]
    f25.ORIGINAL = dict(ORIGINAL)
    f25.CONFIG = CONFIG
    f25.CONFIG_PATH = f"sys/arch/amd64/conf/{CONFIG}"


def main() -> None:
    args = list(sys.argv[1:])
    if "--ack-compile-only" not in args:
        raise RuntimeError("F26 requires --ack-compile-only; NEVER boot/install")
    args.remove("--ack-compile-only")
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source-stage", required=True, type=Path)
    parsed, _ = parser.parse_known_args(args)
    require_native_hp(platform.system(), platform.release(),
                      platform.machine(), socket.gethostname())
    verify_manifest(parsed.source_stage.resolve(strict=True), f25.ROOT)
    configure_clean_builder()
    sys.argv = [sys.argv[0], *args]
    f25.main()
    print("F26_NATIVE_HP_11_PATCH_17_FILE_CLEAN_KERNEL_COMPILE_LINK_PASS", flush=True)
    print("F26_DO_NOT_INSTALL_BOOT_OR_USE_AS_DISPLAY_ACCEPTANCE", flush=True)


if __name__ == "__main__":
    main()
