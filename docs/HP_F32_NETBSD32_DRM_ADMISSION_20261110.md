# F32: bounded NetBSD32 DRM admission and three native ABI owners — 2026-11-10

Scoped PASS on HP `hp-tpnw121.lan`, NetBSD 11 amd64, andreas uid1000.
Unsupported modern DRM calls from the separate NetBSD32 ioctl path now return
`ENOTTY` before argument preparation or user access. This is partial admission
protection; it does not implement Compat32 translation.

## Source behavior and selection

The pinned native NetBSD32 syscall never calls the new `fo_ioctl_user` hook.
Its old DRM conversion and `fo_ioctl` path therefore cannot be taken as proof
of modern Linux DRM compatibility. The new guard requires a non-null operations
table, the opt-in user ioctl hook and command group `d`. It follows the original
descriptor/access and FIOCLEX/FIONCLEX checks, precedes size/conversion/copy work,
and uses the original common exit with exactly one descriptor release.

All native source bytes outside this insertion are unchanged. Legacy DRM
without the hook and other command groups retain their original path. The
three-step F30 default remains unchanged; `--include-netbsd32-guard` explicitly
selects the fourth patch. All five original native files and every immediate
patch predecessor are hash-bound. F29's zero-size native ioctl correction is
retained in both selections.

Original `netbsd32_ioctl.c` SHA256:
`846c5602be6de8550aae1ea03e66e3e46a5107db20708987ece89b41a5184e46`.
Patched SHA256:
`d0385949c415c1810dbdcbb91197bd0766c6bbef6bd3ff232be3f40128f72c6d`.
Fourth patch SHA256:
`b1953c0a3c94fbccc079fcfeaacbb1fb4b32c8ac89c4e0dc389fccad5eb8a6d5`.

## Generated configuration prerequisite

The actual configured NetBSD32 owner needs direct object-directory `lockstat.h`,
a generated device-count header outside F31's default `opt_*.h` rule. The
selected fourth contract explicitly declares its exact basename and SHA256
`844d3989147b86eaa7fb6315a3e70934fecd634b5ad8225b71fb81188e7a25cd`.
It is a regular 269-byte file defining NLOCKSTAT=1; the pinned lockstat source,
GENERIC configuration and configured Makefile establish its role.

Only explicitly selected, frozen contracts may declare additional configuration.
Names, direct regular object-directory path and contents must all match; all
declarations must actually be consumed. Unsafe names, opt-header declarations,
malformed/duplicate metadata, wrong paths/hashes, unused declarations and drift
are rejected. Configuration remains separate from archive source proof.
The default admission policy and clean-Git source mode are preserved.

## Executed tests and review

- 21 new configuration-contract tests, 24 archive tests, 8 core-chain tests and
  8 F30 default-chain tests pass: 61 Python tests. Five new selection/CLI tests
  also pass, for 66 distinct Python tests.
- Nine exact native early-admission/common-exit C cases pass under C11,
  warnings-as-errors and UBSan, including 60 command direction/size combinations
  across modern DRM, legacy DRM and other groups. Eight semantic mutants compile
  and fail at their specific expected assertion and case with SIGABRT.
- The actual four-step Git patch chain passes check/apply with
  `--whitespace=error`; a corrupt-context control is rejected. The complete
  NetBSD32 result is byte-equal to its original after removing only the guard.
- A real public-wrapper invocation with the optional guard but without explicit
  archive mode exits2 for that precise reason before creating output.
- Independent read-only review of source, tests, input admission and the real
  negative CLI receipt found no remaining blocking findings.

The C fixture models descriptor operations and the later syscall body; it uses
actual early and exit source excerpts. It proves neither real Compat32
conversion/user-copy behavior nor concurrency or full FILE lifetime behavior.

Initial source-test attempt A01 preserved its passing CLI/default-chain tests
and a failed corrupt-context control anchor: the expected context was outside
the small patch hunk. Only that checker anchor was corrected to an existing
unique line. A02 reran the entire source/mutant suite successfully. No native
compiler failure occurred and no admission check was removed.

