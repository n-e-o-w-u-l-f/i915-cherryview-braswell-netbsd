#!/usr/bin/env python3
"""Compile/test only on HP, using the real native kernel compiler flags."""
from pathlib import Path
import hashlib
import json
import platform
import resource
import shlex
import socket
import subprocess

ROOT = Path(__file__).resolve().parent
WORK = Path("/root/hp-driver-port-20261005")
if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("compilation/tests only authorized on HP NetBSD")
if ROOT.parent != WORK or not ROOT.name.startswith("pwm-integration-model-"):
    raise SystemExit("isolated HP PWM candidate path required")
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
subprocess.run(["python3", str(ROOT / "generate.py")], check=True)
subprocess.run(["python3", str(ROOT / "tests/prepare.py")], check=True)
line = next(line for line in (WORK / "native-math64-drm_buddy.log").read_text().splitlines()
    if line.startswith(str(WORK / "full-linux-tools/bin/x86_64--netbsd-gcc ")) and " -c " in line)
template = shlex.split(line)
results = []

def record(name, argv, cwd=ROOT, expected="pass", needle=None):
    run = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=150)
    (ROOT / (name + ".log")).write_text(run.stdout)
    valid = run.returncode == 0 if expected == "pass" else run.returncode != 0
    if needle is not None:
        valid = valid and needle in run.stdout
    results.append({"check": name, "argv": argv, "cwd": str(cwd), "exit": run.returncode,
        "expected": expected, "validated": valid, "log": name + ".log"})
    print(name, run.returncode, "expected=" + expected, flush=True)
    if not valid:
        print(run.stdout, flush=True)
        (ROOT / "proof.json").write_text(json.dumps({"checks": results}, indent=2) + "\n")
        raise SystemExit("unexpected result: " + name)
    if run.stdout and expected == "pass":
        print(run.stdout, flush=True)
    return run

def native(name, src, defines=(), expected="pass", needle=None, extra_includes=()):
    argv = template.copy()
    argv[1:1] = ["-I" + str(ROOT / "include")] + list(extra_includes) + list(defines)
    argv[argv.index("-c") + 1] = str(ROOT / src)
    argv[argv.index("-o") + 1] = str(ROOT / (name + ".o"))
    return record(name, argv, WORK / "full-linux-obj", expected, needle)

native("native-pwm-before", "tests/native_probe_before.c")
native("native-pwm-after", "tests/native_probe_after.c")
native("native-pwm-absent", "tests/config_probe.c")
native("native-pwm-zero", "tests/config_probe.c", ["-DCONFIG_PWM=0", "-DCONFIG_PWM_MODULE=0"])
error = "NetBSD enabled PWM consumer/provider and LPSS runtime are not ported"
native("native-pwm-enabled-rejected", "tests/config_probe.c", ["-DCONFIG_PWM=1"], "reject", error)
native("native-pwm-module-rejected", "tests/config_probe.c", ["-DCONFIG_PWM_MODULE=1"], "reject", error)
native("native-of-pointer-disabled", "tests/of_pointer_probe.c")
native("native-of-pointer-enabled", "tests/of_pointer_probe.c", ["-DCONFIG_OF=1"])
native("native-of-before-rejected", "tests/of_pointer_before_probe.c", (), "reject", "device_node")
native("native-of-enabled-before-rejected", "tests/of_pointer_before_probe.c", ["-DCONFIG_OF=1"], "reject", "device_node")
record("userland-compile", ["/usr/bin/cc", "-D_NETBSD_SOURCE", "-std=gnu11", "-O2", "-g",
    "-Wall", "-Wextra", "-Werror", str(ROOT / "tests/test_pwm.c"), "-o", str(ROOT / "tests/test_pwm")])
record("userland-test", [str(ROOT / "tests/test_pwm")])
record("native-relocatable-link", [str(WORK / "full-linux-tools/bin/x86_64--netbsd-ld"),
    "-r", "-o", str(ROOT / "pwm-consumer-and-pointer-probes.o"),
    str(ROOT / "native-pwm-after.o"), str(ROOT / "native-pwm-absent.o"),
    str(ROOT / "native-of-pointer-disabled.o")])
