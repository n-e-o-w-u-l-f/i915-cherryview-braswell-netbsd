#!/usr/bin/env python3
"""Test exact NetBSD-11 boot mode staging, without writing HP system paths."""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "four_modes", ROOT / "tools/render_hp_netbsd11_four_boot_modes.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def check(condition, message):
    if not condition:
        raise AssertionError(message)

with tempfile.TemporaryDirectory(prefix="hp-four-modes-fixture-") as td:
    root = Path(td)
    stage = root / "proposal"
    manifest = MODULE.render(stage)
    check(manifest["status"] == "SOURCE_ONLY_NOT_INSTALLED", "status")
    check(manifest["default_menu_option"] == 3, "shell is safe default")
    check(stage.exists(), "stage absent")
    boot = (stage / "boot.cfg.proposed").read_text()
    menu = [row for row in boot.splitlines() if row.startswith("menu=")]
    check(len(menu) == 4, "not exactly four boot modes")
    for position, filename in enumerate(MODULE.KERNELS):
        check(menu[position].endswith(":boot " + filename), "kernel mapping")
    check("default=3" in boot and "timeout=15" in boot, "default/timeout")
    check("boot -s" not in boot and "boot -1" not in boot and
          "boot -2" not in boot and "boot -3" not in boot,
          "dangerous boot flags or single user")
    check("/netbsd\n" not in boot, "must use distinct named kernel images")
    rc = stage / "etc/rc.conf.d/xdm.proposed"
    xsession = stage / "usr/local/libexec/hp-menu-xsession.proposed"
    for source in (rc, xsession):
        probe = subprocess.run(["sh", "-n", str(source)],
                               capture_output=True, text=True)
        check(probe.returncode == 0, "shell syntax failed: " + str(source))
    raw = rc.read_text()
    to_mock = "$(/sbin/sysctl -n machdep.booted_kernel 2>/dev/null)"
    check(raw.count(to_mock) == 1, "unexpected sysctl shape")
    for kernel, expected in (
        ("netbsd-11-xfce4", "YES"),
        ("netbsd-11-kde", "YES"),
        ("netbsd-11-shell", "NO"),
        ("netbsd-11-i915-rtl-diag", "NO"),
        ("netbsd-F77-recovery", "EXISTING")):
        mock = raw.replace(to_mock, '$(printf "%s" "' + kernel + '")')
        test = root / "rc-mock.sh"
        test.write_text(mock)
        probe = subprocess.run(
            ["sh", "-c", 'xdm=EXISTING; . "$1"; printf "%s" "$xdm"', "_",
             str(test)], capture_output=True, text=True)
        check(probe.returncode == 0 and probe.stdout == expected,
              "xdm routing " + kernel + ": " + repr(probe.stdout))
    check("xfce4-session" in xsession.read_text(), "XFCE startup absent")
    check("startplasma-x11" in xsession.read_text(), "KDE startup absent")
    check("Xsession.pre-hp-modes" in xsession.read_text(), "original fallback")
    check((stage / "etc/syslog.conf.kernel.proposed").read_text() ==
          "kern.*\t/var/log/hp-kernel-boot.log\n", "syslog facility")
    check("MSGBUFSIZE=262144" in
          (stage / "kernel-logging-options.proposed").read_text(), "buffer")
    try:
        MODULE.render(stage)
    except ValueError:
        pass
    else:
        raise AssertionError("refused existing stage overwrite was accepted")
    check(not (root / "boot.cfg").exists(), "wrote outside stage")
    check(json.loads((stage / "stage-manifest.json").read_text())["kernel_names"]
          == list(MODULE.KERNELS), "manifest kernel identity")

print("HP_NETBSD11_FOUR_MODE_STAGING_TEST_PASS")
print("RESULT: 4 menu entries + 5 xdm paths + shell -n + no overwrite")
print("LIMIT: source-only Linux fixture; no HP install, kernel build or boot")
