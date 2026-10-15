# HP i915 native file bridge build gate — 2026-10-16

## PRE: source-authoritative blocker

Reference: NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6,
Linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab.
The published adapter `compat/native-drm/drm_cdevsw.c` uses four
NetBSD-specific includes: `linux/file_netbsd.h`,
`linux/mm_netbsd.h`, `linux/task_netbsd.h`,
`drm/drm_file_netbsd.h`. The first, second and fourth are
absent in the frozen native NetBSD source checkout inspected on Legion.
Its historical `linux/file.h` expressly says that `fput(fp)`
is not implemented as a native drop-in equivalent of `fdput`.
This adapter therefore needs *additional owned and validated runtime code*:
native headers do not resolve the entire Linux file/inode/fput/close,
task/LWP, memory mapping, and event ABI.

The HP compile-only replay previously accepted three independently
compiled objects as PASSED without actually repeating a relocatable
link in that script. This is weaker than the earlier historical
`ld -r` evidence.

## IMPLEMENTED

`tools/build_hp_native_drm_adapter.py` now validates the four
specific bridge headers against its actual relocated compiler
`-I` roots. Missing headers or symlinks escaping the designated
NetBSD source stage fail before any compiler or output creation.
Presence is a *necessary* condition, not semantic ownership proof.

The HP-only compilation step now runs `x86_64--netbsd-ld -r`
against exactly the three newly produced objects and records the
partial link command, exit code, output size/hash and complete link
log hash. Zero-sized or failed link outputs fail the status gate.
It never installs or boots a kernel.

New `tests/test_hp_native_drm_build_closure_preflight.py`
checks absent/present/removed/escaping headers and exact `ld -r`
command construction via isolated synthetic Python fixtures.
The previous command relocation test remains intact.

## POST: actual execution and limits

On Legion a disposable source-only test harness compiled the
Python syntax and ran two tests:
`I915_HP_NATIVE_DRM_ARGV_RELOCATION_SOURCE_REGRESSION_PASS`
and `I915_HP_NATIVE_FILE_BRIDGE_HEADER_AND_LD_R_CONTRACT_PASS`.
No C compiler, NetBSD linker, driver or hardware was exercised.

Full 323 i915 translation-unit closure, actual target ELF symbol
ownership, DRM/TTM/GEM/UVM providers, native close lifetime,
kernel binary link, physical early G01–G09 trace and KMS remain
OPEN. No HP boot identity was read, no F77/GENERIC fallback assumed,
and no kernel, boot menu, GPU MMIO or firmware was modified.

NEXT: independently verify the current HP recovery console and
fresh source/object/tool stage, materialize all bridge header and
function owners, then execute this HP-only three-unit build and
relocatable link. Its PASS does not equal full-driver completion.
