# F24 — Native NetBSD F21/F22 kernel compilation and ELF/CTF link

**2026-10-28. NATIVE COMPILE/LINK PASS; NOT A BOOT RELEASE.**

## What has been built

This is the first true NetBSD 11 amd64 native ABI build for the
i915 F21 and F22 patches. The already available historical NetBSD
crosscompiler and native build tools on Legion were located outside
the regular PATH. Neither the physical HP nor its recovery kernel
F77, installed kernels, firmware or boot.cfg was touched.

NetBSD original source commit:
03d918f6d0e81fa05b8f1160eca0628ad39988a6

Exact original Git blobs checked in both the pinned full source
tree and the historical RTL staging tree:

- i915_pci_autoconf.c = 9798385b02f247c08db9b16624d5ddc9d11a8ca5
- files.i915drmkms = 23d352b64eb1799caf3e9b2770f78795accc8439

Candidate F21 applied before F22. Real git apply --check and
git apply --whitespace=error on complete native C/config sources:
PASS.

The actual native x86_64--netbsd-gcc crosscompiler identifies as
NetBSD nb3 20260326, GCC 12.5.0. The historically generated
NetBSD kernel headers and the previous real kernel compile log
supplied the native kernel GCC arguments.

## Real NetBSD configuration and source compilation

- NetBSD nbconfig executed for HP_I915_FWFB_FAILOVER OFF and ON
  using the prior RTL staging kernel configuration: BOTH PASS.
- The NetBSD-generated option header is undefined for OFF,
  defined to 1 for ON: PASS.
- The NetBSD-generated ioconf.c for each option has the new
  wsemuldisplaydevcf_iattrdata interface in i915drmkms_attrs.
  Relative to the historical ioconf.c, the only differences
  are that attribute line and a generated pathname comment.
  This proves NetBSD autoconfiguration sees the new wsdisplay
  parent attribute; the previously tested mock did not.
- Entire NetBSD native i915_pci_autoconf.c compiled with
  real kernel flags and generated headers, F22 OFF: PASS.
- Entire NetBSD native i915_pci_autoconf.c compiled with
  real kernel flags and generated headers, F22 ON: PASS.
- Generated native ioconf.c compiled to ioconf.o: PASS.

## Actual native kernel linking

The historical RTWN8723BE_STAGE kernel object directory was
copied to a new scratch directory. ONLY the two rebuilt
i915_pci_autoconf.o and ioconf.o replaced their old counterparts
there. All other older kernel objects remained as previously
compiled. The original historical object directory was READ ONLY.

NetBSD nbctfconvert ran on both new objects, then the actual
NetBSD kernel Makefile, linker, CTF merger and objcopy produced
a real ELF64 x86-64 NetBSD kernel and split debug files:
**PASS**. The generated netbsd.gdb contains .SUNW_ctf.

The first direct link attempt passed the ELF linker but initially
failed the CTF phase, because freshly compiled objects had not
yet run through nbctfconvert. Adding the correct historical
NetBSD CTF conversion step made the full link PASS.

First successful scratch kernel SHA-256:
0be5850a989d3ceb52404ce4238d53dc9ee9c314506c0ae7fdbb028e18e8d56b

The entire sequence was then encoded in a reproducible script:
tools/run_native_f22_netbsd_link_gate.py

That script independently repeated the original blob checks,
F21 + F22 real application, nbconfig OFF/ON, native driver
object builds, generated ioconf build, CTF conversion, complete
native kernel link and ELF/CTF validation. It exited 0 with marker:

F24_REAL_NETBSD_AMD64_KERNEL_RELINK_CTF_PASS

Second successful scratch-only kernel SHA-256:
6b0667243905220137e50da5cfb901dc75c24071e9e9de83d9f12b3a1df06a14

The artifact hashes differ because NetBSD regenerates vers.c
with the current build timestamp on each link. This is a
reproducible **build-pass gate**, not byte-for-byte deterministic
kernel image reproducibility.

## Safety and scope

The reused kernel is named RTWN8723BE_STAGE, whose actual
kernel configuration calls it a COMPILATION-ONLY PARTIAL
RTL8723BE WIP target and explicitly prohibits boot/install.

**NOT DONE:** full clean recompilation of all current i915
Cherryview/Braswell candidate patches, full clean RTL8723BE
port, hardware console validation, or physical HP boot.

An F22 fallback after a failed i915 driver probe can still
fail if the GPU has already damaged the firmware display mode
or mapping. F22 also does not cover every i915 failure path.
The actual panic string, stack frames and loaded image identity
from HP boot menu 5 remain unknown.

Neither kernel image is safe to install or boot. F22 stays
disabled by default in normal builds. No HP boot action or
recovery-state changes were taken.
