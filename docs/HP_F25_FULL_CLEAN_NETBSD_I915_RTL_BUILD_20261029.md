# F25 — genuine clean NetBSD 11 amd64 kernel build with F19–F22 and RTL8723BE

**Date:** 2026-10-29. **Result: full clean NetBSD kernel build PASS.**
**Safety:** Compilation-only WIP; DO NOT INSTALL/BOOT. The HP and recovery
F77 kernel and on-disk boot configuration were not touched.

## Scope and significance

F24 compiled the patched i915 driver and generated ioconf to true native
NetBSD amd64 objects and successfully re-linked a historical kernel object
tree. F25 removes this inherited-object limitation by invoking actual
NetBSD build.sh with a **new, empty kernel object directory**.

Original NetBSD source pin:
03d918f6d0e81fa05b8f1160eca0628ad39988a6

Four exact original source Git blob IDs checked before patching:

- sys/external/bsd/drm2/drm/drmfb.c:
  f71bee4c525b4199dc4e3eb52ad3f321787e5905
- sys/arch/x86/x86/consinit.c:
  9ef384c2c07a2202040d0fe672fdfa58a5c07a78
- sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c:
  9798385b02f247c08db9b16624d5ddc9d11a8ca5
- sys/external/bsd/drm2/i915drm/files.i915drmkms:
  23d352b64eb1799caf3e9b2770f78795accc8439

RTL8723BE input is the pre-existing PHY development stage,
netbsd-rtl-phy-df3bc40, independently verified against source
sys/dev/pci/rtwn8723be_netbsd.c native Git blob
9542ec44fddf5861fd815cb065af3b3330306726.
It was an existing partial WIP stage, not a finished RTL driver release.

Native source patches applied to real files, in exact order:

1. F19: drmfb wsdisplay preflight before handoff.
2. F20: x86 GOP/genfb early return-zero fallback.
3. F21: i915 deferred probe error task-owner cleanup when queue empty.
4. F22: optional firmware genfb fallback after failed i915 probe.

All four real git apply --whitespace=error --check and git apply PASS.
In this **isolated compilation-only** config, option
HP_I915_FWFB_FAILOVER was enabled to compile and link the candidate
implementation. The default kernel configuration is NOT changed.

## Isolation and the first aborted build

The source tree is a shallow symlink overlay: all unchanged files point
to the original RTL PHY NetBSD source stage; the four modified native
source/config files are written as separate new regular files. The new
NetBSD kernel config is F25_CONSOLE_RTL_TEST, based on
RTWN8723BE_STAGE (the pre-existing config explicitly says
"COMPILATION-ONLY PARTIAL RTL8723BE WIP target. Never boot/install.")
and adds only the opt-in F22 switch.

The first build.sh attempt aborted before compilation because
build.sh tried writing into the historical source tree via a
sys/arch/amd64/compile symlink. It also needed to regenerate the
nbmake-amd64 wrapper, which was owned by the historical build user.
These are host build-environment mistakes, NOT i915 compile failures.

Correction: sys/arch/amd64/compile is a real, writable directory
in the overlay, containing only the original Makefile. The existing
NetBSD cross tools (288 MB) are copied to a private /tmp toolchain
directory, where build.sh may safely regenerate its wrapper.
No changes or permission modifications were made to the original
historical source/tools.

Actual command from isolated scratch source directory:
./build.sh -U -m amd64 -j8 -O [scratch]/obj -T [scratch]/tools
kernel=F25_CONSOLE_RTL_TEST

This time build.sh exited **0 after 207.44 seconds** and printed the
successful NetBSD kernel path and "build.sh ended" marker.

## Independently checked actual output

- New generated NetBSD configuration has
  HP_I915_FWFB_FAILOVER=1: PASS.
- Generated ioconf.c registers
  wsemuldisplaydevcf_iattrdata for i915drmkms: PASS.
- Native i915_pci_autoconf.o (F21/F22) freshly compiled: PASS.
- Native drmfb.o (F19) freshly compiled: PASS.
- Native consinit.o (F20) freshly compiled: PASS.
- Native ioconf.o freshly compiled: PASS.
- Native RTL8723BE files rtwn8723be_netbsd.o and
  rtwn8723be_phy_exec.o freshly compiled: PASS.
- Full new kernel object directory: **3,265 .o files**.
- Complete kernel link PASS, ELF64 x86-64 executable.
- netbsd.gdb includes .SUNW_ctf CTF section.
- Linked executable size: **29,652,352 bytes**.
- First full clean kernel SHA-256:
  ed47039ca403bd16658e57b3cb7da02ac9d643e9766ca6d0866a7e6c759adcbd

The entire build happened on the connected Legion **Linux** machine
using the NetBSD crosscompiler; no NetBSD host or HP was booted.

Reproducible, safety-gated Python tool:
tools/run_f25_clean_netbsd_console_kernel.py

The script refuses existing output directories, non-/tmp destinations,
unpinned NetBSD i915 original blobs, a wrong RTL PHY source blob,
missing NetBSD toolchain, and kernel configurations not marked as
nonbootable WIP. It makes new scratch source and toolchain overlays
and calls actual NetBSD build.sh without reusing any precompiled
kernel object.

## Cherryview/Braswell candidate distinction

This F25 build tests that the native kernel baseline can compile
the **console repair stack and RTL PHY development stage together**.
It does NOT apply every separate experimental Cherryview display
patch from this repository.

An additional source-only composition audit found that the old
CHV DPIO "explicit PHY" patch and newer "signal PHY consumer"
patch have overlapping changes in intel_sideband.c and
intel_sideband.h. Both apply individually to the original source,
but not sequentially as a simple concatenation.

The two CHV GPLL patches similarly overlap: the later
"GPLL RPS lock order" patch contains the clock helper introduced by
the earlier "VLV GPLL clock" patch, so applying both consecutively
causes a context mismatch. The candidate patch series requires
deduplication/variant selection before producing an integrated
CHV kernel build.

Therefore F25 is a full clean compile **of its stated kernel
configuration**, not proof of a complete, production-ready
Cherryview/Braswell graphics port.

## Still required before hardware evaluation

- Integrate a coherent, deduplicated Cherryview display patch set
  and independently clean-build that exact source state.
- Check F22 firmware framebuffer preservation during failed i915
  hardware probe; actual UEFI mapping may already be invalid.
- Identify the actual HP boot-menu-5 image, exact first panic line
  and relevant DDB stack frames. Do not attribute this panic to
  the F81 cnopen issue without evidence.
- Preserve known working F77 recovery, /netbsd, boot.cfg and HP
  boot default. **No physical boot or installation occurred.**

A successful kernel compilation and link are not hardware proof,
and this build artifact MUST NOT be installed on the HP.
