# HP-I915 0083 — Native-oriented Backlight Class API staging

**STATE: STAGED / FEATURE OFF / GCC+CLANG MOCK COMPILE PASS / NOT NETBSD KERNEL VERIFIED.**

This directory is an **independently compiled, kernel-oriented candidate**, not a modification of the production NetBSD driver. It is based on the exact pinned NetBSD/src commit `03d918f6d0e81fa05b8f1160eca0628ad39988a6` and Linux commit `fd179f8a05be3ccae366b9b96e176b51fbe54aab`. Files in this staging directory **MUST NOT be copied blindly** over existing NetBSD tree files.

## Implemented candidate contract

- `0083_linux_backlight_abi.h`: Linux-class `struct backlight_properties`, `backlight_ops`, `backlight_device`, `bl_get_data` and Linux alias exports; raw/platform/firmware enum, power constants and callback entrypoints.
- `0083_linux_backlight_class.c`: NetBSD-kernel-oriented `kmem_zalloc/kmem_free`, `mutex`, `condvar`, `RUN_ONCE`, error-pointer return semantics. Validates user maximum, requested level, power and callback. Exactly **one globally registered device** until the registry is extended to support multiple graphics devices. Duplicate registration returns `ERR_PTR(-EBUSY)`; allocation failure `ERR_PTR(-ENOMEM)`; malformed properties `ERR_PTR(-EINVAL)`.
- `backlight_disable/enable` set 4/0 power and invoke `ops->update_status`, serialized per device. A separate registry lock is **not held** while invoking the DRM callback. Unregister waits for already admitted callbacks before freeing and supports subsequent registration. `NULL` enable/disable returns 0 as Linux does.
- This is a **lifetime prototype**, not a hardware/provider mapping: **no sysfs, wsdisplay brightness API, ACPI, PWM, AUX, panel enable or real Intel GPU command**.
- No integration into `files.drmkms`, original `linux/backlight.h`, original `linux_backlight.c`, `intel_panel.c` or `intel_connector.c`. The currently pinned `CONFIG_BACKLIGHT_CLASS_DEVICE=0` remains unchanged.

## Test files

`test_0083.c` exercises malformed/absent descriptors, OOM injection, duplicate registration, power transitions, serialized in-flight callback and unregister, then subsequent re-registration; `mockinclude/` provides isolated POSIX pthread-based **test doubles** for NetBSD kernel primitives. These test doubles are **not NetBSD kernel headers**. Use:

```sh
python3 staging/0083/replay_0083.py
```

The runner first hashes all three principal sources against its embedded fixed SHA-256 manifest and refuses mismatches, compiles **with verbose `-v` and `-Werror`**, runs GCC and Clang five times each and a GCC AddressSanitizer+UBSan run with leak detection, and writes local verbose compiler logs. Recorded on isolated Debian host: GCC 14.2.0 **5/5 PASS**, Clang 17 **5/5 PASS**, GCC ASAN/UBSAN **1/1 PASS**. Each execution reports `HP_I915_0083_STAGED_ABI_PASS checks=26 alloc=3 free=3 callbacks=5`: **11×26 = 286 checks** over eleven synthetic fixture executions. This is not 286 independent scenarios and it is not a NetBSD native acceptance.

Pinned tested principal source identities (Git blobs):
- `0083_linux_backlight_abi.h`: `61bec89d2830d9770c443e88bba98c678b9a9c00`, SHA256 `ba6b5cbab440c10868e33d9494f6cea57b71346a4831ab9993d88c763c5be3af`.
- `0083_linux_backlight_class.c`: `de7470105d0a1b63227865a9978fd1278016d776`, SHA256 `cd3352478dae6a9fbef8ac65a13b5984379b94a6e21f8b96ee5daa3aa6088a3a`.
- `test_0083.c`: `a17e8285b161a1375658d27ce8f90998a30863d7`, SHA256 `35ee8d5d6704db07b1a862c260725d45ae53e364bf812e1de5dfbd0035d0e6ba`.
- `replay_0083.py`: Git blob `e348be0c59367fe2d5f91035d3715442b526fa57`.

## Integration gates (all still open)

1. Rebase/stage an actual patch **into** the pinned NetBSD `linux/backlight.h` and `linux_backlight.c` with documented ABI differences; preserve original `backlight_enable/disable` semantics while `CONFIG_BACKLIGHT_CLASS_DEVICE=0`.
2. **Real native NetBSD11 kernel compiler** against a genuinely configured kernel object tree and correct DRM includes (not the bare GCC command that failed in 0081). Check `intel_panel.c`, `intel_connector.c` and `intel_display_types.h`, plus Linux `ERR_PTR/IS_ERR` actual macros. Verify no IRQ/DRM lock inversion with fault injection.
3. Design NetBSD wsdisplay/ACPI brightness-owner registration, correct physical panel power behavior, rollback on backlight create failure and full detach. Remove misleading 'sysfs interface registered' assertion from Intel code when no sysfs exists. Reconcile the `#ifndef __NetBSD__` brightness-props update in `intel_panel.c`.
4. Until all above and native kernel/QEMU tests succeed, **DO NOT SET** `CONFIG_BACKLIGHT_CLASS_DEVICE=1`.
5. Before physical HP i915 boot: independent early console, physically exercised F77/Stock rollback and verified original F16.2 safe-textmode kernel. No reboot/install yet.

**Provider-denied effects:** 0071 Legion source preflight, 0081 HP header read and 0054/Nouveau denials are not retried or rerouted. Step 0083 had **no HP, Legion, kernel tree or boot operations**.
