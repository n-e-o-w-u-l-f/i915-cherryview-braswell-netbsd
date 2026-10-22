#!/usr/bin/env python3
"""Offline/static safety gate for NetBSD 11 kernel compilation flags.
Never executes a command. Passing this check DOES NOT establish kernel build,
driver operation, QEMU or hardware functionality.
Derived from NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6:
sys/conf/Makefile.kern.inc, sys/arch/amd64/conf/Makefile.amd64.
"""
import argparse
import json
import os
import shlex


def inspect(text, root="/usr/src/sys", drm=False):
    items = shlex.split(text)
    flags = set(items)
    inc, defs, errors = set(), set(), []
    idx = 0
    while idx < len(items):
        a = items[idx]
        if a in ("-I", "-D"):
            if idx + 1 == len(items):
                errors.append("missing operand for " + a)
                break
            (inc if a == "-I" else defs).add(items[idx + 1])
            idx += 2
            continue
        if a.startswith("-I") and len(a) > 2:
            inc.add(a[2:])
        if a.startswith("-D") and len(a) > 2:
            defs.add(a[2:])
        idx += 1
    paths = {os.path.normpath(v) for v in inc}
    base = os.path.normpath(root)
    if "-nostdinc" not in flags:
        errors.append("missing -nostdinc: userspace headers may leak")
    if "/usr/include" in paths:
        errors.append("userspace /usr/include explicitly selected")
    for path in (".", base, base + "/arch", base + "/../common/include"):
        if os.path.normpath(path) not in paths:
            errors.append("missing kernel include " + path)
    defined = {v.split("=", 1)[0] for v in defs}
    for f in ("_KERNEL", "_KERNEL_OPT", "amd64", "x86_64"):
        if f not in defined:
            errors.append("missing -D" + f)
    for f in ("-mcmodel=kernel", "-mno-red-zone", "-ffreestanding", "-c"):
        if f not in flags:
            errors.append("missing " + f)
    if drm:
        for part in ("external/bsd/drm2/include", "external/bsd/common/include"):
            if os.path.normpath(base + "/" + part) not in paths:
                errors.append("missing DRM overlay -I" + part)
    return errors


GOOD = ("cc -D_KERNEL -D_KERNEL_OPT -Damd64 -Dx86_64 -nostdinc "
        "-I. -I/usr/src/sys -I/usr/src/sys/arch "
        "-I/usr/src/sys/../common/include -mcmodel=kernel "
        "-mno-red-zone -ffreestanding -c kernel_probe.c -o kernel_probe.o")
BAD_0081 = ("/usr/bin/cc -v -std=gnu11 -O2 -Wall -Wextra -Werror "
            "-D_KERNEL -ffreestanding -c kernel_probe.c -o kernel_probe.o")


def test():
    cases = []
    def verify(name, cond):
        assert cond, name
        cases.append(name)
    verify("complete illustrative flags accepted", inspect(GOOD) == [])
    verify("exact 0081 failed command rejected", bool(inspect(BAD_0081)))
    for f in ("-nostdinc", "-I.", "-I/usr/src/sys",
              "-I/usr/src/sys/arch", "-I/usr/src/sys/../common/include",
              "-D_KERNEL", "-D_KERNEL_OPT", "-Damd64", "-Dx86_64",
              "-mcmodel=kernel", "-mno-red-zone", "-ffreestanding", "-c"):
        verify("removed " + f + " rejected",
               bool(inspect(" ".join(x for x in GOOD.split() if x != f))))
    verify("explicit userspace include rejected",
           bool(inspect(GOOD + " -I/usr/include")))
    verify("split -I operand accepted",
           not inspect(GOOD.replace("-I/usr/src/sys ", "-I /usr/src/sys ")))
    verify("DRM missing overlay rejected", bool(inspect(GOOD, drm=True)))
    verify("DRM overlay accepted",
           not inspect(GOOD + " -I/usr/src/sys/external/bsd/drm2/include"
                       " -I/usr/src/sys/external/bsd/common/include", drm=True))
    return {"status": "PASS", "cases": len(cases),
            "scope": "synthetic static command validation only"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--command", help="literal command text; never executed")
    parser.add_argument("--source-root", default="/usr/src/sys")
    parser.add_argument("--drm", action="store_true")
    opts = parser.parse_args()
    if opts.self_test:
        result = test()
    else:
        if opts.command is None:
            parser.error("pass --command or --self-test")
        issues = inspect(opts.command, opts.source_root, opts.drm)
        result = {"status": "FAIL" if issues else "PASS_STATIC_ONLY",
                  "errors": issues, "scope": "textual flags, not compiler execution"}
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "FAIL":
        raise SystemExit(2)
