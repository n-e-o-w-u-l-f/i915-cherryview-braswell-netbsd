# F18 incident — HP test-kernel boot menu option 5 panics at vpanic

Date: 2026-10-27. State: OPEN, observed owner-reported boot failure.
The physical HP owner tried boot-menu selection 5 and reported vpanic.
The actual panic string, stacktrace, selected boot image, config source,
and crash dump have NOT been captured in this session. Do not substitute
the last documented root boot.cfg or the source-only F17 test branch
for proof of the selected boot image.

## Evidence before patching

The last documented live configuration on 2026-10-11 referenced only
F77 and F16.2 recovery; the four-mode config published 2026-10-18
was staged and not installed. No documented option 5 identity exists.
F17 has only undergone source and Linux-host model validation, not
HP installation or physical boot. The observed failure must therefore
be treated as an as-yet unidentified separate candidate.

vpanic() prints a panic; it does not disclose the cause by itself.
The meaningful information is the literal panic: MESSAGE and the
first non-panic frame underneath vpanic/panic in the traceback.

An actual pinned NetBSD/src 03d918f6 sys/dev/cons.c inspection
(Git blob f3a2387fbceb9c493517ca69600f669d626750e3)
finds the following specific conditional panic in cnopen():

    if (cn_tab == NULL) return;
    cndev = cn_tab->cn_dev;
    #if NNULLCONS > 0
        ...
    #else
        if (cndev == NODEV) panic("cnopen: no console device");
    #endif

The exact source uses an error=0 / goto out path for the NULL table
case. Thus the cnopen panic requires a non-NULL cn_tab, NODEV physical
console and no compiled nullcons support in that branch. It identifies
a console ownership failure, not automatically a Cherryview DPIO error.

The historical HP F81 outcome and public NetBSD kern/56761 i915
case both involved a cnopen console panic after DRM takeover.
It is a testable hypothesis for option 5, NOT its established cause.

Source: https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/cons.c
Independent i915 precedent: https://mail-index.netbsd.org/netbsd-bugs/2022/03/19/msg074559.html

If the actual trace is vpanic -> panic -> cnopen, investigate genfb,
wsdisplay, intelfb, and console device registration/handoff in the
particular failing kernel. Do NOT hide the fault by suppressing the
panic in generic sys/dev/cons.c. If the first relevant frame shows
uvm_fault/i915 assertions, instead audit that exact caller.

## Implemented read-only F18 tool

New executable-by-sh script:
tools/hp_boot5_vpanic_readonly.sh

Running in a recovered, already working F77 NetBSD shell:

    sh tools/hp_boot5_vpanic_readonly.sh

Without HP access, offline decode of an already exported boot.cfg:

    sh tools/hp_boot5_vpanic_readonly.sh --config /path/to/boot.cfg

This script refuses non-NetBSD for the live mode; does not write, mount,
install, reboot, network, execute config directives or modify settings.
It enumerates the literal 5th menu command, warns if the boot image name
appears AFTER flags, identifies safe regular root-level NetBSD image
hashes (only with safe literal file names), reports booted kernel and
firmware mode, mounted partitions and bounded /var/crash filenames.

Important: an UEFI loader can read EFI/NetBSD/boot.cfg on the actual
EFI System Partition; a root directory with the same path does not
establish which menu was used. The tool deliberately labels both root
locations non-authoritative until ESP loader provenance is established.
A missing crash dump does not disprove a pre-userland kernel panic.

NetBSD boot syntax: boot netbsd.test -v (correct). But if an entry uses
boot -v netbsd.test, boot(8) ignores the filename after the options and
may load default netbsd instead.
Reference: https://man.netbsd.org/NetBSD-11.0/boot.8

If the previous failed kernel is STILL stopped at a DDB db{0}> prompt,
obtain the actual panic and stack with read-only commands:

    show panic
    trace

Photograph the visible panic text and frames. Do not use sync, reboot
or continue just for evidence collection. Do not start another failed
option-5 test from a successfully restored F77 session.

Reference: https://man.netbsd.org/ddb.4

## Verification and explicit limitations

Real Legion sh -n and standalone Python fixture regression:
explicit named kernel, wrong filename/flags order, module+boot,
four-entry menu, blank menu label, default boot, symlink refusal,
non-NetBSD refusal. All PASS, no fixture modifications observed.
Runner: tests/test_hp_boot5_vpanic_readonly.py.

NO live HP readback; no actual panic string captured; no matched
vpanic stack; no verified image identity for option 5; no native
NetBSD kernel compile or HP device-level fix has been made.

F77 safe boot, firmware, installed kernels, /netbsd and actual boot
configuration remain untouched. Root-cause repair must follow the
captured panic and image identity, not guesses or another model suite.
