# HP-I915 0078 — Backlight-Class ABI / ownership contract (offline C model)

**TEST-ONLY:** This is a portable Linux-userland C11 *model*, **not** a NetBSD 11 kernel implementation, actual `intel_panel.c` execution, QEMU boot or HP hardware acceptance. The NetBSD `CONFIG_BACKLIGHT_CLASS_DEVICE` setting remains **0**.

## Pinned independent evidence

NetBSD/src@`03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
- `sys/external/bsd/drm2/drm/files.drmkms:47`: `CONFIG_BACKLIGHT_CLASS_DEVICE=0`.
- `sys/external/bsd/drm2/include/linux/backlight.h:35-41`: forward-declared `backlight_device`, only `backlight_enable/disable`.
- `sys/external/bsd/drm2/linux/linux_backlight.c:37-47`: those two functions return 0 without resource ownership.
- `sys/external/bsd/drm2/dist/drm/i915/display/intel_panel.c:1336-1397`: real i915 requires `backlight_properties`, `backlight_device_register/unregister` and a recorded device pointer, gated by config.
- `sys/external/bsd/drm2/dist/drm/i915/display/intel_connector.c:119-147`: backlight registration followed by probe-failure `-EFAULT` and local unwind.
- `sys/dev/wsfb/genfbvar.h:77-92`: native `genfb_parameter_callback`; brightness 0–255, backlight on/off 0–1. This range is **frontend** scope, not proof of physical PWM resolution.
- `sys/external/bsd/drm2/i915drm/intelfb.c`: normal `drmfb` callbacks, no i915 backlight provider wired.

**These observations come from the public, immutable NetBSD upstream source, not the denied 0071 Legion source preflight.**

## Run isolated reproducer (no network, no root, no NetBSD required)

```sh
python3 -m py_compile reproduce_0078_contract.py
python3 reproduce_0078_contract.py --verbose
```

Reproducer checks the C SHA256 `fab5e15866f0646782e2871ff42d86a0488e3d7018705f8fe514675563ecc747`, compiles with GCC and Clang using `-std=c11 -Werror` and runs each binary twice; then runs GCC+ASan+UBSan with leak checks. It requires both compilers, emits JSON with distinct `NOT_RUN` fields for kernel/QEMU/hardware and refuses mismatched markers.

**0078 local results:** Debian GCC 14.2.0 2/2, Clang 17.0.0 2/2, GCC ASan+UBSan 1/1. Every run reported `HP_I915_0078_MODEL_PASS checks=41 allocations=3 releases=3 registrations=3 unregistrations=3 live=0 gpu=0`. `python3 -m py_compile` and verbose reproducer also returned exit 0. The selftest does not exercise NetBSD `linux_backlight.c` or `intel_panel.c`; no actual driver was built.

## Next native step (separate gated task)

Implement minimum pinned ABI on a **separate isolated NetBSD test source tree**, including actual `backlight_device` struct, `backlight_properties`/`backlight_ops`, `bl_get_data`, ownership and `register/unregister`, and an explicit unsupported path. Do not globally flip `CONFIG_BACKLIGHT_CLASS_DEVICE=1` until missing types, constants, locking/refcount semantics, compilation and `-Werror` are proved; do not conflate `wsdisplay` on/off with brightness. Required gates: real native kernel link, QEMU positive/negative tests, 0 leaks, no-op negative control. 0071 provider-denied Legion operation is not to be repeated or rerouted.

[0078 Governance report](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/docs/HP-I915-0078-PINNED-BACKLIGHT-ABI-OWNERSHIP-MODEL-20261022.md).
