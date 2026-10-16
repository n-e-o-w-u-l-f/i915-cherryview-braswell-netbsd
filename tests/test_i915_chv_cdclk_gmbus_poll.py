#!/usr/bin/env python3
"""Frozen 323-unit CHV CDCLK/GMBUS poll-site source + host C mock proof."""
import ast, hashlib, re, shutil, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("/opt/ChatGPT/hp-driver-port/i915-reference-stage-20261001")
SRC = STAGE / "drivers/gpu/drm/i915"
lines = (STAGE / "i915-active.filelist").read_text().splitlines()
units = [line.split("external/bsd/drm2/dist/drm/i915/", 1)[1].split()[0]
         for line in lines]
assert len(units) == len(set(units)) == 323
counts = [
    sum(len(re.findall(r"\b" + name + r"\s*\(",
                       (SRC / path).read_text())) for path in units)
    for name in ("poll_timeout_us", "poll_timeout_us_atomic")]
assert counts == [32, 1], counts
pins = {
    "display/intel_cdclk.c":
      "1473d23c8f82692e8ae68ca129db11eb4007d4484fe12893cbad0a8f7da79780",
    "display/intel_gmbus.c":
      "f950e8574a25291e7201551b7599c79abed9d2c2095f32c634868d6401b8c8f0"
}
for path, checksum in pins.items():
    assert hashlib.sha256((SRC / path).read_bytes()).hexdigest() == checksum
cdclk = (SRC / "display/intel_cdclk.c").read_text()
gmbus = (SRC / "display/intel_gmbus.c").read_text()
assert cdclk.count("poll_timeout_us(") == 3
assert "DSPFREQSTAT_MASK_CHV" in cdclk
assert "cmd << DSPFREQSTAT_SHIFT_CHV" in cdclk
assert gmbus.count("poll_timeout_us_atomic(") == 1
assert gmbus.count("poll_timeout_us(") == 1
assert re.search(r"\b500\s*,\s*50\s*\*\s*1000\s*,\s*false\s*\)", cdclk)
assert re.search(r"\b0\s*,\s*2\s*,\s*false\s*\)", gmbus)
print("I915_PINNED_323_IOPOLL_CALLSITE_32_NORMAL_1_ATOMIC_PASS")
tree = ast.parse((ROOT/"tests/test_i915_netbsd_iopoll_contract.py").read_text())
v = {t.id: ast.literal_eval(n.value)
     for n in tree.body if isinstance(n, ast.Assign)
     for t in n.targets if isinstance(t, ast.Name) and t.id in ("MOCK", "STUBS")}
assert set(v) == {"MOCK","STUBS"}
mock = v["MOCK"]
helpers = r"""
#define DSPFREQSTAT_MASK_CHV (7U << 8)
#define DSPFREQSTAT_SHIFT_CHV 8U
static unsigned int chv_reads, chv_ready, gmbus_reads, gmbus_ready;
static uint32_t chv_read(void)
{
    chv_reads++;
    return chv_reads >= chv_ready ? 3U << 8 : 0;
}
static uint32_t gmbus_read(void)
{
    gmbus_reads++;
    return gmbus_reads >= gmbus_ready ? 0x40U : 0;
}
"""
mock = mock.replace("int main(void)", helpers+"\nint main(void)")
marker = '    puts("IOPOLL_MOCK_C_RUNTIME_14_CASES_PASS");'
assert marker in mock
cases = r"""
    reset_state(); chv_reads = 0; chv_ready = 4;
    rc = poll_timeout_us(value = chv_read(),
          (value & DSPFREQSTAT_MASK_CHV) ==
              (3U << DSPFREQSTAT_SHIFT_CHV), 500, 50 * 1000, false);
    if (rc || chv_reads != 4 || sleep_count != 3 || value != (3U << 8))
        return 15;

    reset_state(); chv_reads = 0; chv_ready = UINT_MAX;
    rc = poll_timeout_us(value = chv_read(),
          (value & DSPFREQSTAT_MASK_CHV) ==
              (3U << DSPFREQSTAT_SHIFT_CHV), 500, 50 * 1000, false);
    if (rc != -ETIMEDOUT || chv_reads < 3) return 16;

    reset_state(); gmbus_reads = 0; gmbus_ready = 3;
    rc = poll_timeout_us_atomic(value = gmbus_read(),
                                value & 0x40U, 0, 2, false);
    if (rc || gmbus_reads != 3 || sleep_count || udelay_count)
        return 17;

    reset_state(); gmbus_reads = 0; gmbus_ready = 2010;
    rc = poll_timeout_us_atomic(value = gmbus_read(),
                                value & 0x40U, 0, 2, false);
    if (rc != -ETIMEDOUT || gmbus_reads < 2000) return 18;
    rc = poll_timeout_us(value = gmbus_read(),
                         value & 0x40U, 500, 50 * 1000, false);
    if (rc || value != 0x40U || gmbus_reads != 2010)
        return 19;

    reset_state(); gmbus_reads = 0; gmbus_ready = UINT_MAX;
    rc = poll_timeout_us_atomic(value = gmbus_read(),
                                value & 0x40U, 0, 2, false);
    if (rc != -ETIMEDOUT) return 20;
    rc = poll_timeout_us(value = gmbus_read(),
                         value & 0x40U, 500, 50 * 1000, false);
    if (rc != -ETIMEDOUT || value != 0U) return 21;

    puts("I915_CHV_CDCLK_GMBUS_POLL_5_C_CASES_PASS");
"""
mock = mock.replace(marker,cases+marker)
cc=shutil.which("cc")
assert cc is not None
with tempfile.TemporaryDirectory(prefix="i915-chv-gmbus-c-") as td:
    wd=Path(td)
    for key,text in v["STUBS"].items():
        p=wd/"mock"/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    p=wd/"case.c";p.write_text(mock)
    exe=wd/"case"
    subprocess.run([cc,"-std=gnu11","-O0","-Wall","-Wextra","-Werror",
                    "-I",str(wd/"mock"),
                    "-I",str(ROOT/"compat/native-runtime/iopoll/include"),
                    str(p),"-o",str(exe)],check=True,timeout=30)
    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,(result.returncode,result.stdout,result.stderr)
    assert "I915_CHV_CDCLK_GMBUS_POLL_5_C_CASES_PASS" in result.stdout
    print(result.stdout.strip())
print("HOST C MOCK ONLY: no NetBSD native ABI, PCI MMIO or KMS hardware proof")
