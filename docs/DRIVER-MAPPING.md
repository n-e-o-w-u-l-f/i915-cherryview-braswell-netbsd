# Cherryview driver mapping

## PCI identity

| Item | Value |
|---|---|
| Vendor | Intel `0x8086` |
| Device | `0x22b1` |
| Class | VGA / display |
| Revision | `0x35` |
| Subsystem vendor | HP `0x103c` |
| Subsystem | `0x8205` |
| Architecture | Cherryview / Braswell |
| Generation | Gen8 LP |

## NetBSD mapping

The NetBSD 11 i915 PCI table already contains `INTEL_CHV_IDS(&chv_info)`.
The associated `chv_info` identifies the platform as Gen8 and enables the Cherryview-specific engine and display characteristics.

The imported driver also contains CHV-specific DPIO mapping. Cherryview uses two PHY groups: one path for the x2 PHY serving DP/HDMI B/C and another for the x1 PHY serving DP/HDMI D.

This means PCI identification is not the missing component. The investigation is further down the initialization path.

## Current safe state

Normal i915 KMS is disabled because enabling `i915drmkms` causes a blackscreen on the target machine. The fallback path remains `genfb0`/`wsdisplay0`.

A previous isolated display-off kernel was built successfully, but it is not the production kernel and has not replaced `/netbsd`.

## Driver-porting targets

The next porting stages are:

1. Compare NetBSD's imported CHV initialization with current Linux CHV display code.
2. Compare ACPI/VBT/OpRegion handling.
3. Compare Cherryview power-domain initialization.
4. Compare DPIO/PHY and PLL setup.
5. Compare initial framebuffer takeover and fbdev/KMS handoff.
6. Add diagnostic logging before changing hardware state.
7. Port only narrowly identified fixes and build isolated kernels.

## Important distinction

Do not change the CHV PCI ID to BXT and do not enable BXT firmware on this hardware. CHV and BXT are separate i915 platforms despite both being low-power Intel graphics generations.