# Cherryview/Braswell firmware audit

Target GPU: Intel `8086:22b1`, revision `0x35`, subsystem `103c:8205`.
This is Cherryview (CHV), Gen8 LP / Braswell, not Broxton (BXT).

## Cross-OS result

Current Arch Linux linux-firmware packages expose BXT, GLK, SKL and newer i915 firmware families, but no Cherryview-specific i915 firmware family.

Debian's firmware-intel-graphics package is the corresponding packaged Intel GPU firmware collection. Its existence does not establish a Cherryview DMC, GuC or HuC requirement.

Upstream Linux i915 documentation places the GuC/HuC/DMC microcontroller firmware model at Gen9 and newer. CHV is Gen8.

## NetBSD result

NetBSD 11's imported i915 `intel_csr.c` selects CSR/DMC firmware for newer platforms including Skylake, Broxton, Gemini Lake, Kaby/Coffee Lake and later generations. There is no Cherryview branch.

The CHV device description also does not use the later Gen9-style GT UC/CSR firmware model.

## Decision

No legitimate Cherryview-specific i915 firmware blob was identified in the Linux firmware sources examined. This project therefore does not substitute BXT firmware for CHV.

The blackscreen work must continue as a CHV driver/display initialization port.

NetBSD's normal firmware search locations include:

```text
/libdata/firmware
/usr/libdata/firmware
/usr/pkg/libdata/firmware
/usr/pkg/libdata
```

Any future firmware addition must be justified by an exact driver request for the target platform.