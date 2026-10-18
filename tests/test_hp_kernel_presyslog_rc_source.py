#!/usr/bin/env python3
"""Test the proposed NetBSD pre-syslog logfile creator in disposable fixture."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
modpath = ROOT / "tools/render_hp_netbsd11_four_boot_modes.py"
spec = importlib.util.spec_from_file_location("hp_mode", modpath)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

with tempfile.TemporaryDirectory(prefix="hp-kernel-presyslog-") as td:
    stage = Path(td) / "stage"
    m.render(stage)
    src = stage / "etc/rc.d/hpbootlogprep.proposed"
    conf = stage / "etc/rc.conf.d/hpbootlogprep.proposed"
    assert conf.read_text() == "hpbootlogprep=YES\n"
    text = src.read_text()
    for line in ("# PROVIDE: hpbootlogprep",
                 "# REQUIRE: mountcritlocal",
                 "# BEFORE: newsyslog syslogd",
                 'load_rc_config "$name"',
                 'run_rc_command "$1"',
                 "set -C", "umask 077",
                 "/var/log/hp-kernel-boot.log"):
        assert line in text, line
    p = subprocess.run(["sh", "-n", str(src)],capture_output=True,text=True)
    assert p.returncode == 0, p.stderr
    # Extract the unmodified POSIX file-creator body; never invoke rc startup
    # or touch a real /var/log path during a portable source-only test.
    before = "hpbootlogprep_file()\n{\n"
    end = "\nhpbootlogprep_start()"
    assert text.count(before) == 1 and text.count(end) == 1
    body = before + text.split(before, 1)[1].split(end, 1)[0]
    def call(path):
        return subprocess.run(["sh", "-c",
            body + "\nhpbootlogprep_file \"$1\"\n", "_", str(path)],
            capture_output=True,text=True,timeout=6)

    target = Path(td) / "kernel.log"
    result = call(target)
    assert result.returncode == 0, result.stderr
    assert target.is_file()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    target.write_text("do not truncate prior boot log\n")
    result = call(target)
    assert result.returncode == 0
    assert target.read_text() == "do not truncate prior boot log\n"
    symlink = Path(td) / "symlink.log"
    symlink.symlink_to(target)
    assert call(symlink).returncode != 0
    assert target.read_text() == "do not truncate prior boot log\n"
    directory = Path(td) / "directory"
    directory.mkdir()
    assert call(directory).returncode != 0
    assert not (Path(td) / "extra").exists()

print("HP_NETBSD_PRESYSLOG_NOCLOBBER_MODE_AND_LINK_GATES_PASS")
print("SOURCE_ONLY: existing log preserved; fresh mode0600; link and dir rejected")
