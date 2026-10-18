# HP NetBSD 11 four-mode boot proposal — isolated stage

State: **source-only, not installed, not booted**. User intent: (1) NetBSD
v11.0 XFCE4, (2) KDE, (3) multi-user shell-only, (4) separately instrumented
i915+RTL8723BE diagnostic kernel with persistent boot logs.

## Implemented staging artifacts

Run `python3 -B tools/render_hp_netbsd11_four_boot_modes.py
--stage-dir /absolute/NEW/private/stage-directory`. This writes only
a new directory; it refuses to overwrite an existing directory.
`tests/test_hp_netbsd11_four_boot_modes.py` exercises exact menu order,
`default=3`, multi-user rather than single-user, NetBSD shell syntax,
5 per-kernel xdm override cases, logging selector and no-overwrite.

The proposed `/boot.cfg` contains exactly four menu choices:

```text
menu=NetBSD v11.0 with XFCE4:boot netbsd-11-xfce4
menu=NetBSD v11.0 with KDE:boot netbsd-11-kde
menu=NetBSD v11.0 shell only:boot netbsd-11-shell
menu=NetBSD v11.0 logging i915+RTL8723BE:boot netbsd-11-i915-rtl-diag
default=3
timeout=15
```

The names `netbsd-11-xfce4`, `netbsd-11-kde` and
`netbsd-11-shell` designate **three byte-identical copies of ONE
independently verified working standard NetBSD kernel**, not three new
kernels. The HP has NOT been read to establish such a standard image.
Preserve the previously verified F77/genfb image and its exact SHA under
a known selectable emergency name, and leave `/netbsd` untouched
until full recovery boot-readback and actual standard identity are proved.
If the original F77 is the only demonstrated working kernel, it remains
the temporary source of the three standard-mode files; renaming it a
different release or silently replacing it is not allowed.

NetBSD's `machdep.booted_kernel` (amd64) identifies which of these
copies booted. Stage `/etc/rc.conf.d/xdm` uses that value to set
`xdm=YES` for XFCE/KDE and `xdm=NO` for shell and diagnostic; unknown
or restored F77 kernels retain the owner's original xdm policy. A
**separate** staged xdm session wrapper chooses
`/usr/pkg/bin/xfce4-session` or `/usr/pkg/bin/startplasma-x11`
(with a legacy `startkde` fallback). These paths MUST be independently
verified against installed packages. Configure the actual xdm
`DisplayManager*session` to point to the new wrapper only after
backing up the old xdm-config and original Xsession; the wrapper chains
that original for any legacy kernel. The script does NOT silently
replace existing per-user `.xsession` or alter passwords/login accounts.

### Verified historical HP UEFI state and read-only probe

The existing, earlier `docs/UEFI-BOOT-CHAIN.md` records a **real HP**
`machdep.bootmethod=UEFI` with a 128-MiB FAT16 EFI System Partition
(GPT partition 1) containing `EFI/BOOT/BOOTX64.EFI`. It also records
the verified NetBSD `/usr/mdec/bootx64.efi` loader digest. These are
historical direct-host observations, not today's active boot state.
NetBSD's x86/boot(8) says an EFI loader reads configuration from
`/EFI/NetBSD/boot.cfg` **on its EFI System Partition**, not necessarily
from the NetBSD root filesystem's `/boot.cfg`. The named kernel ELF
images remain on the NetBSD root filesystem, NOT on the FAT ESP.

**Do not assume the NetBSD root `/EFI/NetBSD` is the mounted ESP.**
Before changing any menu, inspect actual bootmethod, root/ESP device
and mounts, the loader-selected configuration, and preserve both the
preexisting standard kernel and F77 rescue image/hashes.

`tools/audit_hp_netbsd11_boot_readonly.sh` is a POSIX shell-only, no-
change probe; it refuses execution off NetBSD and reports the actual
`machdep.bootmethod`, running kernel identity, standard kernel SHA256,
candidate images, xdm/XFCE/KDE executables, syslog route/file and
savecore/dmesg prerequisites. If the ESP is not independently verified
it reports `uefi_esp_boot_cfg=UNKNOWN` rather than checking the wrong
root path and misreporting an absent firmware config.

The new source-only regression
`tests/test_hp_netbsd11_boot_audit_source.py` passes in a disposable
Legion copy against a synthetic NetBSD `uname`/`sysctl` fixture,
checks no-overwrite and non-NetBSD refusal; it is **NOT** proof that
the real HP audit was run.

### Real HP pre-install checklist

1. Actual authoritative **direct** controller-to-HP executor first
   (Tailscale/native authorized command agent), else independently
   permitted alternate host + native SSH; no quota/tool denial evasion.
2. Read uname/OS/actual selected kernel `sysctl machdep.booted_kernel`,
   original `/boot.cfg`, existing `/netbsd` and F77 names/sha256,
   root filesystem boot identity, disk space and writes/permissions.
3. Verify X server, xdm, tty ownership, XFCE4 session executable,
   KDE/Plasma X11 executable and user's existing login/session scripts.
   If either desktop is absent, do not mark that menu mode TESTREADY.
