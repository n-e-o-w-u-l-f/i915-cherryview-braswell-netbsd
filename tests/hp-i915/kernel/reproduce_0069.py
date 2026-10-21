#!/usr/bin/env python3
"""HP-I915-0069 QEMU-only genuine NetBSD kernel probe-helper regression."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import time

EXPECTED = ("HP_I915_0069_KERNEL_PROBE_PASS disabled=0 before=0 "
            "hit=-14 after=0 fired=1 cleared=1 restored=1 old_param=0")
BASE_SHA = "22d0fd9e4c1aa3eac10cd6a4b0c67de6c16820aeba0150e38a8f6bb65195028e"
DISK_SHA = "1210c3130785f399b4cc17e1cf32f1b3195a167f80fb7d9c39b91fafc495e586"

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run_checked(args, cwd, log, timeout=480):
    with open(log, "wb") as stdout, open(str(log) + ".stderr", "wb") as stderr:
        r = subprocess.run(args, cwd=cwd, stdout=stdout, stderr=stderr, timeout=timeout)
    if r.returncode:
        raise RuntimeError("command failed: %r; see %s.stderr" % (args, log))

def boot(kernel, disk, out, label, seconds=10):
    debugcon = out / (label + ".debugcon.txt")
    args = ["/usr/bin/qemu-system-x86_64", "-machine", "pc,accel=tcg",
            "-cpu", "qemu64", "-m", "768", "-smp", "1", "-nodefaults",
            "-no-reboot", "-vga", "std", "-display", "none",
            "-monitor", "stdio", "-serial", "null", "-nic", "none",
            "-debugcon", "file:" + str(debugcon),
            "-global", "isa-debugcon.iobase=0xe9",
            "-drive", "file=%s,format=raw,if=ide,index=0,snapshot=on" % disk,
            "-kernel", str(kernel), "-append", "root=wd0a"]
    p = subprocess.Popen(args, cwd=out, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(seconds)
        if p.poll() is None:
            p.stdin.write(b"quit\n")
            p.stdin.flush()
        stdout, stderr = p.communicate(timeout=12)
    finally:
        if p.poll() is None:
            p.kill()
            p.communicate()
    data = debugcon.read_bytes()
    if p.returncode or stderr:
        raise RuntimeError("QEMU %s failed: exit=%s stderr=%r" %
                           (label, p.returncode, stderr[-300:]))
    return data.decode("ascii", "strict").splitlines()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-0064", required=True, type=pathlib.Path)
    ap.add_argument("--disk", required=True, type=pathlib.Path)
    ap.add_argument("--output", required=True, type=pathlib.Path)
    ap.add_argument("--patch", type=pathlib.Path,
                    default=pathlib.Path(__file__).with_name("0069-qemu-probe-selftest.patch"))
    ap.add_argument("--make", default="/opt/ChatGPT/hp-driver-port/netbsd-tools-03d918f6/bin/nbmake-amd64")
    args = ap.parse_args()
    base, dest = args.baseline_0064.resolve(), args.output.resolve()
    assert dest != base and not dest.exists(), "destination must be new"
    assert digest(base / "obj/netbsd") == BASE_SHA, "0064 baseline SHA mismatch"
    assert digest(args.disk) == DISK_SHA, "NetBSD11 guest image SHA mismatch"
    dest.mkdir(parents=True)
    for name in ("netbsd", "obj"):
        run_checked(["cp", "-a", "--reflink=auto", str(base / name), str(dest / name)],
                    dest, dest / ("copy-" + name + ".log"), 240)
    mk = dest / "obj/Makefile"
    old = str(base / "netbsd/sys")
    new = str(dest / "netbsd/sys")
    original = mk.read_text()
    assert original.count(old) >= 1, "Makefile source root missing"
    mk.write_text(original.replace(old, new))
    run_checked(["patch", "-p1", "--batch", "--forward", "-i", str(args.patch.resolve())],
                dest, dest / "apply-patch.log", 30)
    for target in ("i915_utils.o", "init_main.o", "netbsd"):
        run_checked(["nice", "-n", "10", args.make, "-j6", target],
                    dest / "obj", dest / ("build-" + target + ".log"))
    kernel = dest / "obj/netbsd"
    assert digest(kernel) != BASE_SHA, "test kernel not distinct"
    assert boot(base / "obj/netbsd", args.disk, dest, "control-0064", 9) == [], "negative control not empty"
    results = [boot(kernel, args.disk, dest, "positive-%d" % n) for n in (1, 2)]
    assert results == [[EXPECTED], [EXPECTED]], "unexpected kernel probe result: %r" % results
    assert digest(base / "obj/netbsd") == BASE_SHA, "baseline changed"
    assert digest(args.disk) == DISK_SHA, "guest disk changed"
    result = {"status": "PASS_REAL_NETBSD_KERNEL_HELPER_TWO_RUNS",
              "diagnostic_kernel_sha256": digest(kernel),
              "negative_control": [], "positive_runs": results,
              "original_0064_sha256": BASE_SHA, "guest_disk_sha256": DISK_SHA,
              "no_physical_hp": True, "no_real_connector_gpu": True}
    (dest / "0069-reproduction-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
