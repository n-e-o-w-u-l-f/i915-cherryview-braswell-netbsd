#!/usr/bin/env python3
"""Standalone userspace mock check; never compiles or links a NetBSD kernel."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "compat/native-runtime/iopoll/include/linux/iopoll.h"
CC = shutil.which("cc")
if CC is None:
    raise RuntimeError("host C compiler unavailable; synthetic test cannot PASS")

MOCK = "#include <stdio.h>\n#include <stdint.h>\n#include <stdbool.h>\n#include <stdlib.h>\n#include <errno.h>\n#include <limits.h>\n\nstatic uint64_t fake_ns, step_ns, last_delay_min, last_delay_max;\nstatic int relax_count, sleep_count, udelay_count, checked_sleep, samples;\nstatic uint32_t fake_reg;\n\nstatic void reset_state(void)\n{\n    fake_ns = step_ns = last_delay_min = last_delay_max = 0;\n    relax_count = sleep_count = udelay_count = checked_sleep = samples = 0;\n    fake_reg = 0;\n}\n#include <linux/iopoll.h>\nstatic uint32_t mock_accessor(void) { return (uint32_t)++samples; }\n\nint main(void)\n{\n    int rc;\n    uint32_t value = 0;\n    reset_state();\n    rc = poll_timeout_us(++samples, samples == 3, 100, 1000, false);\n    if (rc != 0 || samples != 3 || sleep_count != 2 || checked_sleep != 1) return 1;\n    reset_state();\n    step_ns = 6000;\n    rc = poll_timeout_us(++samples, samples == 1, 0, 5, false);\n    if (rc != 0 || samples != 1) return 2;\n    reset_state();\n    step_ns = 6000;\n    rc = poll_timeout_us(++samples, false, 0, 5, false);\n    if (rc != -ETIMEDOUT || samples != 1) return 3;\n    reset_state();\n    rc = poll_timeout_us(++samples, samples == 4, 0, 0, false);\n    if (rc != 0 || samples != 4) return 4;\n    reset_state();\n    rc = poll_timeout_us(++samples, samples == 1, 100, 1000, true);\n    if (rc != 0 || samples != 1 || sleep_count != 1 ||\n        last_delay_min != 26 || last_delay_max != 100) return 5;\n    reset_state();\n    rc = poll_timeout_us_atomic(++samples, samples == 2, 3, 5, true);\n    if (rc != 0 || samples != 2 || udelay_count != 2) return 6;\n    reset_state();\n    rc = poll_timeout_us_atomic(++samples, false, 3, 5, true);\n    if (rc != -ETIMEDOUT || samples != 2 || udelay_count != 2) return 7;\n    reset_state();\n    rc = poll_timeout_us_atomic(++samples, samples == 3, 0, 0, false);\n    if (rc != 0 || samples != 3 || udelay_count != 0) return 8;\n    reset_state();\n    rc = read_poll_timeout(mock_accessor, value, value == 3, 0, 0, false);\n    if (rc != 0 || value != 3 || samples != 3) return 9;\n    reset_state();\n    rc = read_poll_timeout_atomic(mock_accessor, value, value == 2, 1, 2, false);\n    if (rc != 0 || value != 2 || samples != 2) return 10;\n    reset_state();\n    rc = readl_poll_timeout(&fake_reg, value, value == 2, 1, 5);\n    if (rc != 0 || value != 2 || samples != 2) return 11;\n    reset_state();\n    rc = readl_relaxed_poll_timeout_atomic(&fake_reg, value, value == 2, 1, 5);\n    if (rc != 0 || value != 2 || samples != 2) return 12;\n    reset_state();\n    step_ns = 7000;\n    rc = readl_poll_timeout(&fake_reg, value, false, 0, 2);\n    if (rc != -ETIMEDOUT || samples != 1 || value != 1) return 13;\n    reset_state();\n    rc = poll_timeout_us(++samples, samples == 1, 0, UINT64_MAX, false);\n    if (rc != 0 || samples != 1) return 14;\n\n    puts(\"IOPOLL_MOCK_C_RUNTIME_14_CASES_PASS\");\n    return 0;\n}\n"

STUBS = {
    "linux/types.h": """
#ifndef MOCK_TYPES_H
#define MOCK_TYPES_H
#include <stdbool.h>
#include <stdint.h>
#endif
""",
    "linux/kernel.h": """
#ifndef MOCK_KERNEL_H
#define MOCK_KERNEL_H
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#define might_sleep_if(c) do { if (c) checked_sleep++; } while (0)
#define barrier() __asm__ __volatile__("" ::: "memory")
#endif
""",
    "linux/ktime.h": """
typedef int64_t ktime_t;
static inline ktime_t ktime_get(void) {
    ktime_t result = (ktime_t)fake_ns;
    fake_ns += step_ns;
    return result;
}
""",
    "linux/delay.h": """
static inline void usleep_range(unsigned long minimum, unsigned long maximum) {
    sleep_count++;
    last_delay_min = minimum;
    last_delay_max = maximum;
    fake_ns += (uint64_t)minimum * 1000u;
}
static inline void udelay(unsigned int delay) {
    udelay_count++;
    fake_ns += (uint64_t)delay * 1000u;
}
""",
    "linux/time.h": "#define NSEC_PER_USEC 1000ULL\n",
    "linux/io.h": """
#define MOCK_READ_FUNC(name, type) \\
  static inline type name(const void *addr) { (void)addr; return (type)++samples; }
MOCK_READ_FUNC(readb, uint8_t)
MOCK_READ_FUNC(readw, uint16_t)
MOCK_READ_FUNC(readl, uint32_t)
MOCK_READ_FUNC(readq, uint64_t)
MOCK_READ_FUNC(readb_relaxed, uint8_t)
MOCK_READ_FUNC(readw_relaxed, uint16_t)
MOCK_READ_FUNC(readl_relaxed, uint32_t)
MOCK_READ_FUNC(readq_relaxed, uint64_t)
""",
    "asm/processor.h": """
#define cpu_relax() do { relax_count++; fake_ns++; } while (0)
""",
    "sys/errno.h": "#include <errno.h>\n",
    "sys/types.h": "#include <stdint.h>\n",
}

with tempfile.TemporaryDirectory(prefix="i915-iopoll-mocks-") as tmp:
    wd = Path(tmp)
    for name, content in STUBS.items():
        target = wd / "mocks" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    src = wd / "test_iopoll.c"
    src.write_text(MOCK)
    executable = wd / "test_iopoll"
    compile_cmd = [CC, "-std=gnu11", "-O0", "-Wall", "-Wextra",
                   "-Werror", "-I", str(wd / "mocks"),
                   "-I", str(HEADER.parent.parent),
                   str(src), "-o", str(executable)]
    subprocess.run(compile_cmd, check=True, timeout=25)
    tested = subprocess.run([str(executable)], check=True,
                            capture_output=True, text=True, timeout=15)
    assert "IOPOLL_MOCK_C_RUNTIME_14_CASES_PASS" in tested.stdout
    print(tested.stdout.strip())
    print("LIMITATION: synthetic LinuxKPI stubs on a host userspace compiler; "
          "not NetBSD kernel ABI, HP runtime or i915 display validation")
