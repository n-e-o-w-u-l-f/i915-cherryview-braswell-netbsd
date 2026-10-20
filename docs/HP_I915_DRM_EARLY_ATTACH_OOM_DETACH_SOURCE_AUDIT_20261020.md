# HP-I915 — NetBSD DRM early `attach()` ENOMEM and `detach()` source audit

Date: 2026-10-20 (Europe/Berlin).  
Status: **PINNED SOURCE-ONLY; NO NEW DRIVER PATCH; NO RUNTIME / NATIVE KERNEL ACCEPTANCE**.  
Source branch before this audit: `7dd4ed9ec42a8f98b1570407ff7a82b60e6a2f1c`.  
NetBSD pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Standalone [0047 corrected](../candidates/0047-netbsd11-i915-pci-mmio-mapping-size-and-agp-borrow-owner.patch), Git blob `b83637537e5ce2a2924ff40a786bacf1cc00fcea`; standalone [0048 OOM propagation](../candidates/0048-netbsd11-drm-linux-pci-dev-init-oom-propagation.patch), blob `b84011509a49d889893977a237be9edca17977cf`. BOTH **UNINTEGRATED**. Their **combined patch creation was provider safety BLOCKED** and no artifact exists; this step is independent pinned source inspection, not a reroute.

## Exact NetBSD kernel contracts checked

| Source | Frozen Git blob | Read-only observation |
|---|---|---|
| [`sys/kern/subr_autoconf.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_autoconf.c) | `5ee8a7998b07fd570d7b1f67d23cdb814de63039` | `config_devalloc()` ~1590 allocates the device softc `dev_private` with `kmem_zalloc(..., KM_SLEEP)`, providing initially zeroed fields. `device_pmf_driver_deregister()` ~3349 resets suspend/resume handlers, clears power-handlers bit and waits for locks. Bus/class deregistration ~3528/3589 checks callback presence first. |
| [`sys/sys/queue.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/sys/queue.h) | `5e11055172fdf73757e6585f756b301cc889c399` | `SIMPLEQ_EMPTY(head)` reads `head->sqh_first == NULL` (~316). `SIMPLEQ_INIT` also initializes `sqh_last` (~333); an uninitialized zeroed head is **not** a fully initialized queue, but the simple empty check alone passes. Do not permit insertion without explicit initialization. |
| [`sys/kern/kern_pmf.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/kern_pmf.c) | `5f6e69ba9584fcda5ed6f09a227cfd2d3dd3dbb1` | `pmf_device_deregister` ~428 calls class/bus/driver deregister in that order; its component paths are detailed above. |

## Six driver detach paths

| Native frontend | Frozen blob | Detach contract |
|---|---|---|
| [`i915drm/i915_pci_autoconf.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c) | `9798385b02f247c08db9b16624d5ddc9d11a8ca5` | ~224: children detach, assert task-thread NULL and queue empty, PMF deregister, conditional i915 remove/workqueue destroy, common PCI destroy. |
| [`amdgpu/amdgpu_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/amdgpu/amdgpu_pci.c) | `267ebec239968897ea45f23eafd76d8d4ba5761d` | ~225: children and task assertions; conditional DRM unregister/detach/ref-put/workqueue; common PCI destroy. |
| [`radeon/radeon_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/radeon/radeon_pci.c) | `9610b65b82a72dafee89c90e3824409db34bb3cd` | ~330: same bounded checks and cleanup. |
| [`nouveau/nouveau_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/nouveau/nouveau_pci.c) | `c8479ce5653e589d5dde9f8818feecb729960ca6` | ~280: no queue assertion, guarded NVKM/DRM/workqueue cleanup, common PCI destroy. `nouveau_pci_match` ~105-147 uses temporary `pdev`, destroys it after successful PCI initialization and detection; staged 0048 would return match score zero if that initial allocation failed. |
| [`vmwgfx/vmwgfx_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/vmwgfx/vmwgfx_pci.c) | `6c7bc7e077cd87e44edb4f7cf4b550b821f2f75c` | ~256: children/task asserts and guarded DRM/workqueue cleanup. |
| [`via/via_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/via/via_pci.c) | `4093e9e1c4012665b7538dbf7941616418635ab0` | ~159: children/PMF and guarded DRM unregister/detach/put, common PCI destroy. |

At each of the six pinned `*_attach` entrypoints, an `int error` local already exists, so 0048's `error=linux_pci_dev_init(...)` does **not** introduce an undeclared variable. The source puts `SIMPLEQ_INIT` and workqueue allocation **after** PCI init in applicable frontends. Proposed 0048 returns before either operation if the `pdev->bus` `KM_NOSLEEP` allocation fails. The zero-initialized `sc_task_thread`, queue's `sqh_first`, conditional workqueue pointers and DRM flags thus do not by themselves establish a NULL dereference on later detach. The common 0048 destructor candidate null-checks `pdev->bus` prior to examining `bus->self`; its correctness requires real fail-path verification.

## Bounded conclusion, release checks and no reroute

**No additional concrete C defect was demonstrated by this narrow early-attach/detach audit; no new speculative patch was created.** In NetBSD, a `void attach()` returning early can leave an enumerated device instance without a working DRM driver; this needs driver outcome reporting/retry design and **must not be labeled hardware PASS**.

Required still: native fault injection for `KM_NOSLEEP` OOM → subsequent `config_detach`/PMF/workqueue state, device reprobe/retry behavior, and native compiler ABI after `linux_pci_dev_init` changes from `void` to `int`. **All NOT_RUN**. The original proposed `0047+0048` combined artifact was safety-blocked by the provider, was independently checked absent, and must **not** be recreated by equivalent alternate executor. Separately, earlier 0045's authored sixteen negative source mutations remain NOT_RUN after provider denial. Neither refusal can be labeled validation.

HP recovery G01–G09 early console and proven standard-kernel fallback **NOT VERIFIED**; i915/DRM/TTM+RTL native combined build, actual KMS, WLAN/WPA2 **NOT_RUN / NOT_VERIFIED**; 300 Linux→NetBSD semantic mapping units OPEN. No active driver source, HP kernel, bootloader or hardware changed.

Canonical governance: `Agent-Governance/state/events/hp-i915-drm-early-attach-oom-detach-source-audit-20261020.jsonl`.
