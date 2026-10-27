#!/usr/bin/env python3
"""POSIX-sh menu-5 panic evidence: real config parsing, no boot mutation."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/hp_boot5_vpanic_readonly.sh"

subprocess.run(["sh", "-n", str(SCRIPT)], check=True)

with tempfile.TemporaryDirectory(prefix="netbsd-boot5-source-check-") as temporary:
    root = Path(temporary)
    cfg = root / "boot.cfg"
    prefix = "".join(
        f"menu=Recovery {n}:boot netbsd.f77\n" for n in range(1, 5)
    )
    fixtures = [
        ("named_kernel", prefix +
         "menu=F18 test:boot netbsd.test5 -vx\ndefault=1\ntimeout=10\n",
         ["SUPPLIED_MENUS_TOTAL=5",
          "SUPPLIED_MENU5_TITLE=F18 test",
          "SUPPLIED_MENU5_BOOT_IMAGE=netbsd.test5",
          "SUPPLIED_DEFAULT=1", "SUPPLIED_TIMEOUT=10"]),
        ("boot_flags_before_name", prefix +
         "menu=Wrong syntax:boot -v netbsd.test5\n",
         ["SUPPLIED_MENU5_BOOT_IMAGE=netbsd_DEFAULT",
          "SUPPLIED_MENU5_WARNING=FILENAME_AFTER_FLAGS_IGNORED"]),
        ("module_and_disk_specifier", prefix +
         "menu=Diag:load i915drmkms;boot hd0a:netbsd-test5 -v\n",
         ["SUPPLIED_MENU5_BOOT_IMAGE=hd0a:netbsd-test5"]),
        ("four_entries_only", prefix,
         ["SUPPLIED_MENUS_TOTAL=4", "SUPPLIED_MENU5=NOT_PRESENT"]),
        ("empty_label", prefix + "menu=:boot netbsd-fifth\n",
         ["SUPPLIED_MENU5_TITLE=", "SUPPLIED_MENU5_BOOT_IMAGE=netbsd-fifth"]),
        ("default_loader_fallback", prefix + "menu=Default:boot -s\n",
         ["SUPPLIED_MENU5_BOOT_IMAGE=netbsd_DEFAULT"]),
    ]
    for name, sample, required in fixtures:
        cfg.write_text(sample)
        before = cfg.read_bytes()
        result = subprocess.run(["sh", str(SCRIPT), "--config", str(cfg)],
                                capture_output=True, text=True, timeout=12)
        assert result.returncode == 0, (name, result.stderr)
        rows = result.stdout.splitlines()
        for expected in required:
            assert expected in rows, (name, expected, result.stdout)
        assert rows[-1] == "F18_DONE=READ_ONLY_NO_MUTATIONS"
        assert cfg.read_bytes() == before, "offline parser changed boot config"
        print("F18_MENU5_CASE_PASS", name)

    link = root / "linked.cfg"
    link.symlink_to(cfg.name)
    result = subprocess.run(["sh", str(SCRIPT), "--config", str(link)],
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == 0
    assert "SUPPLIED_CONFIG=NOT_READABLE_OR_SYMLINK" in result.stdout

    # A default invocation on non-NetBSD must explicitly refuse without
    # probing/mutating the host. Isolate uname through a disposable PATH mock.
    mockdir = root / "bin"
    mockdir.mkdir()
    uname = mockdir / "uname"
    uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n")
    uname.chmod(0o755)
    environ = dict(os.environ, PATH=str(mockdir) + ":" + os.environ["PATH"])
    result = subprocess.run(["sh", str(SCRIPT)], env=environ,
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == 2
    assert "F18_REFUSED=NOT_NETBSD" in result.stdout
    assert "F18_DONE=READ_ONLY_NO_MUTATIONS" not in result.stdout

text = SCRIPT.read_text()
for forbidden in ("mount -", "umount ", "reboot ", "shutdown ", "installboot ",
                  "sysctl -w ", "chmod ", "rm -", "mv ", "dd if="):
    assert forbidden not in "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ), f"unsafe operation in read-only script: {forbidden}"

print("F18_BOOT5_SIX_MENU_FIXTURES_SYMLINK_NON_NETBSD_READONLY_PASS")
