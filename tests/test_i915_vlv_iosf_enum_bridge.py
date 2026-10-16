#!/usr/bin/env python3
"""Frozen modern/old Intel IOSF enum ABI and C bitmask translation tests."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "compat/native-runtime/vlv-iosf/include/nb_i915_vlv_iosf_unit_bridge.h"
LINUX = Path("/opt/ChatGPT/hp-driver-port/i915-reference-stage-20261001/include/drm/intel/vlv_iosf_sb_regs.h")
NETBSD = Path("/opt/ChatGPT/hp-driver-port/netbsd-src-03d918f6-full/sys/external/bsd/drm2/dist/drm/i915/intel_sideband.h")
NETBSD_C = NETBSD.with_suffix(".c")
LINUX_C = Path("/opt/ChatGPT/hp-driver-port/i915-reference-stage-20261001/drivers/gpu/drm/i915/vlv_iosf_sb.c")
PIN = {
    LINUX: "e4198672b507cff85df32084643c731d29f32efa67c820a4bea91aaeee3804df",
    NETBSD: "498168f1ac94396e5e25aabd8f10e39e64f513f19e378d24b4f2b7b64110d612",
    NETBSD_C: "ae1aefbd0683cb031a0bc9b20a9c16c1438d391f51b4158fddfc0e1555a05807",
    LINUX_C: "ce076e147edc00599df16641cf9f1587ee24277f858c7df4aff00f8d690b2e65",
}
for path, sha in PIN.items():
    assert path.is_file(), path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, path


def enum_names(text, modern):
    needle = (r"enum\s+vlv_iosf_sb_unit\s*\{([\s\S]*?)\};"
              if modern else
              r"\benum\s*\{\s*(VLV_IOSF_SB_BUNIT[\s\S]*?)\};")
    m = re.search(needle, text)
    assert m, "VLV enum declaration not found"
    names = re.findall(r"\bVLV_IOSF_SB_[A-Z0-9_]+\b", m[1])
    assert len(names) == len(set(names))
    return names


modern = enum_names(LINUX.read_text(), True)
legacy = enum_names(NETBSD.read_text(), False)
assert modern == [
    "VLV_IOSF_SB_BUNIT", "VLV_IOSF_SB_CCK", "VLV_IOSF_SB_CCU",
    "VLV_IOSF_SB_DPIO", "VLV_IOSF_SB_DPIO_2", "VLV_IOSF_SB_FLISDSI",
    "VLV_IOSF_SB_GPIO", "VLV_IOSF_SB_NC", "VLV_IOSF_SB_PUNIT"]
assert legacy == [name for name in modern if name != "VLV_IOSF_SB_DPIO_2"]
assert NETBSD_C.read_text().count("vlv_iosf_sb_get(") >= 1
assert "locked_unit_mask" in LINUX_C.read_text()
assert "locked_unit_mask" not in NETBSD_C.read_text()

candidate = HEADER.read_text()
for index, name in enumerate(modern):
    assert f"NB_I915_MOD_{name[len('VLV_IOSF_SB_'):]} = {index}" in candidate
for index, name in enumerate(legacy):
    assert f"NB_I915_LEG_{name[len('VLV_IOSF_SB_'):]} = {index}" in candidate
assert "return -EOPNOTSUPP;" in candidate
print("I915_IOSF_BOTH_FROZEN_ENUMS_AND_LOCK_DIFFERENCE_PASS")

C = r"""
#include <stdio.h>
#include <limits.h>
#include <nb_i915_vlv_iosf_unit_bridge.h>
int main(void)
{
    const unsigned modern[9] = {0,1,2,3,4,5,6,7,8};
    const unsigned legacy[9] = {0,1,2,3,~0U,4,5,6,7};
    unsigned long output = ~0UL;
    unsigned int unit = ~0U;
    int error;
    for (unsigned i = 0; i < 9; i++) {
        unit = 0xcafeU;
        error = nb_i915_vlv_iosf_legacy_unit(modern[i], &unit);
        if (i == 4) {
            if (error != -EOPNOTSUPP || unit != 0xcafeU)
                return 1;
        } else {
            if (error != 0 || unit != legacy[i])
                return 2;
        }
        output = ~0UL;
        error = nb_i915_vlv_iosf_legacy_mask(1UL << i, &output);
        if (i == 4) {
            if (error != -EOPNOTSUPP || output != ~0UL)
                return 3;
        } else {
            if (error != 0 || output != (1UL << legacy[i]))
                return 4;
        }
    }
    output = 0xbadeUL;
    if (nb_i915_vlv_iosf_legacy_mask(1UL << NB_I915_MOD_PUNIT,
                                      &output) != 0 ||
        output != (1UL << NB_I915_LEG_PUNIT)) return 5;
    if (nb_i915_vlv_iosf_legacy_mask((1UL<<0)|(1UL<<7)|(1UL<<8),
                                      &output) != 0 ||
        output != ((1UL<<0)|(1UL<<6)|(1UL<<7))) return 6;
    if (nb_i915_vlv_iosf_legacy_mask(0x1EFUL, &output) != 0 ||
        output != 0xFFUL) return 7;
    if (nb_i915_vlv_iosf_legacy_mask(0UL, &output) != 0 ||
        output != 0UL) return 8;
    output = 0xbadeUL;
    if (nb_i915_vlv_iosf_legacy_mask(1UL << 4, &output) !=
        -EOPNOTSUPP || output != 0xbadeUL) return 9;
    if (nb_i915_vlv_iosf_legacy_mask(1UL << 12, &output) !=
        -EINVAL || output != 0xbadeUL) return 10;
    if (nb_i915_vlv_iosf_legacy_mask(0UL, NULL) != -EINVAL)
        return 11;
    if (nb_i915_vlv_iosf_legacy_unit(0, NULL) != -EINVAL)
        return 12;
    unit = 0xdeadU;
    if (nb_i915_vlv_iosf_legacy_unit(UINT_MAX, &unit) != -EINVAL ||
        unit != 0xdeadU) return 13;
    puts("I915_CHV_IOSF_9_UNITS_MASKS_AND_FAILCLOSED_C_PASS");
    return 0;
}
"""
cc = shutil.which("cc")
assert cc, "No host C compiler"
with tempfile.TemporaryDirectory(prefix="i915-iosf-bridge-c-") as td:
    root = Path(td)
    file = root / "sys/errno.h"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("#include <errno.h>\n")
    main = root / "test.c"
    main.write_text(C)
    exe = root / "test"
    subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root),
                    "-I", str(HEADER.parent), str(main), "-o", str(exe)],
                   timeout=25, check=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True,
                            timeout=20)
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert "I915_CHV_IOSF_9_UNITS_MASKS_AND_FAILCLOSED_C_PASS" in result.stdout
    print(result.stdout.strip())
print("LIMITATION: isolated enum/lock-mask bridge, NOT NetBSD MMIO, IRQ or full KMS")
