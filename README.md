# i915-cherryview-braswell-netbsd

Experimental NetBSD i915/DRM work for Intel Cherryview/Braswell graphics, focused on KMS bring-up, display initialization, Linux driver comparison, firmware analysis, and blackscreen debugging.

## Target hardware

- HP TPN-W121
- Intel Celeron N3060 / Braswell
- GPU: Intel HD Graphics
- PCI ID: `8086:22b1`
- Revision: `0x35`
- Subsystem: `103c:8205`
- NetBSD: 11.0 amd64

## Important finding: firmware

The target GPU is **Cherryview (CHV), Gen8 LP**, not Broxton (BXT).

Current Linux i915 documentation states that the GuC/HuC/DMC microcontroller firmware model starts with Gen9. The current Linux firmware packages contain BXT, GLK, SKL and later i915 firmware, but no Cherryview-specific i915 firmware. NetBSD's imported i915 source likewise has no CSR/DMC firmware selection for CHV.

Therefore this project does **not** manufacture or substitute a BXT DMC/GuC/HuC blob for CHV. The correct porting target is the CHV driver/display path itself.

## Current NetBSD baseline

`i915drmkms` is currently disabled at boot because enabling it causes a blackscreen. The safe console path is:

```text
i915drmkms* disabled
acpivga0 at acpi0 (GFX0): ACPI Display Adapter
genfb0 at pci0 dev 2 function 0: Intel HD Graphics (rev. 0x35)
wsdisplay0 at genfb0
drm at genfb0 not configured
```

The production `/netbsd` kernel has not been replaced by an experimental i915 kernel.

## Driver direction

The NetBSD 11 source already maps `8086:22b1` through `INTEL_CHV_IDS()` to `chv_info`, identifies the platform as Gen8, and contains Cherryview-specific DPIO/IRQ/display paths. The investigation therefore focuses on differences between this imported DRM snapshot and current/known-good Linux Cherryview support rather than inventing firmware.

See:

- [`docs/FIRMWARE-AUDIT.md`](docs/FIRMWARE-AUDIT.md)
- [`docs/DRIVER-MAPPING.md`](docs/DRIVER-MAPPING.md)
- [`STATUS.md`](STATUS.md)

## Safety / test policy

Experimental kernels are installed under separate names. The known-good production kernel remains untouched. No reboot is performed automatically. Every hardware-access change must be isolated, documented, built, hashed, and tested with a fallback kernel.
