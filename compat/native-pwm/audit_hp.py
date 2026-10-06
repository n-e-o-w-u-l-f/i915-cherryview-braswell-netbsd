#!/usr/bin/env python3
"""Read-only selected PWM/OF and pinned Kconfig/provider audit on HP."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import re
import socket
import subprocess

if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("HP-only audit")
WORK = Path("/root/hp-driver-port-20261005")
parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
OUT = args.out.resolve(strict=True)
STATUS = json.loads((WORK / "full-linux-graph-status.json").read_text())
DIST = WORK / "netbsd-full-linux/sys/external/bsd/drm2/dist"
PWM = re.compile(r"\b(?:pwm_[A-Za-z_0-9]+|pwmchip_[A-Za-z_0-9]+|devm_pwm[A-Za-z_0-9]*|devm_fwnode_pwm_get|PWM_[A-Za-z_0-9]+|PWMF_[A-Za-z_0-9]+|CONFIG_PWM[A-Za-z_0-9]*)\b")
OF = re.compile(r"\b(?:device_node|of_get_drm_[A-Za-z_0-9]+|CONFIG_OF)\b")
sources, pwm_matches, of_matches, headers = [], [], [], []
for group, names in STATUS["units"].items():
    for name in names:
        path = DIST / "drm" / ("" if group == "drm" else group) / name
        relative = str(path.relative_to(DIST))
        sources.append({"group": group, "path": relative,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for num, line in enumerate(path.read_text().splitlines(), 1):
            for pattern, target in [(PWM, pwm_matches), (OF, of_matches)]:
                identifiers = sorted(set(pattern.findall(line)))
                if identifiers:
                    target.append({"path": relative, "line": num,
                                   "identifiers": identifiers, "text": line.strip()})
for directory in [DIST / "drm", DIST / "include"]:
    for path in sorted(directory.rglob("*.h")):
        for num, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            identifiers = sorted(set(PWM.findall(line)))
            if identifiers:
                headers.append({"path": str(path.relative_to(DIST)), "line": num,
                                "identifiers": identifiers, "text": line.strip()})
def pinned(repo, args):
    run = subprocess.run(["git", "-C", repo] + args, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run.returncode not in (0, 1):
        raise RuntimeError(run.stderr)
    return run.stdout

kconfig = pinned("/root/linux-rtl8723be-ref-fresh", ["grep", "-n", "-E",
    r"(select|imply|depends on).* PWM([^A-Za-z0-9_]|$)", STATUS["linux_pin"], "--",
    "drivers/gpu/drm/*Kconfig*", "drivers/acpi/*Kconfig*", "drivers/platform/x86/*Kconfig*"])
paths = pinned("/root/netbsd-src-ref", ["ls-tree", "-r", "--name-only",
    STATUS["netbsd_pin"], "--", "sys/dev", "sys/arch", "share/man/man4"]).splitlines()
native_paths = [p for p in paths if re.search(r"pwm|lpss", p, re.I)]
result = {"host": socket.gethostname(), "linux_pin": STATUS["linux_pin"],
    "netbsd_pin": STATUS["netbsd_pin"], "profile": STATUS["profile"],
    "selected_c_count": len(sources),
    "group_counts": {group: len(names) for group, names in STATUS["units"].items()},
    "selected_pwm_matches": pwm_matches, "selected_of_pointer_matches": of_matches,
    "all_materialized_pwm_header_matches": headers, "selected_source_hashes": sources,
    "kconfig_pwm_constraint_matches": kconfig.splitlines(),
    "native_pwm_lpss_paths": native_paths,
    "profile_pwm_disabled": not any(STATUS["profile"].get(k) in ["y", "m", 1]
        for k in ["CONFIG_PWM", "CONFIG_PWM_MODULE"]),
    "provider_acceptance": "OPEN: native Linux consumer ownership/lookup and LPSS PWM driver absent; existing native PWM config is u_int nanoseconds"}
if len(sources) != 410 or not result["profile_pwm_disabled"]:
    raise SystemExit("expected frozen 410-unit disabled PWM profile")
(OUT / "pwm-call-audit.json").write_text(json.dumps(result, indent=2) + "\n")
print("PWM_FRESH_SHARED_STAGE_AUDIT", result["selected_c_count"],
    "pwm_disabled=" + str(result["profile_pwm_disabled"]),
    "pwm_calls=" + str(len(result["selected_pwm_matches"])))