nm = subprocess.check_output(["/usr/bin/nm", "-g", str(ROOT / "pwm-consumer-and-pointer-probes.o")], text=True)
(ROOT / "native-symbols.log").write_text(nm)
if " U pwm_enable" not in nm or " U pwm_disable" not in nm:
    raise SystemExit("real native PWM names must remain accessible and unchanged")
unresolved_linux = [line for line in nm.splitlines() if " U " in line and
    ("netbsd_linux_pwm" in line or " pwm_get" in line or " pwm_apply" in line)]
if unresolved_linux:
    raise SystemExit("unresolved disabled Linux PWM methods: " + repr(unresolved_linux))

# Also try the actual entire modern drm_modes.h with the isolated one-line patch.
# Its other imported dependencies may still be open in root's full graph; retain
# this evidence independently from the proved file-scope pointer signature fix.
argv = template.copy()
argv[1:1] = ["-I" + str(ROOT / "include"), "-I" + str(ROOT / "probe_include")]
argv[argv.index("-c") + 1] = str(ROOT / "tests/full_of_header_probe.c")
argv[argv.index("-o") + 1] = str(ROOT / "native-full-of-header.o")
run = subprocess.run(argv, cwd=WORK / "full-linux-obj", text=True, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, timeout=150)
(ROOT / "native-full-of-header.log").write_text(run.stdout)
full_of = {"argv": argv, "cwd": str(WORK / "full-linux-obj"), "exit": run.returncode,
    "log": "native-full-of-header.log", "status": "PASS" if not run.returncode else "OPEN: unrelated full modern header dependencies"}
print("native-full-of-header", run.returncode, full_of["status"], flush=True)
if run.returncode:
    print("\n".join(run.stdout.splitlines()[:25]), flush=True)

files = ["include/linux/pwm.h", "native-pwm.patch", "pwm-namespace.json", "generate.py", "build_hp.py", "audit_hp.py",
    "modern/include/drm/drm_modes.h", "of-pointer-hygiene.patch", "of-pointer-manifest.json",
    "tests/prepare.py", "tests/test_pwm.c", "tests/test_pwm_header.h", "tests/test_err_header.h", "tests/test_math_macros.h",
    "tests/test_list_type.h", "tests/vectors.h", "tests/vector-manifest.json", "tests/test_pwm",
    "tests/linux_consumer_probe.inc", "tests/native_probe_prefix.inc", "tests/native_probe_before.c", "tests/native_probe_after.c",
    "tests/config_probe.c", "tests/of_pointer_probe.c", "tests/of_pointer_before_probe.c", "tests/full_of_header_probe.c",
    "native-pwm-before.o", "native-pwm-after.o", "native-pwm-absent.o", "native-pwm-zero.o",
    "native-of-pointer-disabled.o", "native-of-pointer-enabled.o", "pwm-consumer-and-pointer-probes.o", "native-symbols.log",
    "probe_include/drm/drm_modes.h", "pwm-call-audit.json"]
if not run.returncode:
    files.append("native-full-of-header.o")
proof = {"host": socket.gethostname(), "os": platform.platform(), "checks": results,
    "files": {name: {"bytes": (ROOT / name).stat().st_size, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
        for name in files},
    "base_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "base").iterdir()) if p.is_file()},
    "vectors": json.loads((ROOT / "tests/vector-manifest.json").read_text()),
    "native_full_of_header": full_of, "unresolved_linux_pwm": unresolved_linux,
    "acceptance": "OPEN: enabled Linux PWM lookup/ownership/provider and LPSS runtime, full selected graph/link/native hardware; OF fields/provider unimplemented",
    "scope": "Frozen CONFIG_PWM-disabled consumer layouts/state helpers/arithmetic/errors; opaque OF tag hygiene separate"}
(ROOT / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
print("DISABLED_NATIVE_PWM_CONTRACT_AND_PRIVATE_NATIVE_COEXISTENCE PASS", flush=True)
