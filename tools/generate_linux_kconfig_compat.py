#!/usr/bin/env python3
"""Port frozen Linux tristate helpers to NetBSD build-option inputs."""
import argparse
import difflib
from pathlib import Path
import subprocess

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
KERNEL = "sys/external/bsd/common/include/linux/kernel.h"

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--linux-tree", type=Path, required=True)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--header-out", type=Path, required=True)
    p.add_argument("--patch-out", type=Path, required=True)
    a = p.parse_args()
    for tree, pin in [(a.linux_tree, LINUX_PIN), (a.netbsd_tree, NETBSD_PIN)]:
        head = subprocess.check_output(["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
        if head != pin: p.error("wrong frozen reference revision")
    if a.header_out.exists() or a.patch_out.exists(): p.error("preserve existing output")
    header = subprocess.check_output(["git", "-C", str(a.linux_tree), "show", "HEAD:include/linux/kconfig.h"], text=True)
    old_include = "#include <generated/autoconf.h>"
    native_inputs = """/* Linux fd179f8a helpers, with NetBSD nbconfig/make options as inputs.
 * This does not synthesize Linux generated bounds or VM-layout definitions.
 */
#if defined(_MODULE) && !defined(MODULE)
#define MODULE 1
#endif"""
    if header.count(old_include) != 1: p.error("unexpected Linux kconfig header")
    header = header.replace(old_include, native_inputs)
    endian = "#ifdef CONFIG_CPU_BIG_ENDIAN\n#define __BIG_ENDIAN 4321\n#else\n#define __LITTLE_ENDIAN 1234\n#endif"
    if header.count(endian) != 1: p.error("unexpected Linux endian selection")
    header = header.replace(endian, "/* NetBSD asm/byteorder.h owns the native endian markers. */")
    old = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "show", "HEAD:" + KERNEL], text=True)
    obsolete = "#define\tIS_BUILTIN(option)\t(1) /* Probably... */\n#define\tIS_ENABLED(option)\t(option)\n#define\tIS_REACHABLE(option)\t(option)\n"
    if old.count(obsolete) != 1: p.error("unexpected native predicate baseline")
    new = old.replace(obsolete, "#include <linux/kconfig.h>\n")
    diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="a/" + KERNEL, tofile="b/" + KERNEL))
    for path, text in [(a.header_out, header), (a.patch_out, diff)]:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

if __name__ == "__main__":
    main()
