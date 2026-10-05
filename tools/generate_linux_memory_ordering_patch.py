#!/usr/bin/env python3
"""Generate native memory-ordering/time adapter changes against the NetBSD pin."""
import argparse
import difflib
from pathlib import Path
import subprocess

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
COMPILER = "sys/external/bsd/common/include/linux/compiler.h"
KTIME = "sys/external/bsd/drm2/include/linux/ktime.h"

def transform(path, old):
    if path == COMPILER:
        marker = "#define\tsmp_store_release(X, V)"
        before, body = old.split(marker, 1)
        if body.count("(X) = __write_once_tmp;") != 1:
            raise ValueError("unexpected release-store baseline")
        body = body.replace("(X) = __write_once_tmp;", "(X) = __smp_store_release_tmp;")
        new = before + marker + body
        anchor = "#endif\t/* _LINUX_COMPILER_H_ */"
        addition = (
            "/* Linux acquire-load: read once before the native acquire barrier. */\n"
            "#define\tsmp_load_acquire(X)\t({\t\t\t\t\t      \\\n"
            "\ttypeof(X) __smp_load_acquire_tmp = READ_ONCE(X);\t\t      \\\n"
            "\tmembar_acquire();\t\t\t\t\t\t      \\\n"
            "\t__smp_load_acquire_tmp;\t\t\t\t\t      \\\n"
            "})\n\n")
        if new.count(anchor) != 1: raise ValueError("unexpected compiler guard")
        return new.replace(anchor, addition + anchor)
    if path == KTIME:
        anchor = "static inline bool\nktime_after(ktime_t a, ktime_t b)"
        if old.count(anchor) != 1: raise ValueError("unexpected ktime baseline")
        addition = """/* Compare without subtracting: preserve signed extrema without overflow. */
static inline int
ktime_compare(ktime_t a, ktime_t b)
{
\tif (a < b)
\t\treturn -1;
\tif (a > b)
\t\treturn 1;
\treturn 0;
}

"""
        return old.replace(anchor, addition + anchor)
    raise ValueError(path)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    head = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN: p.error("expected frozen NetBSD reference")
    if a.out.exists(): p.error("preserve existing patch output")
    patch = []
    for path in (COMPILER, KTIME):
        old = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "show", "HEAD:" + path], text=True)
        new = transform(path, old)
        patch.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/" + path, tofile="b/" + path))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(patch))

if __name__ == "__main__":
    main()
