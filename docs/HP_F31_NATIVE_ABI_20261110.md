# F31: archive-verified native FILE ABI objects — 2026-11-10

Scoped native ABI PASS on the actual HP, NetBSD11amd64, andreas uid1000.
The public FILE probe used the F30 corrected chain, explicit pinned archive and
actual private F27 toolchain/configuration. All10 commands exit0.

## Actual native artifacts

| Object | Bytes | SHA256 |
|---|---:|---|
| sys_generic.o |154048|b86726e5e9bc535de50def59bc0c0cdc5565570c9f22247af51bcb56685c954a|
| kern_descrip.o |259968|ec11edcd3c0d613c562ea8bf5bf9edb35d940d5a06e46623878716ecbdd59600|

Independent readback confirms ELF64 x86-64 relocatable objects and exported
sys_ioctl/fd_get_linux_file definitions. The patched file.h/filedesc.h were
consumed. Source dependency sets contain242 and239 paths respectively.

## Provenance and controls

The ordinary Git path still requires exact source pin and clean Git status.
Only explicit --source-archive selects ARCHIVE_USED_SUBSET; no Git identity is
fabricated for the archive-extracted stage. The fixed archive SHA256 is
3645aca2c1ac9716558075b7747a98583a8e87435f00ff30c786b4b438dbe15b.

One regular archive FD remains identity-bound through hashing and TAR reads.
213 original/used baseline source members are verified against regular archive
bytes without extraction. Actual compiler -M dependency scans run before object
compilation; -MD sets and bytes are rechecked afterward.32 generated opt headers
are separately frozen current configuration, not claimed pinned archive bytes.
Foreign dependencies, unbound overlay files, source/config/tool drift, links,
duplicate or missing archive members fail closed.

24 new provenance/env/artifact/CLI tests plus8 existing core and8 F30 tests pass.
Independent reviews prompted sanitizing four ambient Git selectors and freezing
all six prior .o/.d/.su files, including absence when relevant. All source tests,
Makefile, tools, prior objects/sidecars and kernel hashes are rechecked.
A separate root readback initially used relative receipt filenames without the
object directory; correcting that read-only invocation independently confirmed
all six existing artifacts unchanged. No compile was repeated for that issue.

[Summary and test receipt](evidence/HP_F31_NATIVE_ABI_20261110.json).
[Complete native command/dependency receipt](evidence/HP_F31_NATIVE_CORE_STATUS_20261110.json).
Durable HP output:
/home/andreas/projects/hp-i915-f26-20261106/f31-native-abi-20261110-a01.
No process remains active.

## Scope and next action

These are two native source-owner objects, not a complete kernel or all Fileops
consumers/providers. Do not substitute them into an old kernel: the changed
fileops layout requires consistent consumer rebuild and complete link acceptance.
F77, installed /netbsd, /boot.cfg, EFI and radio are unchanged; no install, boot,
repository cleanup or hosted CI occurred.

The separate netbsd32 ioctl path bypasses fo_ioctl_user. Its modern-file path
therefore still reaches legacy native marshalling. Next is a bounded early
admission gate for opt-in modern DRM files, preserving legacy/non-DRM behavior,
with explicit ENOTTY until real Compat32 translation is implemented. This is a
partial safety gate, not Compat32 support. FILE/MM/UVM/lifetime, full configured
kernel/link, physical KMS/WPA2/PM/recovery remain open.
