# F29: native zero-size ioctl kernel-buffer boundary — 2026-11-10

Scoped source PASS. Opted-in native Linux DRM calls with zero argument bytes now
supply NULL as kernel data before the old UNIX raw-userpointer branch. Original
command, separate user address, direction translation, highbit admission and
legacy behavior are unchanged.

The new standalone candidate supersedes F11 for future native composition.
It applies to four complete pinned NetBSD03d918f6 originals; it must NOT be
stacked on recovered0038/dispatch. Compared with F11 result bytes, file.h,
filedesc.h and kern_descrip.c are identical. Only sys_generic.c gains the
scoped zero-size branch; its final SHA256 is
36d9743f193d7a7e40e0bbf0c2a84ee4183cadc21363d8261a54e60af443e977.

## Executed proof on HP

The checker verifies all four original hashes, actual Git check/apply with
--whitespace=error on new private copies, exact postimages and unchanged inputs.
A corrupt-context negative is rejected. Parent Git discovery/index variables
are disabled; the source stage has no Git metadata and is not reported Git-clean.

The combined C11/-Wall/-Wextra/-Werror/UBSan test uses unchanged native
early-admission/size/marshalling excerpts and five real derived DRM functions.
FD, descriptor, allocator and user-access surroundings are explicit models.
11 baseline cases pass;8 semantic mutants abort at the exact expected case
and assertion. These cover zero-sized forged GET_CAP with16-byte canonical
descriptor for all direction combinations,256-byte canonical heap allocation,
success/error output boundaries, positive-sized Linux reads/writes, unchanged
legacy/non-DRM userpointer behavior and rejected argument/copyin faults.
For zero-sized calls: NULL native data, internal canonical zero extension,
no user copy and zero output bytes.

Two initial attempts failed only in the new C fixture: a native macro
redefinition and an unused modeled file variable under-Werror. Both are fixed;
all attempts/logs are retained. Attempt A03 exits0 and includes exact tested
source, generated source, binary and log hashes.

[Structured evidence](evidence/HP_F29_NATIVE_ZERO_SIZE_IOCTL_20261110.json).
Durable HP output:
/home/andreas/projects/hp-i915-f26-20261106/f29-native-zero-size-ioctl-20261110-a03.

## Limits and next integration

This proves source behavior under the stated surroundings, not native
kernel-header compilation, complete file lifetime/UVM/Compat32 or hardware.
No actual memory corruption is claimed. Compat32 has its own ioctl preparation
and dispatch and remains separately open.

Next: preserve recovered dispatch and mmap-request contracts, append a
sys_generic-only F30delta with this exact postimage, and select that ordered
chain in the existing native fileops build entrypoint. Native object compilation
then needs independently verified source provenance; the archive-extracted
source must not be given a fabricated Git pin. F77,/netbsd,/boot.cfg,EFI and
radio remain unchanged; no build/install/boot/hostedCI action in this step.
