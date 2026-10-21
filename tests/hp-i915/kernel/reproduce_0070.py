#!/usr/bin/env python3
"""Reproduce 0070 real NetBSD11 DRM connector kernel test, isolated QEMU only.

Never run on or transfer to physical HP. Requires 0069 scratch source/obj,
NetBSD cross toolchain, QEMU TCG, immutable 0066 guest disk, no network.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

TOOL = "/opt/ChatGPT/hp-driver-port/netbsd-tools-03d918f6/bin/nbmake-amd64"
DISK_SHA = "1210c3130785f399b4cc17e1cf32f1b3195a167f80fb7d9c39b91fafc495e586"
EXPECTED = ("HP_I915_0070_DRM_CONNECTOR_PASS init=1 no_dev=1 fail=1 "
            "success=1 unreg=1 cleanup=1 late=2 early=1 sysfs_stub=1 gpu=0")
ROOT = Path("/var/lib/sentinelx/uploads")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def build(out, name, targets, timeout):
    with (out / (name + ".stdout")).open("wb") as so, \
         (out / (name + ".stderr")).open("wb") as se:
        result = subprocess.run([TOOL, "-j6", *targets], cwd=out / "obj",
                                stdout=so, stderr=se, timeout=timeout)
    record = {
        "rc": result.returncode,
        "stderr_bytes": (out / (name + ".stderr")).stat().st_size,
        "stdout_bytes": (out / (name + ".stdout")).stat().st_size,
    }
    if result.returncode or record["stderr_bytes"]:
        raise RuntimeError(name + " failed: " + repr(record) +
                           "\n" + (out / (name + ".stdout")).read_text(
                               errors="replace")[-1500:])
    return record


def qemu(out, disk, kernel, label):
    dbg = out / (label + ".debugcon.txt")
    cmd = ["/usr/bin/qemu-system-x86_64", "-machine", "pc,accel=tcg",
           "-cpu", "qemu64", "-m", "768", "-smp", "1", "-nodefaults",
           "-no-reboot", "-vga", "std", "-display", "none",
           "-monitor", "stdio", "-serial", "null", "-nic", "none",
           "-drive", f"file={disk},format=raw,if=ide,index=0,snapshot=on",
           "-kernel", str(kernel), "-append", "root=wd0a",
           "-debugcon", f"file:{dbg}",
           "-global", "isa-debugcon.iobase=0xe9"]
    t = time.monotonic()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(13)
        if p.poll() is None:
            stdout, stderr = p.communicate("quit\n", timeout=10)
        else:
            stdout, stderr = p.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        p.kill()
        stdout, stderr = p.communicate(timeout=6)
    lines = dbg.read_text(errors="replace").splitlines() if dbg.exists() else []
    markers = [line for line in lines if
               line.startswith("HP_I915_0070_DRM_CONNECTOR_")]
    positive = label.startswith("positive")
    ok = (p.returncode == 0 and not stderr and
          (markers == [EXPECTED] if positive else markers == []) and
          any(line.startswith("HP_I915_0069_KERNEL_PROBE_PASS")
              for line in lines))
    return {"label": label, "qemu_exit": p.returncode,
            "seconds": round(time.monotonic() - t, 2),
            "stderr_bytes": len(stderr), "debugcon_lines": lines,
            "pass": ok, "qemu_monitor_exit_not_guest_shutdown": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--disk", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base, disk, out = (x.resolve() for x in
                       (args.baseline, args.disk, args.out))
    patch = Path(__file__).resolve().with_name(
        "0070-qemu-real-drm-connector.patch")
    if (base.name != "i915-0069-qemu-kernel-probe-20261021-a01" or
        not str(out).startswith(str(ROOT) + "/") or
        not out.name.startswith("i915-0070-replay-") or
        out.exists() or not patch.is_file() or
        sha(disk) != DISK_SHA):
        raise SystemExit("SAFETY_PREFLIGHT_FAILED: refuse unexpected paths/disk")
    baseline_kernel = base / "obj/netbsd"
    originals = {
        "baseline_kernel": sha(baseline_kernel),
        "disk": sha(disk),
    }
    out.mkdir(mode=0o700)
    for sub in ("netbsd", "obj"):
        subprocess.run(["cp", "-a", "--reflink=auto", str(base / sub),
                        str(out / sub)], check=True, timeout=250)
    mk = out / "obj/Makefile"
    m = mk.read_text()
    if str(base / "netbsd") not in m:
        raise RuntimeError("baseline Makefile source mismatch")
    mk.write_text(m.replace(str(base / "netbsd"),
                            str(out / "netbsd")))
    apply = subprocess.run(["patch", "-p1", "--batch", "--forward",
                            "--input", str(patch)], cwd=out,
                           capture_output=True, text=True, timeout=30)
    if apply.returncode:
        raise RuntimeError("patch apply failed: " + apply.stdout +
                           apply.stderr)
    compilation = build(out, "0070-replay-compile",
                        ["drm_connector.o", "init_main.o"], 240)
    linkage = build(out, "0070-replay-link", ["netbsd"], 400)
    new_kernel = out / "obj/netbsd"
    runs = [qemu(out, disk, baseline_kernel, "negative_0069"),
            qemu(out, disk, new_kernel, "positive_1"),
            qemu(out, disk, new_kernel, "positive_2")]
    after = {
        "baseline_kernel": sha(baseline_kernel),
        "disk": sha(disk),
    }
    result = {
        "status": "PASS" if all(x["pass"] for x in runs) and
                  originals == after else "FAIL",
        "compile": compilation, "link": linkage,
        "kernel_sha256": sha(new_kernel),
        "baseline_and_disk_immutable": originals == after,
        "before": originals, "after": after, "runs": runs,
        "scope": "real NetBSD DRM core functions; synthetic DRM device; "
                 "no Intel GPU, no PCI attach, no physical HP",
    }
    (out / "0070-reproduction-result.json").write_text(
        json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}))
    for run in runs:
        print(json.dumps({"label": run["label"], "pass": run["pass"],
                          "debugcon_lines": run["debugcon_lines"]}))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
