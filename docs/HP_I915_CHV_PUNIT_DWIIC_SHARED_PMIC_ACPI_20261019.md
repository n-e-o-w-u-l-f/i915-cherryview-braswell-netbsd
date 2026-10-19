# HP i915 / Cherryview PUNIT — kernel-global PMIC/I²C arbitration and Intel ACPI attach

**Status 2026-10-19: actual frozen-source cross-subsystem gaps identified; runtime applicability on HP UNKNOWN. No kernel source changes, native compilation, installation, reboot, or physical KMS proof.**

## Pinned references and observed source

Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`:

| Source | Git blob | Relevant behavior |
| --- | --- | --- |
| `arch/x86/platform/intel/iosf_mbi.c` | `40ae94db20d8e31d6812a119095e079e9a627d8` | `iosf_mbi_punit_acquire/release` count in-flight PUNIT accesses against shared PMIC I²C operations using **one kernel-global mutex, wait queue, and counters**; a separate `block_punit_i2c_access` path claims/awaits the PUNIT semaphore and applies CPU idle constraints |
| `drivers/i2c/busses/i2c-designware-baytrail.c` | `45774aa47c28c65c510b523eddc08348de30cfd4` | ACPI `_SEM` must evaluate to nonzero for PUNIT-shared bus; requires `iosf_mbi_available`, registers `dev->acquire_lock = iosf_mbi_block_punit_i2c_access` and `dev->release_lock = iosf_mbi_unblock_punit_i2c_access` |
| `drivers/i2c/busses/i2c-designware-platdrv.c` | `447af5523c2e4fc74e93f3cd22f8f0b380617e9c` | ACPI DesignWare device table explicitly contains Intel `80860F41` (Bay Trail) and `808622C1` (Cherry Trail) |

NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`:

| Source | Git blob | Confirmed difference |
| --- | --- | --- |
| `sys/dev/acpi/dwiic_acpi.c` | `6c8b32c817022f34d4f36b24c1cf94b8e7d5a9b7` | ACPI match table contains `AMD0010`, `AMDI0010`, `AMDI0510`, `APMC0D0F` only — neither Intel HID; does not query `_SEM` |
| `sys/dev/ic/dwiic.c` | `258490c8ac6a67e0715640047f86acd1fe44525f` | Configures `sc_i2c_tag.ic_exec = dwiic_i2c_exec` without setting `ic_acquire_bus`/`ic_release_bus` for shared PUNIT |
| `sys/dev/ic/dwiic_var.h` | `2e3f9682c1b6067028abf984675d3b16663c3e32` | Existing controller struct and I²C tag can be extended for *conditional* lock support |
| `sys/dev/i2c/i2cvar.h` | `eb2c009b3fb7153c68a62d5cc7d659ba949e5117` | Framework already provides `ic_acquire_bus` / `ic_release_bus` callback slots; no need to invent another I²C API |
| `sys/external/bsd/drm2/include/asm/iosf_mbi.h` | `b72c89aed5d1e0ad258c0dd8a6561eafe6398089` | i915 compatibility-layer PUNIT acquire/release/assert currently empty; offers no kernel-global PMIC arbitration |

## Exact semantic boundary

In pinned Linux, `iosf_mbi_punit_acquire` waits while a shared I²C PMIC operation is active, then increments a PUNIT counter; release decrements and wakes waiters. Conversely, the Linux I²C path blocks PUNIT clients, coordinates a PMIC semaphore, and releases the reservation. This is **more than a per-driver or header-local mutex**. An i915-only mutex cannot synchronize independent I²C drivers and does not implement the host/PUNIT PMIC semaphore handshake.

Linux `i2c_dw_baytrail_probe_lock_support` deliberately behaves differently for a controller *without* a shared PMIC bus (no `_SEM`/false value; no special locking) versus a controller with the ACPI flag (lock provider must be available before transfers). This is a **conditional hardware contract**. Neither the HP's actual ACPI `_SEM` nor its controller HID, PMIC model, active I²C driver and cross-driver contenders has been freshly collected. Consequently, **do not assert that this HP physically shares the bus, or that the current stub caused a hang**.

The NetBSD pinned ACPI DesignWare driver not matching `808622C1` is a separate *potential attach gap*. Do not enable an Intel HID unconditionally before supplying an appropriate, correctly ordered power/PMIC arbitration mechanism or confirming the device does not share the bus. Also check if a different NetBSD platform-specific attachment owns the actual HP device before adding one.

## Engineering design and acceptance gates

1. **HP ACPI/driver evidence first:** read `acpidump` / ACPICA tables when legitimate authorized target access is available; resolve the actual Cherryview controller's `_HID`, `_CID`, `_SEM` value, PMIC attachment, PCI and I²C driver owner. Preserve all current HP boot and network access.
2. **Kernel-global owner:** enumerate pinned NetBSD kernel consumers of MBI/PUNIT/PMIC access, including I²C, ACPI PMIC and any PUNIT sideband caller. If shared bus behavior is present, design one shared NetBSD object with correctly initialized mutual exclusion, reference counts, waiter/wakeup semantics, bounded semaphore acquisition, failure rollback, suspend/detach rules and lock ordering. No distinct per-translation-unit static locks or fictitious no-op success.
3. **Conditional I²C integration:** extend the correct Intel ACPI attachment *and* bind the existing NetBSD `ic_acquire_bus` and `ic_release_bus` callbacks only where `_SEM` demands the shared PMIC bus. Ensure I²C is not advertised as safely attached if the required arbitration backend is unavailable. Handle partial attach/PMF transitions and failure propagation.
4. **Proper PUNIT client integration:** replace the i915 DRM compatibility no-ops only after the global provider is real and selected by the actual NetBSD kernel filelist. Preserve Linux acquire/put nesting, thread context, lock dependency order and data-plane register use.
5. **Separate Valleyview CPU-latency guarantee:** the other NetBSD `linux/pm_qos.h` no-op affects Valleyview CPU package idle safety. Do not extrapolate the Bay Trail workaround to Cherryview without hardware evidence. Candidate `0042` still repairs source-level early cleanup only, is untested and cannot provide QoS semantics by itself.
6. **Verification before native build or boot:** source pin and negative regression; then native NetBSD lock/condition variable, error-injection and ACPI parser/PMIC handshake tests, independent recovery-safe HP-native kernel compile/link, isolated selectable candidate install, **user tests installed kernel before physical i915-KMS and WLAN acceptance**. The umbrella 323-source requirement and 300 OPEN statuses remain unchanged.

## Repeatable machine check

`tests/test_chv_punit_dwiic_acpi_boundary.py` anchors **eight exact frozen Git blobs** (Linux MBI, Bay Trail semaphore helper and ACPI platform; NetBSD ACPI DW driver, DW core, softc, I²C framework and MBI compatibility header). It asserts the *known unsafe missing-state*, records seven negative mutations and deliberately emits **BLOCKED_KERNEL_INTEGRATION**. This test is **authored but not executed in this turn**; historical host-side test execution was denied. Its passing would not constitute a semantically complete implementation.

**Publication state:** all verified artifacts here are repository **source evidence and design/negative gates**. No working kernel-global lock provider, target ACPI probe, native NetBSD compiled object, boot attempt or HP hardware acceptance is claimed. No i915 unit was reclassified as complete.
