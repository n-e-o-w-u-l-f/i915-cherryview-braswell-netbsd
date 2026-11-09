# F30: select the corrected native ioctl patch chain — 2026-11-10

Scoped source/composition PASS. The existing native FILE ABI entrypoint now
selects dispatch -> mmap-request -> early-drm-ioctl and delegates to the existing
guarded core builder with python -B. Both --netbsd-source and --source work.
HP/NetBSD11/amd64/nonroot, explicit toolchain, clean pinned Git source, flags,
source/header/tool/kernel hashes and exclusive private output remain delegated.
No automatic alternative source identity or native compiler execution is added.

The additive delta owns only sys/kern/sys_generic.c, from SHA256
7d9ffd3ad324a4efb1334a866cb06188be80f41338045d8e8ed24393243fa781 to
36d9743f193d7a7e40e0bbf0c2a84ee4183cadc21363d8261a54e60af443e977.
It binds mmap-request as its immediate predecessor. Dispatch/mmap patches and
contracts remain byte-exact. The two header files and fd owner retain their
existing recovered final bytes; syscall bytes exactly equal standalone F29.

## Executed evidence

On actual HP:8 new wrapper/contract tests and8 existing patchchain admission
tests PASS. The final -B child-interpreter adjustment is covered by another
8 affected tests PASS. Private complete-original-byte Git check/apply with
--whitespace=error passes for all three stages. Six negative controls reject
wrong order, doubled chain, patch drift, source-contract drift, corrupt source
context and double application of the final delta. Independent review found
no blocking source/delegation issue.

The first attempt failed only because a help-text assertion ignored argparse's
line wrapping. The test now compares normalized whitespace; the failed evidence
is retained. A02 is the complete acceptance run; A03 records final source
hashes and the bytecode-safe child invocation.

[Structured receipt](evidence/HP_F30_NATIVE_IOCTL_CHAIN_20261110.json).
Durable HP evidence: f30-native-ioctl-chain-20261110-a02 and -a03 under
/home/andreas/projects/hp-i915-f26-20261106.

## Native gate remains separate

The current source stage has no Git metadata. The existing strict Git source
guard correctly remains in force; no fabricated pin or fallback bypass is used.
F31 must add an explicitly selected, hard-pinned archive-used-subset provenance
mode and bind every consumed baseline dependency plus generated configuration
before actual native object compilation. Provider, UVM, Compat32, complete
kernel/physical KMS/WPA2 acceptance remain separate. No C compiler, kernel
installation/boot, EFI/radio/cleanup or hosted CI was invoked by this step.
