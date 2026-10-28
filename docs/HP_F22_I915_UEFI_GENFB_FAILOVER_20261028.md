# F22: opt-in native NetBSD i915 probe-error UEFI console failover

Date: 2026-10-28
Status: **EXPERIMENTAL FUNCTIONAL C PATCH, NOT BOOT-SAFE**.

F22 is a concrete candidate to close the previously documented F19/F20/F21
console ownership gap. It is not proof that HP boot menu option 5 failed at
this error site: the actual panic line, non-vpanic stack, kernel image and
SHA-256 for menu option 5 are STILL UNKNOWN.

## Precisely which failure is covered?

NetBSD/src pinned HEAD:
03d918f6d0e81fa05b8f1160eca0628ad39988a6.

Native unmodified original Git blobs:
- sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c:
  9798385b02f247c08db9b16624d5ddc9d11a8ca5
- sys/external/bsd/drm2/i915drm/files.i915drmkms:
  23d352b64eb1799caf3e9b2770f78795accc8439

At x86 consinit, UEFI GOP can provide a physical framebuffer, leading
to wsdisplay_preattach. That establishes a usable early text-output
console but not yet its /dev/console device number: wsdisplay_cons.cn_dev
starts as NODEV, and wsdisplay_emul_attach sets the real device number.

PCI autoconfiguration chooses i915drmkms at match rank 6 over genfb_pci
at match rank at most 5. Consequently the PCI genfb path does not get
an independent chance to complete the wsdisplay console. i915 then
defers its driver probe until mountroot. If i915_driver_probe fails,
no intelfb/drmfb/genfb callback has been called and F19's later
drmfb preflight cannot help.

x86 device_pci_register DOES copy the existing firmware framebuffer
width, height, depth, linebytes, physical address, virtual address,
is_console and clear-screen flag into the selected display PCI
device's properties. These properties may be reused after an i915
probe error, but the GPU's hardware mode/mapping may no longer
be functional. There is no guarantee of video recovery.

## Functional patch: staged after F21

File:
patches/candidates/netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch

Dependency: first apply
patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch
to the original pinned NetBSD C file. F20 and F19 touch other sources
and are not required for F22's functional code.

Changes:
1. Declare the option HP_I915_FWFB_FAILOVER using NetBSD config
   defflag in files.i915drmkms and include its generated option header.
   The default is **OFF**; the patch alone does not activate failover.
2. Expose wsemuldisplaydev as another interface attribute of the
   i915drmkms parent, permitting a configured wsdisplay child.
3. In opt-in builds only, embed struct genfb_softc as the FIRST
   member of the i915drmkms device softc. This is essential:
   genfb_enable_polling/disable_polling use device_private(sc_dev)
   to obtain the genfb_softc. A detached or stack-allocated softc
   would cause memory corruption.
4. If and only if deferred i915_driver_probe fails AND its synchronous
   task queue is empty, F21 clears sc_task_thread and invokes the
   optional UEFI console failover helper. Nonempty queues and
   successful i915 probes retain their original behavior.
5. The helper requires the console property, cn_tab->cn_dev==NODEV,
   a non-null preexisting framebuffer mapping, width and height
   within 640..8192 / 400..8192, 32bpp, a suitable stride and
   a matching wsdisplay child. It does not remap the framebuffer,
   force a GPU mode, or create a made-up console device number.
6. It disables extra shadow framebuffer allocation, calls native
   genfb_init on the persistent embedded genfb_softc, then invokes
   genfb_attach under the same NetBSD giant lock used by drmfb.
   The real wsdisplay attach path must assign cn_dev. A missing
   child is rejected BEFORE genfb_attach, and success is reported
   only if cn_dev is no longer NODEV.

This fallback is deliberately limited to 32bpp x86 UEFI-like mapped
framebuffers. It provides basic text-console operations, not an i915
GPU, accelerated modesetting, mmap, or reliable suspend/resume.
The original x86 genfb suspend/resume callbacks are NOT registered
by F22 because they assume pci_genfb_softc, not i915drmkms_softc.
The original GPU firmware configuration may already have been
damaged by the probe failure; F22 cannot restore it.

### Native ABI / lifetime caveats

- The actual complete C file has NOT been compiled against NetBSD
  kernel headers or linked into a kernel.
- genfb_attach can fail or return without completing a wsdisplay
  device despite a config_search match; F22 logs this but does not
  pretend it can safely undo wsdisplay state.
- A probe that succeeds but later fails to create an intelfb (e.g.
  CRTC/connector trouble) remains unaddressed.
- A failed probe with a NONEMPTY synchronous task queue remains
  unaddressed: the queued callbacks may retain freed framebuffer
  resources, and F22 must not execute or discard them casually.
- A firmware framebuffer may be nonfunctional after failed i915
  initialization. It is unsafe to claim a guaranteed boot.
- Adding an i915 interface attribute changes generated autoconf
  metadata even when the option is OFF; the actual C runtime path
  must remain equivalent to F21 and is explicitly checked.

## Executed reproducible test

Test:
tests/test_f22_i915_fwfb_failover.py

Legion run on full original C/config files checked by exact NetBSD
Git blob SHA, then native real git apply --whitespace=error --check
and actual git apply of both F21 and F22 in order. PASS.

The test also strips each optional C region and normalizes only
the one-statement conditional braces to verify the disabled F22
source is byte-identical to F21 (except the new generated-option
header, which is intentionally present but empty by default).

The helper is extracted in full, unchanged from the actually patched
NetBSD driver and compiled with host GCC/Clang, GNU99/GNU11,
-Wall -Wextra -Werror and UBSan. Four builds each execute 20 real
branches, for 80/80 passing host-C cases. Coverage includes:
successful wsdisplay cn_dev assignment, absent/invalid firmware
properties, missing wsdisplay child, unavailable framebuffer
mapping, denied shadowfb property, init failure, attach failure,
and apparently successful attach with cn_dev still NODEV.

Result marker:
F22_F21_F22_PINNED_GIT_APPLY_OPTION_OFF_EXACT_80_HOST_C_CASES_PASS

This is a host-side test with mocked kernel dependencies and does
NOT replace a native NetBSD compile or prove actual HP behavior.

## Non-negotiable safety gates

DO NOT add this option to the HP kernel configuration, install
an image, update boot.cfg, switch boot menu defaults, change F77
or request another failed menu-5 boot on this source-only evidence.

Before any physical attempt: actual native NetBSD compiler and link,
check generated autoconf tables/wsemuldisplaydev binding, ensure
the full i915+RTL port compiles, confirm no queued task lifetime
failure, preserve recovery image, and obtain menu-5 exact panic
message and first meaningful DDB frames independently.

Original sources:
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/pci/pci_machdep.c
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/wsfb/genfb.c
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/wscons/wsdisplay.c