4. Read `/etc/rc.conf`, `/etc/rc.conf.d/xdm`,
   `/etc/X11/xdm/xdm-config`, existing original `Xsession`,
   `/etc/syslog.conf`, syslogd state, `/var/log` and
   `/var/crash`; preserve entire original configuration byte-for-byte.
5. After a separate legitimate file mutation authorization, stage
   kernel copies and all config replacements into NEW paths; compare
   hashes and parse source. Make narrow backups, never replace
   `/netbsd` or the F77 image. Use atomic per-file changes and read
   the complete files back, including unrelated boot menu entries.
6. Verify the chosen **safe default** via unattended menu timeout
   *only after* recovery transport is proven; keep diagnostic option 4
   nondefault. No blind reboot to test xdm session routing.
7. On any mismatch use the pre-existing verified boot menu/kernel
   rather than discovering the recovery path by repeated blackscreens.

### NetBSD pre-syslog logfile creation, isolated staging

NetBSD `syslogd` does **not** create a missing output file.
The renderer now includes **two additional staged-only artifacts**:

- `etc/rc.d/hpbootlogprep.proposed`: opt-in NetBSD
  `rc.subr` service, `PROVIDE: hpbootlogprep`,
  `REQUIRE: mountcritlocal`, `BEFORE: newsyslog syslogd`.
  It creates the file `/var/log/hp-kernel-boot.log` with
  `umask 077` and shell `noclobber` only when missing. Existing
  regular files are left intact; symlink and directory targets fail.
- `etc/rc.conf.d/hpbootlogprep.proposed`: sets
  `hpbootlogprep=YES`, to be activated **only after** verifying the
  original HP rc.d/service layout, file mode, logrotate ownership
  and source/configuration backups.

The proposed `kern.* /var/log/hp-kernel-boot.log` syslog selector
remains staged. The rc.d file, rc.conf.d setting, syslog route,
filesystem mode and service order must be verified together on a
legitimate HP owner session before any **atomic** deployment.

The source test `tests/test_hp_kernel_presyslog_rc_source.py` extracts
the precise shell creation function into a disposable fixture: new
file mode 0600 PASS, preexisting content unchanged PASS, symlink and
directory refusal PASS, `sh -n` PASS. On Legion exact i915 commit
`ab774429472e481e78531786b009467b65773cf9`, all three
boot/audit/pre-syslog Python source tests EXIT 0.

**Important timing limit:** neither this service nor syslogd can
persist a freeze *before* /var is mounted and userland begins.
The kernel msgbuf, DDB and configured dumps remain independent
diagnostic layers, with physically verifiable early console still
needed for a non-dumpable hard lockup.

### Diagnostic logging and shared i915+RTL build

Kernel KMS init occurs BEFORE userspace and filesystem logging. The
proposed `kern.* /var/log/hp-kernel-boot.log` syslog selector catches
kernel messages **only after syslogd starts and the file is correctly
created**. Keep NetBSD `dmesg=YES` for `/var/run/dmesg.boot` on
successful multi-user startup. Verify `savecore=YES` and the actual
dump device/free space before claiming panic persistence. Increase
`MSGBUFSIZE=262144` and enable `DDB_TEE_MSGBUF=1` only in an isolated
NetBSD-verified diagnostic kernel config. Neither gives guaranteed
on-disk tracing of a complete pre-userland lockup. G01–G09 display
markers must be inserted at genuinely owning NetBSD i915 attach/
display phase transitions, not invented in generic userland.

The **RTL project owns the combined kernel build**, with currently
existing `tools/build_hp_combined_i915_rtl_candidate.sh` and
`tools/configure_hp_combined_i915_rtl.py`. Their full-release guard
currently requires six real KMS/native/recovery PASS facts plus
complete i915 owner source closure. No such i915 release JSON exists
on the inspected working branch; the 323 Linux units have only a
structural file/path inventory, **300 semantically unreviewed**. This
creates an intentional compile-vs-KMS dependency cycle and means the
production combined builder MUST NOT be rerun with false verification
flags. A future separately reviewed **diagnostic build-only** gate
may permit native compile/link diagnostics without a fake full release,
but never installation/boot or relaxation of actual source/host safety.
RTL currently selects 50 native units, but none is represented as
physically WLAN-accepted.

The HP's Tailscale peer is online, yet the current ChatGPT session
has no callable Tailscale execution tool; the direct RDC HP agent
responds to ping but its account reported 0% remote-command quota.
Legion-to-HP public-key SSH attempt failed authentication. Accordingly
**no HP commands, live boot edits, builds, installs or boots were made**.

Primary NetBSD references:
- https://man.netbsd.org/NetBSD-11.0/boot.cfg.5
- https://man.netbsd.org/rc.subr.8
- https://www.netbsd.org/docs/guide/en/chap-x.html
- https://www.netbsd.org/docs/guide/en/chap-rc.html
- https://man.netbsd.org/syslog.conf.5
- https://man.netbsd.org/ddb.4
