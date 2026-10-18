#!/bin/sh
# HP NetBSD-11 BIOS/UEFI + recovery/menu/login/logging READ-ONLY inventory.
# Does not install anything, create logs, change services, mount ESP or reboot.
# Run only on an independently authorized HP owner shell.
set -u
export LC_ALL=C

say() { printf '%s\n' "$1"; }
bool_file() {
  if [ -f "$2" ] && [ ! -L "$2" ]; then say "$1=PRESENT";
  else say "$1=ABSENT_OR_SYMLINK"; fi
}
bool_exec() {
  if [ -x "$2" ] && [ ! -L "$2" ]; then say "$1=EXECUTABLE";
  else say "$1=NOT_VERIFIED_EXECUTABLE"; fi
}
kernel_digest() {
  name=$1
  path=$2
  if [ ! -f "$path" ] || [ -L "$path" ]; then
    say "$name=ABSENT_OR_SYMLINK"
  elif command -v sha256 >/dev/null 2>&1; then
    digest=$(sha256 -q "$path" 2>/dev/null) || digest=HASH_ERROR
    say "$name=$digest"
  else
    say "$name=SHA256_NOT_AVAILABLE"
  fi
}
if [ "$(uname -s 2>/dev/null)" != NetBSD ]; then
  say "AUDIT_REFUSED=ONLY_NATIVE_NETBSD"
  exit 2
fi
say "AUDIT_MODE=READ_ONLY"
say "AUDIT_KERNEL_BUILD=NOT_RUN"
say "AUDIT_INSTALL=NOT_RUN"
say "AUDIT_BOOT_TEST=NOT_RUN"
# The historical HP UEFI audit observed machdep.bootmethod=UEFI,
# but current mode must be read again; firmware mode is not an install path.
if bootmethod=$(sysctl -n machdep.bootmethod 2>/dev/null); then
  case "$bootmethod" in
    UEFI|BIOS) say "AUDIT_BOOTLOADER=$bootmethod" ;;
    *) say "AUDIT_BOOTLOADER=UNKNOWN_OTHER" ;;
  esac
else
  say "AUDIT_BOOTLOADER=UNKNOWN_REQUIRE_PHYSICAL_BIOS_UEFI_CHECK"
fi
say "uname=$(uname -srm 2>/dev/null || printf UNKNOWN)"
if kernel=$(sysctl -n machdep.booted_kernel 2>/dev/null); then
  say "booted_kernel=$kernel"
else
  say "booted_kernel=UNKNOWN"
fi
kernel_digest "kernel_netbsd_sha256" /netbsd
for path in /netbsd-11-xfce4 /netbsd-11-kde /netbsd-11-shell /netbsd-11-i915-rtl-diag; do
  kernel_digest "kernel_${path##*/}_sha256" "$path"
done
# Never infer F77 file location from the last documented F77 boot.
say "f77_recovery_sha256=UNKNOWN_REQUIRE_ACTUAL_PATH"
bool_file "bios_boot_cfg" /boot.cfg
# The UEFI loader reads /EFI/NetBSD/boot.cfg *inside the actual ESP*.
# Never confuse the NetBSD root directory with the FAT EFI partition.
# The actual mounted ESP and loader read path must be identified separately.
say "uefi_esp_boot_cfg=UNKNOWN_REQUIRES_ESP_MOUNTPOINT_READBACK"
# A mounted EFI system partition may be elsewhere; presence is NOT proof of use.
say "authoritative_boot_cfg=UNKNOWN_REQUIRE_LOADER_AND_ESP_CHECK"
bool_file "rc_conf" /etc/rc.conf
bool_file "rc_xdm_override" /etc/rc.conf.d/xdm
bool_file "syslog_conf" /etc/syslog.conf
bool_file "rc_d_xdm" /etc/rc.d/xdm
bool_file "rc_d_dmesg" /etc/rc.d/dmesg
bool_file "rc_d_savecore" /etc/rc.d/savecore
bool_file "kernel_syslog_file" /var/log/hp-kernel-boot.log
bool_file "boot_dmesg_file" /var/run/dmesg.boot
bool_file "xdm_config" /etc/X11/xdm/xdm-config
bool_file "xdm_xsession" /etc/X11/xdm/Xsession
bool_exec "x_server" /usr/X11R7/bin/X
bool_exec "xfce4_session" /usr/pkg/bin/xfce4-session
bool_exec "startxfce4" /usr/pkg/bin/startxfce4
bool_exec "kde_plasma_x11" /usr/pkg/bin/startplasma-x11
bool_exec "kde_startkde" /usr/pkg/bin/startkde
if [ -f /etc/syslog.conf ] && grep -Eq '^[[:space:]]*kern\.\*[[:space:]]+/var/log/hp-kernel-boot\.log([[:space:]]|$)' /etc/syslog.conf; then
  say "kernel_syslog_route=CONFIGURED"
else
  say "kernel_syslog_route=NOT_VERIFIED"
fi
say "AUDIT_DONE=READ_ONLY_NO_MUTATIONS"
