#!/usr/bin/env python3
"""Compile the exact imported release/acquire macros and check single evaluation.

Kernel barrier intrinsics are modelled by observable callbacks. The test checks
the production macro body and publication ordering, not CPU litmus coverage.
Compiler execution is restricted to the authorized HP host by its caller.
"""
import argparse
from pathlib import Path
import re
import platform
import socket
import subprocess
import tempfile

def macro(text, name):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"#define\s+" + name + r"\(", line):
            block = [line]
            while block[-1].endswith("\\"):
                index += 1; block.append(lines[index])
            return "\n".join(block) + "\n"
    return "/* macro missing: " + name + " */\n"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--apply-candidate", action="store_true")
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("compiler-invoking checks are authorized only on HP/NetBSD")
    candidate = None
    if a.apply_candidate:
        candidate = tempfile.TemporaryDirectory(prefix="i915-ordering-candidate-")
        root = Path(candidate.name)
        for relative in ("sys/external/bsd/common/include/linux/compiler.h",
                         "sys/external/bsd/drm2/include/linux/ktime.h"):
            target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
            # Frozen Git objects remain authoritative even if sparse input
            # files have not been materialized, or a worktree has other edits.
            original = subprocess.check_output(["git", "-C", str(a.netbsd_tree),
                "show", "03d918f6d0e81fa05b8f1160eca0628ad39988a6:" + relative])
            target.write_bytes(original)
        patch = Path(__file__).resolve().parents[1] / "patches/0018-netbsd-linux-memory-ordering.patch"
        subprocess.run(["git", "-C", str(root), "apply", "--check", str(patch)], check=True)
        subprocess.run(["git", "-C", str(root), "apply", str(patch)], check=True)
        a.netbsd_tree = root
    compiler = a.netbsd_tree / "sys/external/bsd/common/include/linux/compiler.h"
    text = compiler.read_text()
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static int memory, pointer_evals, value_evals, release_count, acquire_count;
static int *slot(void) { ++pointer_evals; return &memory; }
static int value(void) { ++value_evals; return 0x12345; }
static void membar_release(void) { assert(memory==0); ++release_count; }
static void membar_acquire(void) { assert(memory==0x12345); memory=0x54321; ++acquire_count; }
#undef __insn_barrier
static void __insn_barrier(void) { }
static void membar_datadep_consumer(void) { }
'''
    for name in ("READ_ONCE", "smp_store_release", "smp_load_acquire"):
        code += macro(text, name)
    ktime = (a.netbsd_tree / "sys/external/bsd/drm2/include/linux/ktime.h").read_text()
    compare = re.search(r"static inline int\s+ktime_compare\([^)]*\)\s*\{[^}]*\}", ktime)
    code += "typedef int64_t ktime_t;\n" + (compare[0] if compare else "/* ktime_compare missing */") + "\n"
    code += r'''
int main(void) {
 smp_store_release(*slot(),value());
 assert(memory==0x12345 && pointer_evals==1 && value_evals==1 && release_count==1);
 int observed=smp_load_acquire(*slot());
 assert(observed==0x12345 && pointer_evals==2 && acquire_count==1);
 assert(ktime_compare(INT64_MIN,INT64_MAX)==-1);
 assert(ktime_compare(INT64_MAX,INT64_MIN)==1);
 assert(ktime_compare(0,0)==0 && ktime_compare(-1,0)==-1 && ktime_compare(0,-1)==1);
 puts("LINUX_MEMORY_ORDERING_MACROS_OK: typed value, single evaluation, release/store/load/acquire");
 return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="i915-memory-ordering-") as directory:
        root = Path(directory); (root / "test.c").write_text(code)
        binary = root / "test"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=undefined", "-fno-sanitize-recover=all", str(root / "test.c"),
            "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    if candidate is not None:
        candidate.cleanup()

if __name__ == "__main__":
    main()