## Actual native ABI result

The public wrapper compiled the full patched `sys_generic.c`,
`kern_descrip.c` and `netbsd32_ioctl.c` with the actual F27 configured compiler,
kernel flags and F30 FILE headers. COMPAT_NETBSD32=1 is verified. All 14 commands
exit0: eight patch checks/applications, three preprocessor dependency scans and
three native object compilations. Every result is an ELF64 x86-64 relocatable
object with its expected exported function.

| Object | Bytes | SHA256 | Exported function |
|---|---:|---|---|
| sys_generic.o | 154048 | `7ec6e51289db74d055c9fd3dbc350277e3af997c3a532c90bfdadba6ad8411b6` | `sys_ioctl` |
| kern_descrip.o | 259968 | `18af52f144b9a2641a69f5d03ad819840242fbd2e388fa9b91042e7dd0625106` | `fd_get_linux_file` |
| netbsd32_ioctl.o | 308104 | `18d5c8bcdda0b71f3d075459d098c91c786d88f6b74d357be20405e78f469590` | `netbsd32_ioctl` |

The fixed NetBSD archive is verified through one bound regular file descriptor.
306 selected archive members, 34 generated options
headers and one separately declared configuration header are verified.
Precompile and postcompile dependency sets and bytes match. This is an
archive-used-subset proof; no clean Git identity or full source-tree identity
is fabricated.

Root independently rechecked the three object hashes/ELF types/exported symbols,
all consumed dependency hashes, ten tested source files, all four patch/contract
pairs, the five original native inputs, nine old object/dependency/stack files,
configuration, Makefile, tools, prior kernel and protected system files.
The original F27 checkout stays clean at `5c7ac64c8c740701365dfbf3bf9159cc13fcf344`.

## Evidence, governance and boundaries

[Summary and test receipts](evidence/HP_F32_NETBSD32_DRM_ADMISSION_20261110.json),
[complete native status](evidence/HP_F32_NATIVE_CORE_STATUS_20261110.json) and
[complete C/source status](evidence/HP_F32_SOURCE_STATUS_20261110.json) bind the
exact checked files. Native private output is
`/home/andreas/projects/hp-i915-f26-20261106/f32-native-abi-20261110-a01`;
A01/A02 source, configuration-unit, negative CLI and root-verification receipts
are retained alongside it.

Main PRE:
`state/events/hp-i915-f32-netbsd32-drm-admission-20261110.jsonl`.
Supplemental configuration PRE:
`state/events/hp-i915-f32-config-header-binding-20261110.jsonl`.
Both preserve their immutable scope fields through POST.

The running F77 kernel, /netbsd, boot configuration, EFI and radio were not
changed. Existing F27 outputs were not relinked. No full kernel build/link,
installation, boot, real Compat32 runtime, physical KMS, WPA2 or hosted CI was run.
HP-I915 remains PARTIAL. Fleet limitations and preserved mirrors from
[the F28 audit](HP_F28_MODERN_SOURCE_INTEGRATION_20261109.md#fleet) remain;
complete fleet synchronization is not claimed.

## Next scoped action

A bounded read-only F33 audit found that `tools/build_hp_native_provider.py`
still requires a clean Git source checkout and has no archive/dependency
admission path. The next source step adds explicit archive-used-subset admission
while preserving that default guard. Repository FILE/MM/UIO inputs need their
own reviewed Git blob identities and actual include/dependency proof; they
are not NetBSD archive members. Core configuration proof remains verified
without requiring every unrelated provider to consume lockstat.h.

Then a separate bounded native probe can compile `compat/native-file/linux_fd.c`
using the necessary native Linux KPI include roots. Full providers, FILE/MM/UVM
lifetimes, real Compat32 translation, complete kernel link and physical recovery
acceptance remain open. Earlier denied scopes remain excluded.
