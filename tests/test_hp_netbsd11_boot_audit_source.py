#!/usr/bin/env python3
"""Read-only NetBSD BIOS/UEFI boot inventory contract and mock-shell audit."""
from pathlib import Path
import importlib.util
import json
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/audit_hp_netbsd11_boot_readonly.sh"
RENDER = ROOT / "tools/render_hp_netbsd11_four_boot_modes.py"
assert SCRIPT.is_file() and RENDER.is_file()
text = SCRIPT.read_text()
assert re.search(r"^if \[ \"\$\(uname -s", text, re.M)
for phrase in (
    "ONLY_NATIVE_NETBSD", "READ_ONLY_NO_MUTATIONS",
    "machdep.booted_kernel", "/netbsd-11-i915-rtl-diag",
    "/netbsd-11-xfce4", "/netbsd-11-kde", "/netbsd-11-shell",
    "authoritative_boot_cfg=UNKNOWN_REQUIRE_LOADER_AND_ESP_CHECK",
    "AUDIT_BOOTLOADER=UNKNOWN_REQUIRE_PHYSICAL_BIOS_UEFI_CHECK",
    "/EFI/NetBSD/boot.cfg", "/boot.cfg", "f77_recovery_sha256=UNKNOWN",
    "xfce4_session", "kde_plasma_x11", "kernel_syslog_route",
    "/var/log/hp-kernel-boot.log", "/var/run/dmesg.boot",
):
    assert phrase in text, "missing grounded inventory field: " + phrase

# The auditor is strictly read-only and must NEVER pretend to install or
# choose the bootloader solely from the presence of an EFI-looking file.
noncomments = "\n".join(line for line in text.splitlines()
                        if not line.lstrip().startswith("#"))
assert not re.search(r"\b(?:mount|umount|reboot|shutdown|dd|installboot|"
                     r"touch|mkdir|chmod|chown|sysctl\s+-w|service\s+"
                     r"(?:start|restart)|pkgin\s+in)\s", noncomments)
for test in ("sh -n",):
    proc = subprocess.run(["sh", "-n", str(SCRIPT)],
                          text=True, capture_output=True, timeout=5)
    assert proc.returncode == 0, proc.stderr

with tempfile.TemporaryDirectory(prefix="hp-boot-preflight-") as tmp:
    d = Path(tmp)
    tools = d / "bin"
    tools.mkdir()
    mock_uname = tools / "uname"
    mock_uname.write_text(
        '#!/bin/sh\ncase "$1" in -s) echo NetBSD ;;'
        ' -srm) echo "NetBSD 11.0 amd64" ;; *) exit 2 ;; esac\n')
    mock_uname.chmod(0o755)
    mock_sysctl = tools / "sysctl"
    mock_sysctl.write_text(
        '#!/bin/sh\n'
        '[ "$1" = "-n" ] && [ "$2" = machdep.booted_kernel ] || exit 3\n'
        'echo /netbsd-11-shell\n')
    mock_sysctl.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = str(tools) + os.pathsep + environment["PATH"]
    status = subprocess.run(["sh", str(SCRIPT)],
                            text=True, capture_output=True,
                            timeout=12, env=environment)
    assert status.returncode == 0, status.stderr
    rows = status.stdout.splitlines()
    assert "uname=NetBSD 11.0 amd64" in rows
    assert "booted_kernel=/netbsd-11-shell" in rows
    assert "AUDIT_MODE=READ_ONLY" in rows
    assert "AUDIT_INSTALL=NOT_RUN" in rows
    assert "AUDIT_BOOT_TEST=NOT_RUN" in rows
    assert "AUDIT_DONE=READ_ONLY_NO_MUTATIONS" in rows
    assert len(rows) == len(set(k.split("=", 1)[0] for k in rows)), "duplicate keys"
    assert sorted(x.name for x in d.iterdir()) == ["bin"], "audit wrote files"
    # Explicit refusal on non-NetBSD is independent of agent capabilities.
    mock_uname.write_text("#!/bin/sh\necho Linux\n")
    refusal = subprocess.run(["sh", str(SCRIPT)],
                             text=True, capture_output=True,
                             timeout=8, env=environment)
    assert refusal.returncode == 2
    assert "AUDIT_REFUSED=ONLY_NATIVE_NETBSD" in refusal.stdout

    spec = importlib.util.spec_from_file_location("staging", RENDER)
    m = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(m)
    manifest = m.render(d / "staging")
    policy = manifest["boot_loader_policy"]
    assert policy["install_target"] == "UNKNOWN_DO_NOT_INSTALL"
    assert policy["active_firmware_mode"].startswith("UNKNOWN")
    assert policy["bios_cfg"] == "/boot.cfg"
    assert policy["uefi_cfg"].startswith("/EFI/NetBSD/boot.cfg")
    assert any("syslogd requires precreated" in x
               for x in manifest["preconditions"])
    assert any("audit_hp_netbsd11_boot_readonly.sh" in x
               for x in manifest["preconditions"])
    assert (d / "staging/boot.cfg.proposed").is_file()

print("HP_NETBSD_BOOT_BIOS_UEFI_READONLY_PREFLIGHT_PASS")
print("RESULT: native-shell synthetic NetBSD, non-NetBSD refusal, "
      "boot/xdm/logger coverage and no HP install")
