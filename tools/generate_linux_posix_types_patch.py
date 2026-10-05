#!/usr/bin/env python3
"""Make native Linux scalar types expose the frozen Linux UAPI POSIX types.

The UAPI definitions come from the pinned Linux include/uapi and x86/uapi
headers, materialized by the API input importer. They are not NetBSD typedef
aliases: notably Linux old_uid/dev and long-sized ioctl members differ from
their native OS counterparts. This patch does not port ioctl dispatch.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
TYPES = "sys/external/bsd/common/include/linux/types.h"

def transform(old):
    anchor = "#include <sys/stdint.h>\n"
    if old.count(anchor) != 1:
        raise ValueError("unexpected frozen native types header")
    new = old.replace(anchor, anchor + "\n/* Linux ioctl scalar ABI, using the pinned architecture UAPI definitions. */\n#include <linux/posix_types.h>\n")
    # Linux's asm-generic/int-ll64.h uses long long even on LP64. Equal
    # widths alone do not preserve type compatibility or printf contracts.
    for native, linux in [("uint64_t", "unsigned long long"), ("int64_t", "long long")]:
        for name in (["u64", "__u64", "__le64", "__be64"] if native == "uint64_t" else ["s64", "__s64"]):
            before = "typedef " + native + " " + name + ";"
            if new.count(before) != 1: raise ValueError("unexpected native " + name + " type")
            new = new.replace(before, "typedef " + linux + " " + name + ";")
    return new

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    head = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN: p.error("expected frozen NetBSD reference")
    if a.out.exists(): p.error("preserve existing output")
    old = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "show", "HEAD:" + TYPES], text=True)
    new = transform(old)
    diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="a/" + TYPES, tofile="b/" + TYPES))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(diff)

if __name__ == "__main__":
    main()
