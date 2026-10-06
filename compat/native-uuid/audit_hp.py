#!/usr/bin/env python3
"""Read-only selected graph and native UUID compatibility audit on HP."""
from pathlib import Path
import hashlib
import json
import platform
import re
import socket
import subprocess

if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("HP-only audit")
WORK = Path("/root/hp-driver-port-20261005")
OUT = WORK / "agent-native-uuid"
STATUS = json.loads((WORK / "full-linux-graph-status.json").read_text())
DIST = WORK / "netbsd-full-linux/sys/external/bsd/drm2/dist"
PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*(?:uuid|guid|UUID|GUID)[A-Za-z_0-9]*\b|\b(?:uuid|guid|UUID|GUID)[A-Za-z_0-9]*\b")
sources, matches, headers = [], [], []
for group, names in STATUS["units"].items():
    for name in names:
        path = DIST / "drm" / ("" if group == "drm" else group) / name
        relative = str(path.relative_to(DIST))
        sources.append({"group": group, "path": relative,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for num, line in enumerate(path.read_text().splitlines(), 1):
            identifiers = sorted(set(PATTERN.findall(line)))
            if identifiers:
                matches.append({"path": relative, "line": num,
                                "identifiers": identifiers, "text": line.strip()})
for directory in [DIST / "drm", DIST / "include"]:
    for path in sorted(directory.rglob("*.h")):
        for num, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            identifiers = sorted(set(PATTERN.findall(line)))
            if identifiers:
                headers.append({"path": str(path.relative_to(DIST)), "line": num,
                                "identifiers": identifiers, "text": line.strip()})
native = subprocess.run(["git", "-C", "/root/netbsd-src-ref", "grep", "-n", "-E",
    r"guid_t|uuid_t|GUID_INIT|UUID_INIT|uuid_is_valid|guid_bytes",
    STATUS["netbsd_pin"], "--", "sys/external/bsd/drm2"], text=True,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if native.returncode not in (0, 1):
    raise SystemExit(native.stderr)
result = {"host": socket.gethostname(), "linux_pin": STATUS["linux_pin"],
    "netbsd_pin": STATUS["netbsd_pin"], "selected_c_count": len(sources),
    "group_counts": {group: len(names) for group, names in STATUS["units"].items()},
    "selected_c_matches": matches, "all_materialized_header_matches": headers,
    "selected_source_hashes": sources, "native_pin_matches": native.stdout.splitlines()}
(OUT / "uuid-call-audit.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"counts": result["group_counts"], "selected_c_count": len(sources),
                  "selected_c_matches": matches, "native_pin_matches": result["native_pin_matches"]}, indent=2))
