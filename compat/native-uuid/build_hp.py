#!/usr/bin/env python3
"""Build/test the isolated UUID candidate using the actual HP native toolchain."""
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
if ROOT.parent != WORK or not ROOT.name.startswith("uuid-integration-model-"):
    raise SystemExit("isolated HP candidate path required")
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
subprocess.run(["python3", str(ROOT / "generate.py")], check=True)
subprocess.run(["python3", str(ROOT / "tests/prepare.py")], check=True)
line = next(line for line in (WORK / "native-math64-drm_buddy.log").read_text().splitlines()
            if line.startswith(str(WORK / "full-linux-tools/bin/x86_64--netbsd-gcc "))
            and " -c " in line)
template = shlex.split(line)
checks = []
for src, obj in [("linux_uuid.c", "linux_uuid.o"),
                 ("tests/native_probe.c", "native-probe.o"),
                 ("tests/translated_namespace_probe.c", "namespace-probe.o"),
                 ("native_acpi.c", "native-acpi.o")]:
    argv = template.copy()
    argv[argv.index("-c") + 1] = str(ROOT / src)
    argv[argv.index("-o") + 1] = str(ROOT / obj)
    checks.append((obj.removesuffix(".o") + "-native-compile", argv, WORK / "full-linux-obj"))
checks.append(("userland-compile", ["/usr/bin/cc", "-D_NETBSD_SOURCE", "-std=gnu11", "-O2", "-g",
    "-Wall", "-Wextra", "-Werror", str(ROOT / "tests/test_uuid.c"),
    "-o", str(ROOT / "tests/test_uuid")], ROOT))
checks.append(("userland-test", [str(ROOT / "tests/test_uuid")], ROOT))
checks.append(("native-relocatable-link", [str(WORK / "full-linux-tools/bin/x86_64--netbsd-ld"),
    "-r", "-o", str(ROOT / "uuid-and-probes.o"), str(ROOT / "linux_uuid.o"),
    str(ROOT / "native-probe.o"), str(ROOT / "namespace-probe.o"), str(ROOT / "native-acpi.o")], ROOT))
results = []
for name, argv, cwd in checks:
    run = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=150)
    (ROOT / (name + ".log")).write_text(run.stdout)
    results.append({"check": name, "argv": argv, "cwd": str(cwd), "exit": run.returncode,
                    "log": name + ".log"})
    print(name, run.returncode, flush=True)
    print(run.stdout, flush=True)
    if run.returncode:
        (ROOT / "proof.json").write_text(json.dumps({"checks": results}, indent=2) + "\n")
        raise SystemExit(run.returncode)
nm = subprocess.check_output(["/usr/bin/nm", "-g", str(ROOT / "uuid-and-probes.o")], text=True)
(ROOT / "native-symbols.log").write_text(nm)
if " U cprng_strong" not in nm or " U kern_cprng" not in nm:
    raise SystemExit("native UUID generation must call the real native CPRNG")
if " T linux_acpi_evaluate_dsm" not in nm:
    raise SystemExit("native ACPI body must be compiled, not disabled by a config guard")
unresolved = [line for line in nm.splitlines() if " U " in line and
              any(name in line for name in ["uuid", "guid"])]
if unresolved:
    raise SystemExit("unresolved UUID/GUID API: " + repr(unresolved))
files = ["include/linux/uuid.h", "linux_uuid.c", "native_acpi.c", "native-uuid.patch", "uuid-namespace.json",
    "uuid-include-hygiene.patch", "include-hygiene-manifest.json",
    "generate.py", "build_hp.py", "audit_hp.py", "linux_uuid.o", "native-probe.o",
    "namespace-probe.o", "native-acpi.o", "uuid-and-probes.o", "tests/test_uuid.c", "tests/prepare.py",
    "tests/native_probe.c", "tests/linux_namespace_probe.c", "tests/translated_namespace_probe.c",
    "tests/test_uuid", "native-symbols.log"]
proof = {"host": socket.gethostname(), "os": platform.platform(), "checks": results,
    "files": {name: {"bytes": (ROOT / name).stat().st_size,
                     "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in files},
    "base_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((ROOT / "base").iterdir()) if path.is_file()},
    "unresolved_uuid_api": unresolved,
    "tests": "ABI/alignment/native aliases, endian static initializers, all-byte comparison, raw import/export, null objects, parse and invalid-output preservation, first36 prefix contract, 1024 OS-entropy adapter fills/version bits, 512 random parse roundtrips, native libuuid namespace coexistence",
    "acceptance": "OPEN: native kernel CPRNG execution, full selected graph link/hardware, hard-IRQ generation parity"}
(ROOT / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
print("REAL_NATIVE_CPRNG_BINDING_AND_UUID_SYMBOLS_RESOLVED", flush=True)
