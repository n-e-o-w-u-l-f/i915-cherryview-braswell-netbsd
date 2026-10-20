# HP-I915 — linux_pci_dev_init allocation failure contract and six DRM frontends

Date: 2026-10-20 (Europe/Berlin).  
Status: **SOURCE-CONFIRMED MISSING OOM CHECK; NO BLIND 0048 PATCH; NATIVE TEST NOT_RUN**.  
Development baseline: `e51ee70cf6c0650bff464bd626161e42fa65cb14`.  
NetBSD source pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Project ownership: HP-I915 NetBSD 11 amd64/Cherryview/Braswell and combined RTL8723BE release, not an independent AMD/NVIDIA/VIA project. Because this is a **shared DRM PCI adapter**, source semantics must account for all consumers.

## Confirmed allocation invariant violation

Pinned NetBSD [`sys/external/bsd/drm2/linux/linux_pci.c:145–205`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c), Git blob `52be483d5d3410d7e2955c2c59704ee4a80b2c9b`, declares:

```c
void linux_pci_dev_init(struct pci_dev *pdev, ...)
{
    ...
    pdev->bus = kmem_zalloc(sizeof(*pdev->bus), KM_NOSLEEP);
    pdev->bus->pb_pc = pa->pa_pc;
    pdev->bus->pb_dev = parent;
    pdev->bus->number = pa->pa_bus;
    ...
    pdev->bus->self = alloc_fake_parent_device(parent, pa);
}
```

The current API returns `void`; **no failed-allocation check** appears between nonblocking `KM_NOSLEEP` allocation and immediate `pdev->bus` dereference. If the allocation actually returns NULL (resource pressure), the next dereference is invalid. This is a **source-proven conditional NULL-dereference hazard**, *not* a reproduced panic on HP.

The helper [`alloc_fake_parent_device():~81–143`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c#L81-L143) returns NULL if the parent is not a PCI bridge path; when the parent is a PCI device beneath a PPB, it makes an independent **`KM_SLEEP`** allocation. Thus simply replacing `KM_NOSLEEP` with `KM_SLEEP` would not establish that all callers are in a legal sleep context, or fix the pre-existing potential to block during match.

Destructor [`linux_pci_dev_destroy():~995–1020`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c#L995-L1020) checks `pdev->bus->self` before a separate `if (pdev->bus != NULL)` branch. Therefore merely allowing `pdev->bus` to stay NULL after init would also require **destructor error-path repair**. The earlier staged `0047` v4 fixes BAR-mapping cleanup only; it does not fix this bus-object allocation contract.

## All pinned direct callers — seven init sites across six DRM PCI frontends

| Frontend | Pinned Git blob and path | Direct caller context | Implication |
|---|---|---|---|
| i915 | [`i915drm/i915_pci_autoconf.c:148`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c#L148), `9798385b02f247c08db9b16624d5ddc9d11a8ca5` | `i915drmkms_attach` (void), before workqueue/firmware deferred init | A failure must prevent later use and be represented in subsequent detach. |
| nouveau | [`nouveau/nouveau_pci.c:134,159`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/nouveau/nouveau_pci.c#L115-L159), `c8479ce5653e589d5dde9f8818feecb729960ca6` | **Both `nouveau_pci_match` and `nouveau_pci_attach`**; match does preliminary `nvkm_device_pci_new` and calls `linux_pci_dev_destroy` on stack descriptor | The match path is special; no blanket permission to block/sleep. A failure must return no-match without leaking initialization. |
| amdgpu | [`amdgpu/amdgpu_pci.c:140`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/amdgpu/amdgpu_pci.c#L140), `267ebec239968897ea45f23eafd76d8d4ba5761d` | `amdgpu_attach` (void), prior to creating workqueue | Must propagate error or store init-success marker for safe detach. |
| vmwgfx | [`vmwgfx/vmwgfx_pci.c:146`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/vmwgfx/vmwgfx_pci.c#L146), `6c7bc7e077cd87e44edb4f7cf4b550b821f2f75c` | `vmwgfx_attach` (void), prior to creating workqueue | Same detach ownership requirement. |
| radeon | [`radeon/radeon_pci.c:~205`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/radeon/radeon_pci.c), `9610b65b82a72dafee89c90e3824409db34bb3cd` | `radeon_attach` (void), before deferred `radeon_attach_real` | Match/attach transitions need failure state safe for detach. |
| via | [`via/via_pci.c:129`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/via/via_pci.c#L129), `4093e9e1c4012665b7538dbf7941616418635ab0` | `viadrm_attach` (void), before synchronous DRM creation | Needs error-aware detach if init is incomplete. |

The seven occurrences were found through an exact pinned NetBSD GitHub code search and relevant source-file fetches. The six frontends also call `linux_pci_dev_destroy` in their detach paths; Nouveau additionally does so inside `match` for the temporary test descriptor. That establishes **call-site impact**, not that an out-of-memory state was induced or kernel behavior tested.

## A safe change needs a coherent contract, not only a one-line swap

A potential **future design**, explicitly **NOT yet coded or approved**, is:

1. Decide NetBSD PCI match/attach sleepability from exact autoconfiguration API contract. Investigate `alloc_fake_parent_device()` existing `KM_SLEEP` on a PPB path, not just `pdev->bus` allocation.
2. Convert `linux_pci_dev_init` from `void` to a status-returning initialization contract (`0` on complete success, `ENOMEM` on failed `KM_NOSLEEP`) **if** the six consumers can absorb it. Update declaration in `include/linux/pci.h` and all seven calls together, including Nouveau match.
3. Keep all partially-initialized PCI state safe: `linux_pci_dev_destroy` must not dereference `pdev->bus` before a null guard; confirm the initial `memset`, allocation cleanup and possible partially built fake-parent resources.
4. On attach errors, skip workqueue/DRM registration/firmware setup, and ensure subsequent autoconfig detach cannot dereference or double free a failed `pci_dev`. Add init-success metadata/cleanup rules only as justified by native state invariants.
5. Add **newly authorized** failure-injection acceptance for each of the seven call-sites and basic pre-existing Linux PCI descriptor semantics, followed by full native NetBSD C/kernel tests. No rerouting of previously denied equivalent i915 source regression.

A global `KM_SLEEP` substitution may look shorter but is **not verified safe** in Nouveau match. Replacing it alone is not a completed error-path repair. No `0048` C candidate has been created because the required API and multi-driver failure contracts are not independently approved or tested.

## Current release limits

The [0047 v4 MMIO KVA unwind](HP_I915_0047_V4_PCI_IOMAP_KVA_FAILURE_20261020.md) is **a staged source-only candidate**, not a built driver. Seven staged candidates 0013–0047 remain UNINTEGRATED; the 0045 sixteen-source-mutant regression remains AUTHORED **NOT_RUN** after provider denial. **300 semantic mapping units remain OPEN**, and full native NetBSD i915/DRM/TTM+RTL kernel link/boot, physical HP eDP/KMS, RTL WPA2 and G01–G09 early console with proven standard-kernel fallback are NOT_VERIFIED. No active HP kernel or bootloader change is authorized by this source audit.

Canonical governance PRE/POST: `Agent-Governance/state/events/hp-i915-linux-pci-init-allocation-contract-20261020.jsonl`.
