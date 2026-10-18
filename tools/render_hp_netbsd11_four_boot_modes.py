#!/usr/bin/env python3
"""Generate, never install, the HP NetBSD-11 four-mode boot proposal."""
import argparse
import json
from pathlib import Path

KERNELS = ("netbsd-11-xfce4", "netbsd-11-kde", "netbsd-11-shell",
           "netbsd-11-i915-rtl-diag")

BOOT = """# Proposal only. Preserve and hash the existing /netbsd and F77 first.
banner=HP NetBSD 11 - select desktop or diagnostic kernel
format=n
timeout=15
default=3
menu=NetBSD v11.0 with XFCE4:boot netbsd-11-xfce4
menu=NetBSD v11.0 with KDE:boot netbsd-11-kde
menu=NetBSD v11.0 shell only:boot netbsd-11-shell
menu=NetBSD v11.0 logging i915+RTL8723BE:boot netbsd-11-i915-rtl-diag
"""

XDM_RC = """# Sourced by NetBSD rc.subr after rc.conf, for service xdm only.
_hp_kernel="$(/sbin/sysctl -n machdep.booted_kernel 2>/dev/null)" || _hp_kernel=""
case "$(/usr/bin/basename "$_hp_kernel")" in
netbsd-11-xfce4|netbsd-11-kde) xdm=YES ;;
netbsd-11-shell|netbsd-11-i915-rtl-diag) xdm=NO ;;
*) : ;; # untouched fallback kernel: retain pre-existing xdm policy
esac
unset _hp_kernel
"""

XSESSION = """#!/bin/sh
# Requires a backed-up original /etc/X11/xdm/Xsession and a narrow
# xdm-config DisplayManager*session override verified on the HP.
_hp_kernel="$(/sbin/sysctl -n machdep.booted_kernel 2>/dev/null)" || _hp_kernel=""
case "$(/usr/bin/basename "$_hp_kernel")" in
netbsd-11-xfce4)
    if [ -x /usr/pkg/bin/xfce4-session ]; then exec /usr/pkg/bin/xfce4-session; fi
    echo "XFCE4 session absent" >&2; exit 127 ;;
netbsd-11-kde)
    if [ -x /usr/pkg/bin/startplasma-x11 ]; then exec /usr/pkg/bin/startplasma-x11; fi
    if [ -x /usr/pkg/bin/startkde ]; then exec /usr/pkg/bin/startkde; fi
    echo "KDE X11 session absent" >&2; exit 127 ;;
esac
if [ -x /etc/X11/xdm/Xsession.pre-hp-modes ]; then
    exec /etc/X11/xdm/Xsession.pre-hp-modes "$@"
fi
echo "Original Xsession missing" >&2; exit 127
"""

SYSLOG = "kern.*\t/var/log/hp-kernel-boot.log\n"
# New, opt-in rc.d service. /var must exist before writing the log.
# A normal userspace syslogd never guarantees pre-mount freeze persistence.
BOOTLOG_RC = """#!/bin/sh
# PROVIDE: hpbootlogprep
# REQUIRE: mountcritlocal
# BEFORE: newsyslog syslogd

$_rc_subr_loaded . /etc/rc.subr

name="hpbootlogprep"
rcvar="$name"
start_cmd="hpbootlogprep_start"
stop_cmd=":"

hpbootlogprep_file()
{
    target=$1
    if [ -L "$target" ]; then
        return 1
    fi
    if [ -e "$target" ]; then
        [ -f "$target" ] || return 1
        return 0
    fi
    # O_EXCL-style shell noclobber avoids overwriting a racing file.
    ( umask 077; set -C; : > "$target" ) || return 1
    [ -f "$target" ] && [ ! -L "$target" ]
}

hpbootlogprep_start()
{
    [ -d /var/log ] || return 1
    hpbootlogprep_file /var/log/hp-kernel-boot.log
}

load_rc_config "$name"
run_rc_command "$1"
"""

BOOTLOG_RCCONF = "hpbootlogprep=YES\n"
DEBUG = """# Diagnostic kernel options: verify against actual NetBSD 11 source.
options DDB
options DDB_TEE_MSGBUF=1
options MSGBUFSIZE=262144
# Isolated driver printf tags: G01 PCI, G02 MMIO, G03 GTT/GEM,
# G04 VBT/eDP, G05 panel power, G06 AUX link, G07 DPIO/PLL,
# G08 pipe/fb, G09 wsdisplay. A userland log cannot survive a pre-rc hang.
"""

def render(stage):
    stage = Path(stage)
    if not stage.is_absolute() or stage == Path("/") or stage.exists():
        raise ValueError("Require a NEW absolute, non-root stage directory")
    files = {
        "boot.cfg.proposed": BOOT,
        "etc/rc.conf.d/xdm.proposed": XDM_RC,
        "usr/local/libexec/hp-menu-xsession.proposed": XSESSION,
        "etc/syslog.conf.kernel.proposed": SYSLOG,
        "etc/rc.d/hpbootlogprep.proposed": BOOTLOG_RC,
        "etc/rc.conf.d/hpbootlogprep.proposed": BOOTLOG_RCCONF,
        "kernel-logging-options.proposed": DEBUG,
    }
    stage.mkdir(mode=0o700)
    for name, content in files.items():
        dest = stage / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    manifest = {
        "status": "SOURCE_ONLY_NOT_INSTALLED",
        "kernel_names": KERNELS,
        "default_menu_option": 3,
        "boot_loader_policy": {
            "active_firmware_mode": "UNKNOWN_REQUIRE_LIVE_HP_PROOF",
            "last_documented_mode": "UEFI in docs/UEFI-BOOT-CHAIN.md; historical, recheck machdep.bootmethod",
            "bios_cfg": "/boot.cfg",
            "uefi_cfg": "/EFI/NetBSD/boot.cfg on the EFI system partition",
            "install_target": "UNKNOWN_DO_NOT_INSTALL",
            "reason": "NetBSD x86/boot(8) uses distinct BIOS vs UEFI paths",
        },
        "preconditions": [
            "Run native read-only tools/audit_hp_netbsd11_boot_readonly.sh",
            "Identify the active BIOS/UEFI loader, boot filesystem and mounted ESP before choosing boot.cfg target",
            "live HP NetBSD read-only identity and current boot.cfg check",
            "all three standard kernel copies byte-identical with verified /netbsd",
            "preserve byte-identical F77 image and manual boot-loader recovery",
            "XFCE4 and KDE programs, X server and xdm verified",
            "back up existing rc.conf.d/xdm, Xsession, xdm-config and syslog.conf",
            "verify current rc.d/xdm and xdm security/session policy before choosing XDM wrapper",
            "syslogd requires precreated /var/log/hp-kernel-boot.log; prove kernel facility route and rotation",
            "enable hpbootlogprep=YES only after verifying pinned NetBSD rcorder REQUIRE mountcritlocal BEFORE newsyslog/syslogd",
            "no live file or rc.d installation until actual HP filesystem and syslogd config readback",
            "confirm dumpdev/savecore and actual independent recovery, not just dmesg.boot",
            "separate genuine i915+RTL native ELF for the diagnostic menu item",
            "only then atomic install and readback, no unattended diagnostic boot",
        ],
        "written_files": list(files),
    }
    (stage / "stage-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--stage-dir", required=True)
    args = p.parse_args()
    print(json.dumps(render(args.stage_dir)))
