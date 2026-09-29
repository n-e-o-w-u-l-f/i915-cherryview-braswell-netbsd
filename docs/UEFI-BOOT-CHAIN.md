# UEFI / EFI / ELF boot-chain audit — HP 17-x037ng

Verified on the live HP TPN-W121 / NetBSD 11 target.

## Boot mode

- `machdep.bootmethod = UEFI`
- NetBSD reports an EFI system table and ACPI UEFI/BGRT tables.
- GOP/genfb is active before i915drmkms takeover.

## GPT and EFI System Partition

Physical disk: `wd0`.

- GPT index 1: 128 MiB, type `efi`, GUID type `c12a7328-f81f-11d2-ba4b-00a0c93ec93b`, FAT16.
- GPT label is misleadingly `Basic data partition`, but the actual partition type is EFI.
- GPT index 2: FFS root filesystem. Its label is misleadingly `EFI system partition`, but its actual type is NetBSD FFS.

Read-only FAT16 inspection of index 1 shows:

```
/EFI/BOOT/BOOTIA32.EFI
/EFI/BOOT/BOOTX64.EFI
```

## NetBSD EFI loader

Extracted `EFI/BOOT/BOOTX64.EFI`:

- PE32+ EFI application, x86-64
- SHA256: `55695265cff2bb52e0c1da9b443550e64710bc8357f120f1a93a19c631d42229`
- Exactly matches live NetBSD `/usr/mdec/bootx64.efi`.

Its PE Security Directory is zero, so this loader has no embedded Authenticode signature.

## Kernel format

The booted F77 kernel and F78 candidate are normal NetBSD ELF64 x86-64 executables. This is correct: UEFI loads the PE/COFF EFI loader, and the NetBSD EFI loader loads the ELF kernel from the NetBSD filesystem.

No i915 driver or Cherryview graphics firmware belongs on the EFI System Partition. Cherryview Gen8 has no Linux DMC/GuC/HuC blob requirement; its display bring-up is a driver/platform-state problem (GOP/VBT/OpRegion/KMS handoff), not a missing ESP firmware file.

## Secure Boot implication

Because the machine successfully boots the unsigned NetBSD `BOOTX64.EFI`, Secure Boot is not enforcing signature validation in the current configuration. Do not enable Secure Boot for the current unsigned NetBSD loader unless a signed/trusted loader chain is deliberately introduced.
