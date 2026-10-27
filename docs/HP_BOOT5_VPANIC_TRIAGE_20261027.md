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


## 2026-10-27 source-based console ownership boundary and F18 patch

New [F18 guarded console-handoff source patch](../patches/candidates/netbsd11-f18-i915-console-handoff-trace-20261027.patch)
instruments the actual **NetBSD 11** console owners:

1. `[I915-CN IFB1]` — intelfb delayed attach task enters DRM framebuffer setup.
2. `[I915-CN DRM1]` — drmfb decides console ownership and surface dimensions.
3. `[I915-CN GFB1]` — genfb begins screen preparation, *before* its
   explicit don't-print/clear interval.
4. `[I915-CN WSD]` — wsdisplay installs the real console `cn_dev` identifier.
5. `[I915-CN GFB2]` — genfb receives the `config_found` child result.
   `wsdisplay=NONE` means no child was found.
6. `[I915-CN DRM2]` — generic framebuffer attachment returns to drmfb.
7. `[I915-CN IFB2]` — i915 intelfb attachment returns.

**Specific source-proven hole:** pinned `genfb.c` installs
`wsdisplay_cons` in `wsdisplay_cnattach` when `console` is true,
but leaves its `cn_dev` initialized to `NODEV` until
`wsdisplay_emul_attach` executes. The following
`config_found(..., iattr="wsemuldisplaydev")` has its result
discarded in uninstrumented `genfb_attach` and the function
unconditionally returns success. When no matching child is attached,
the console can be left without a real device. That is a source-backed
failure mechanism, **not evidence that option 5 actually hit it**.
Source-proven alternatives include an earlier `wsdisplay_cnattach`
assertion when another console is already fully initialized and
multiple other unrelated `vpanic` callers.

The patch modifies `genfb.c`, `wsdisplay.c`, `drmfb.c` and
`intelfb.c`, with *seven* marker sites behind a single
`HP_I915_CONSOLE_TRACE` compile-time diagnostic macro.
No macro is enabled by default; the normal C source is unchanged
after removal of the guarded blocks. It does **not** suppress
`cnopen`, change console selection, retry failed display init,
disable checks, override `/boot.cfg` or install another image.
Do not infer that the patch alone makes a bootable kernel.

The standalone source check
`tests/test_f18_console_handoff_trace_source.py` PASSed on Legion with
all four original NetBSD Git blobs verified. A second, stricter run
used an actual sparse NetBSD/src Git checkout on the exact commit
`03d918f6d0e81fa05b8f1160eca0628ad39988a6` and also PASSed
in `--netbsd-tree` mode. It executed real
`git apply --whitespace=error --check` and `git apply` in an isolated
temporary tree, then removed only F18 `#ifdef` regions and asserted
byte-for-byte identity against all four original files, all seven
unique marker placements and source execution order. The initial
incomplete final newline in the candidate diff was found by the
*real git apply parser*, fixed, and the same test then exited 0.
Result:
`F18_PINNED_4_NETBSD_FILES_7_TRACE_MARKERS_NO_BEHAVIOR_DIFF_PASS`.

**NOT_RUN:** native NetBSD compiler with this macro enabled, linked
diagnostic kernel, source-level instrumentation on the HP, panic
capture and observed symptom recovery. No further experimental boot
is authorized by this patch. Wait for the full original option-5
panic text and image identity before deciding whether the first
remedial patch should target console registration or something else.
