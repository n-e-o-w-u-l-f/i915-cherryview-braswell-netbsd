# HP-I915 0070 — QEMU-only NetBSD 11 real DRM connector lifecycle

**Scope:** Actual pinned NetBSD 11/amd64 kernel DRM functions `drm_mode_config_init`, `drm_connector_init`, `drm_connector_register`, `drm_connector_unregister`, `drm_connector_cleanup` and `drm_mode_config_cleanup` execute inside a **QEMU TCG kernel**. The device and connector are synthetic. **No physical PCI Intel GPU, Cherryview/Braswell display, i915 connector callback, RTL8723BE, real sysfs or HP target is tested.**

## Inputs and safety

- NetBSD source pin `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
- Input baseline: **0069 QEMU scratch** `i915-0069-qemu-kernel-probe-20261021-a01`, with its existing 0069 i915 probe diagnostic. This patch is **incremental to 0069**, not applicable directly to pristine upstream NetBSD.
- Input guest image: `i915-0066-qemu-native-smoke-20261021-a01/netbsd11-root-quiet-ffs2.raw`, SHA256 `1210c3130785f399b4cc17e1cf32f1b3195a167f80fb7d9c39b91fafc495e586`, always attached `snapshot=on`.
- Native toolchain `/opt/ChatGPT/hp-driver-port/netbsd-tools-03d918f6/bin/nbmake-amd64`, QEMU `/usr/bin/qemu-system-x86_64`.
- No network (`-nic none`), no KVM, no HP SSH, no physical HP kernel/boot.cfg/EFI writes, no SSH trust bypass, no 0054/Nouveau denied-action retry.
- Source modifications are **test-only** and live in disposable copied `netbsd/sys/external/bsd/drm2/dist/drm/drm_connector.c` and `netbsd/sys/kern/init_main.c`. Production port code is unchanged.

## Reproduce on authorized Legion scratch only

```sh
python3 reproduce_0070.py \
  --baseline /var/lib/sentinelx/uploads/i915-0069-qemu-kernel-probe-20261021-a01 \
  --disk /var/lib/sentinelx/uploads/i915-0066-qemu-native-smoke-20261021-a01/netbsd11-root-quiet-ffs2.raw \
  --out /var/lib/sentinelx/uploads/i915-0070-replay-NEW-UNIQUE-ID
```

The script refuses existing destinations, unexpected baseline directory names, paths outside Legion scratch, or an unexpected guest image digest. It copies baseline source and object trees, applies the incremental patch, compiles the two modified objects with kernel `-Werror`, links a full kernel, runs the baseline negative control and two positive QEMU boots, checks exact debugcon output and disk/baseline immutability. QEMU monitor `quit` is **not** proof of a guest shutdown. Logs and `0070-reproduction-result.json` are written to the new scratch directory.

## Kernel runtime contract

The QEMU-only selftest uses `device_find_by_xname("mainbus0")` and a synthetic `drm_device` with a fake `drm_driver`; it **does not call `drm_dev_init` or attach any PCI hardware**. At runtime it checks DRM core initialization, initializes DRM mode configuration and a virtual connector, then verifies:

1. Unregistered DRM device: `drm_connector_register` returns 0 but leaves connector INITIALIZING; no `late_register` callback.
2. Registered DRM device, first `late_register`: controlled `-EFAULT`, connector remains INITIALIZING; this is the genuine DRM core error/rollback path.
3. Retry without injected failure: success, REGISTERED, and real `idr_find` resolves the connector's DRM mode object.
4. `drm_connector_unregister` twice: UNREGISTERED and exactly one `early_unregister` callback.
5. Real `drm_connector_cleanup` plus `drm_mode_config_cleanup`: connector count zero and object removed from IDR.

The test also checks the original 0069 i915 probe helper marker. `drm_core_init_complete=1` was observed in the initial QEMU run. If the DRM core is not ready, the test fails closed without manually initializing global connector IDAs.

NetBSD's `sys/external/bsd/drm2/drm/drm_sysfs.c` implements `drm_sysfs_connector_add` by setting `connector->kdev = connector->dev->dev` and returning 0; `drm_sysfs_connector_remove` is empty. The diagnostic explicitly reports `sysfs_stub=1` and cannot validate Linux sysfs object lifecycle or real hardware resource unwind.

Expected terminal debugcon line:

```text
HP_I915_0070_DRM_CONNECTOR_PASS init=1 no_dev=1 fail=1 success=1 unreg=1 cleanup=1 late=2 early=1 sysfs_stub=1 gpu=0
```

**Acceptance gate remains CLOSED for HP testboot:** independent physical early-console capture and exercised F77/stock fallback are not verified. The 0054 provider-denied scratch readback and Nouveau shim refusal are not retried.
