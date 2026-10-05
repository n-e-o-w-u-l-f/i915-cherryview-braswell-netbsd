#!/usr/bin/env python3
"""Check real Linux tristate helpers for builtin and native module compilation."""
import argparse
from pathlib import Path
import platform
import re
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--baseline", action="store_true")
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("compiler-invoking checks are authorized only on HP/NetBSD")
    native = ROOT / "compat/linux/kconfig.h"
    if a.baseline or not native.exists():
        text = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "show",
            "03d918f6d0e81fa05b8f1160eca0628ad39988a6:sys/external/bsd/common/include/linux/kernel.h"], text=True)
        text = "\n".join(line for line in text.splitlines()
            if re.match(r"#define\s+IS_(?:BUILTIN|ENABLED|REACHABLE|MODULE)\(", line)) + "\n"
    else:
        text = native.read_text()
    with tempfile.TemporaryDirectory(prefix="i915-tristate-") as directory:
        root = Path(directory); (root / "kconfig.h").write_text(text)
        for module in (False, True):
            code = ("#define _MODULE 1\n" if module else "") + '''
#define CONFIG_YES 1
#define CONFIG_ZERO 0
#define CONFIG_LOADABLE_MODULE 1
/* Exact native asm/byteorder.h marker: the config helper must not redefine it. */
#define __LITTLE_ENDIAN
#include "kconfig.h"
#include "kconfig.h"
_Static_assert(IS_BUILTIN(CONFIG_YES)==1,"builtin y");
_Static_assert(IS_ENABLED(CONFIG_YES)==1,"enabled y");
_Static_assert(IS_REACHABLE(CONFIG_YES)==1,"reachable y");
_Static_assert(IS_MODULE(CONFIG_YES)==0,"builtin is not module");
_Static_assert(IS_BUILTIN(CONFIG_ZERO)==0,"zero is disabled");
_Static_assert(IS_ENABLED(CONFIG_ZERO)==0,"zero is not enabled");
_Static_assert(IS_REACHABLE(CONFIG_ZERO)==0,"zero is not reachable");
_Static_assert(IS_MODULE(CONFIG_ZERO)==0,"zero is not module");
_Static_assert(IS_BUILTIN(CONFIG_UNDEFINED)==0,"undefined is disabled");
_Static_assert(IS_ENABLED(CONFIG_UNDEFINED)==0,"undefined is not enabled");
_Static_assert(IS_REACHABLE(CONFIG_UNDEFINED)==0,"undefined is not reachable");
_Static_assert(IS_MODULE(CONFIG_UNDEFINED)==0,"undefined is not module");
_Static_assert(IS_BUILTIN(CONFIG_LOADABLE)==0,"module is not builtin");
_Static_assert(IS_ENABLED(CONFIG_LOADABLE)==1,"module is enabled");
_Static_assert(IS_MODULE(CONFIG_LOADABLE)==1,"module option");
'''
            code += f'_Static_assert(IS_REACHABLE(CONFIG_LOADABLE)=={int(module)},"builtin/module linkage");\n'
            code += '''
#if !IS_ENABLED(CONFIG_UNDEFINED) && IS_BUILTIN(CONFIG_YES)
int main(void) { return 0; }
#else
#error Invalid preprocessor predicate
#endif
'''
            source = root / "test.c";source.write_text(code)
            binary = root / "test"
            subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
    print("LINUX_KCONFIG_HELPERS_OK: 32 predicates, native builtin/module linkage, CPP/C contexts")

if __name__ == "__main__":
    main()
