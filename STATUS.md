# Project status

Date: 2026-09-14

## Hardware

HP TPN-W121, Intel Celeron N3060 / Braswell, NetBSD 11.0 amd64.

GPU:

```text
PCI vendor/device: 8086:22b1
Revision:           0x35
Subsystem:          103c:8205
Platform:           Intel Cherryview (CHV), Gen8 LP
```

## Reproduced problem

Normal boot with `i915drmkms` enabled results in a blackscreen.

Safe diagnostic boot currently keeps i915 disabled and uses `genfb0` for the console.

## Source findings

- NetBSD i915 PCI identification already contains the CHV device mapping.
- CHV-specific DPIO/PHY handling is already present in the imported driver.
- NetBSD's CSR/DMC loader has no CHV firmware selection.
- Current Arch Linux firmware listings contain BXT/GLK/SKL/newer i915 firmware but no CHV-specific i915 firmware family.
- Linux documentation describes GuC/HuC/DMC firmware beginning with Gen9; CHV is Gen8.

## Firmware conclusion

A BXT firmware blob is not a valid CHV firmware port. No source evidence currently supports adding a CHV DMC/GuC/HuC binary.

The project therefore changes direction from firmware fabrication to driver/display porting.

## Build/test history

A dedicated `I915-BSW-DISPLAY-OFF` kernel was built as a controlled diagnostic kernel. The production `/netbsd` kernel remains unchanged.

Known artifact:

```text
/netbsd.i915-bsw-display-off
SHA256 1df288ee93e30956e55ed4cdf8a1aa932bbb13d6a317bac77180e93ae35dbee4
```

The source was restored after the controlled build.

## Safety state

- No automatic reboot.
- Production `/netbsd` not replaced.
- i915 remains disabled for the normal diagnostic boot.
- Future driver changes must be isolated and reversible.

## Next work package

1. Diff the NetBSD CHV display path against a current Linux CHV implementation.
2. Identify changes that are specifically applicable to Gen8 CHV.
3. Port one functional change at a time.
4. Build a separate test kernel.
5. Preserve a fallback kernel and collect boot diagnostics before enabling the next stage.