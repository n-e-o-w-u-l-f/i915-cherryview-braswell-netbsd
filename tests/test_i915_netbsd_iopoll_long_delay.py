#!/usr/bin/env python3
"""Adversarial long-delay and LP64 no-truncation C contract for i915 iopoll.

Host userspace mocks only; never a NetBSD kernel compile/link.
"""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/test_i915_netbsd_iopoll_contract.py"
HEADER = ROOT / "compat/native-runtime/iopoll/include"
tree = ast.parse(BASE.read_text())
values = {
    target.id: ast.literal_eval(node.value)
    for node in tree.body if isinstance(node, ast.Assign)
    for target in node.targets if isinstance(target, ast.Name)
    if target.id in ("MOCK", "STUBS")
}
assert set(values) == {"MOCK", "STUBS"}
mock = values["MOCK"]
stubs = values["STUBS"].copy()
old = "static uint32_t fake_reg;"
replacement = old + "\nstatic unsigned long long total_udelay_us;\nstatic unsigned int max_udelay_us;"
assert mock.count(old) == 1
mock = mock.replace(old, replacement)
old = "    udelay_count++;"
replacement = """    udelay_count++;
    total_udelay_us += delay;
    if (delay > max_udelay_us) max_udelay_us = delay;"""
assert stubs["linux/delay.h"].count(old) == 1
stubs["linux/delay.h"] = stubs["linux/delay.h"].replace(old, replacement)
marker = '    puts("IOPOLL_MOCK_C_RUNTIME_14_CASES_PASS");'
assert mock.count(marker) == 1
cases = r"""
    reset_state();
    total_udelay_us = 0;
    max_udelay_us = 0;
    rc = poll_timeout_us_atomic(++samples, samples == 1, 2501UL, 0, true);
    if (rc != 0 || samples != 1 || total_udelay_us != 2501 ||
        max_udelay_us > 1000U || udelay_count != 3) return 15;

#if ULONG_MAX > UINT_MAX
    reset_state();
    total_udelay_us = 0;
    max_udelay_us = 0;
    rc = poll_timeout_us_atomic(++samples, samples == 1,
                               (unsigned long)UINT_MAX + 1UL, 0, true);
    if (rc != 0 || samples != 1 ||
        total_udelay_us != (unsigned long long)UINT_MAX + 1ULL ||
        max_udelay_us > 1000U) return 16;
#endif
    puts("IOPOLL_LONG_UDELAY_NO_TRUNCATION_C_TEST_PASS");
"""
mock = mock.replace(marker, cases)
compiler = shutil.which("cc")
if compiler is None:
    raise RuntimeError("Host C compiler unavailable")
with tempfile.TemporaryDirectory(prefix="i915-iopoll-long-delay-") as tmp:
    root = Path(tmp)
    for name, body in stubs.items():
        target = root / "stubs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    source = root / "long_delay.c"
    source.write_text(mock)
    exe = root / "iopoll_long_delay"
    subprocess.run(
        [compiler, "-std=gnu11", "-O0", "-Wall", "-Wextra", "-Werror",
         "-I", str(root / "stubs"), "-I", str(HEADER),
         str(source), "-o", str(exe)], check=True, timeout=30)
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    if run.returncode:
        raise RuntimeError("Long-delay C test failed with exit code " +
                           str(run.returncode) + ": " + run.stderr)
    assert "IOPOLL_LONG_UDELAY_NO_TRUNCATION_C_TEST_PASS" in run.stdout
    print(run.stdout.strip())
    print("LIMITATION: LP64 host mock; NetBSD kernel ABI and KMS not tested")
