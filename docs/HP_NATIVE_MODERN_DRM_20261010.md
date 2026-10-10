# Current HP NetBSD11 modern DRM file bridge — native three-object proof

Date: 2026-10-10 Europe/Berlin. This evidence is attached to the
existing complete Intel i915 Cherryview/Braswell port. The parent
acceptance is **NOT MET**; GPU is still genfb 1024x768, no DRM KMS.

## Correct source-of-truth distinction

The old 2026-10-06 native `drm_cdevsw.c` diagnostic report contains
42 GCC error lines / 29 distinct diagnostics for the **former**
modern/native ABI state. During current live access on HP NetBSD11,
a newer full native file bridge is already in the root-owned isolated
worktree. It differs from frozen NetBSD/src by approximately 849
unified diff lines (328 insertions, 410 deletions), including
`drm_native_open/read/poll/mmap/ioctl`, `linux_task_entry_*`,
minor, event and NetBSD fileops integration.

The **exact** current real HP stage source was saved without
reformatting or modification into
`compat/native-drm/drm_cdevsw.c`:
- GitHub commit: `7dbdc90fac2d18788bc312f4ccd7afc54e1fa739`
- source size: 13,377 bytes
- SHA256: `ae0ddb2629a89a2729fef8b1d6c00c865998d19d59c5a0aebafc7a66e6b0abc7`
- Native HP GitHub checkout readback: bytewise exact match to
  unchanged root-owned previously prepared source.

## Actual native HP compiler acceptance

The original NetBSD native compiler `x86_64--netbsd-gcc` was
replayed with **identical strict frozen kernel options and -Werror**,
not host-C mock flags. The compiler's working directory MUST be
the preexisting configured NetBSD object directory, because the
generated `machine/cdefs.h`, architecture/option headers are
resolved via `-I.`. A first owner-directory-only replay
rightly failed for lack of `machine/cdefs.h`, with no source
modification. Corrected to read-only native configured `cwd`,
all object destinations redirected into a private `andreas`
subdirectory. The source was hash-verified unchanged before
and after the compile.

Reproducible tool `tools/build_hp_native_drm_adapter.py`,
published in `53760ec56d0990af6adc05db86cb5c8345ed42b3`,
ran on **HP NetBSD 11** as an unprivileged existing owner:

| Object | Native compile exit | Bytes |
|---|---:|---:|
| `linux_task.o` | 0 | 150,840 |
| `linux_module.o` | 0 | 23,584 |
| `drm_cdevsw.o` | 0 | 165,976 |

`HP_NATIVE_MODERN_DRM_THREE_OBJECTS_PASS`

The three produced real NetBSD ELF objects were then linked
**relocatably** using native `x86_64--netbsd-ld -r` into
`modern_drm_three.o` (328,608 bytes), exit 0. Unresolved
externals are intentional at this intermediate stage, including
`drm_minor_acquire`, `drm_ioctl` and kernel atomic/task
functions; this is not a final kernel symbol/link gate.

Proof output path on real HP, not in GitHub (binary objects
are not copied to/from owner devices):

`/home/andreas/projects/driver-port-20261010/i915-native-drm-20261010/status.json`

Frozen input references remain:
- Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`
- NetBSD `03d918f6d0e81fa05b8f1160eca0628ad39988a6`

## Explicit remaining full-port work

This is a **three-object** successful compilation of the native
modern DRM file/task adapter, **not** a full 323-unit Linux
i915 + modern DRM/TTM/folio/GEM/UVM dependency closure.
Remaining: linkage and semantics of all external kernel/DRM
symbols, event/poll/kqueue/ioctl/mmap/PM contracts, memory
management & bus DMA, actual Intel PCI attach, firmware/IRQ,
gem/PPGTT, Cherryview eDP/HDMI modeset and stable display,
suspend/resume and recovery, final full kernel compile/link.

The HP still boots its tested F77 fallback. NO kernel was
installed, no graphics driver was enabled, no forced modeset
or reboot was performed. Preserve the tested fallback
until all gates are satisfied; source/partial linker success
must not be reported as functional GPU.
