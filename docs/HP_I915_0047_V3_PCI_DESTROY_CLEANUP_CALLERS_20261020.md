# HP-I915 — candidate 0047 v3: PCI destructor cleanup, partial-BAR lifetime and native DRM consumers

Date: 2026-10-20  
Status: **SOURCE-CONFIRMED DEFECT / UNINTEGRATED CANDIDATE / EXECUTABLE ACCEPTANCE NOT_RUN**  
i915 branch: `work/hp-native-drm-stage-replay-20261015`  
Source HEAD before edit: `f83b609b4d269d51cc31fda73e2d165912339bfc`  
0047 v3 candidate commit: `023ceaa9eb68bc2fedd33e979cfb1068e89fc234`; candidate blob `a62b6e05b01ec72246b88a24480ee47b6b217f5b` (v2 blob `752325b9c84d675868f64c3e0b8969070575e0d3` remains in Git history).  
Pinned NetBSD source `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

## Confirmed omitted destructor path in 0047 v2

Pinned [`linux/linux_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c), Git blob `52be483d5d3410d7e2955c2c59704ee4a80b2c9b`:
- `pci_iomap()` at ~842–864 maps *requested size*; the previous original unmap mismatch was addressed in 0047 v2 by recording `mapped_size`.
- `pci_iounmap()` at ~867–884 uses and clears `mapped_size` **only with 0047 v2 applied**.
- **`linux_pci_dev_destroy()` at ~995–1020 is a distinct fallback cleanup path**: on every resource whose `mapped` boolean is true it calls `bus_space_unmap(..., pd_resources[i].size)`, where `size` is the **full BAR resource size**. This remains wrong for partial BAR mapping even if the regular `pci_iounmap()` logic from 0047 v2 is present. Device teardown may therefore re-expose the exact length mismatch 0047 was intended to fix.

**0047 v3** changes this destructor loop to `bus_space_unmap(..., pd_resources[i].mapped_size)` and after successful unmapping clears `kva`, `mapped_size`, and `mapped`. In the normal successful i915 detach, `intel_uncore_fini_mmio()` releases the map first, making destructor cleanup a no-op for that BAR. The destructor branch remains necessary for resources **still marked mapped** when an earlier detach, failure unwind, or another driver's release path reaches the PCI device destructor.

## Verified native DRM teardown consumers (frozen sources, not inferred runtime)

| NetBSD native wrapper | Pinned blob | Source reference / caller |
|---|---|---|
| [i915 `i915_pci_autoconf.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c) | `9798385b02f247c08db9b16624d5ddc9d11a8ca5` | ~247: after `i915_driver_remove` and workqueue teardown, calls `linux_pci_dev_destroy(&sc->sc_pci_dev)` |
| [amdgpu `amdgpu_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/amdgpu/amdgpu_pci.c) | `267ebec239968897ea45f23eafd76d8d4ba5761d` | ~252: DRM detach/release then PCI destructor |
| [nouveau `nouveau_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/nouveau/nouveau_pci.c) | `c8479ce5653e589d5dde9f8818feecb729960ca6` | ~139: invokes destructor even from a `nvkm_device_pci_new` probe/detect path |
| [radeon `radeon_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/radeon/radeon_pci.c) | `9610b65b82a72dafee89c90e3824409db34bb3cd` | ~357: detach and PCI destructor |
| [vmwgfx `vmwgfx_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/vmwgfx/vmwgfx_pci.c) | `6c7bc7e077cd87e44edb4f7cf4b550b821f2f75c` | ~283: detach and PCI destructor |
| [via `via_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/via/via_pci.c) | `4093e9e1c4012665b7538dbf7941616418635ab0` | ~182: detach and PCI destructor |

This establishes **call-site reach**, not that every driver leaves a partial BAR mapping live in the destructor or has an observed bug. The compatibility struct-field addition affects DRM translation units using `struct pci_dev`, so native compilation must cover multiple DRM subsystems, not just i915.

## Staged patch v3 evidence and exact scope

The current [0047 v3 patch](../candidates/0047-netbsd11-i915-pci-mmio-mapping-size-and-agp-borrow-owner.patch), Git blob `a62b6e05b01ec72246b88a24480ee47b6b217f5b`, now has **seven** original-file unified diff hunks over **four** files:
1. `include/linux/pci.h` stores actual `mapped_size`;
2. `linux/linux_pci.c` initializes mapped size, honors zero=full-BAR, maps ordinary `pci_iomap` as UC rather than forwarding PREFETCHABLE/WC, and resets normal unmap metadata;
3. `linux/linux_pci.c` **new seventh hunk** at original line ~1006 fixes destructor unmap length and clears metadata;
4. `intel_uncore.c` leaves AGP-borrowed mappings to their AGP owner;
5. `agp_i810.c` passes requested size to `bus_space_subregion`.

The new hunk matched exactly once in the pinned `linux_pci.c` source at original line ~1010. The full original text replaced by the new loop restores byte-exactly under inverse substitution. The original v2 hunks were retained without rewriting, the new hunk's old/new line counts were constructed against the cumulative +12 earlier `linux_pci.c` line delta, and the exact GitHub candidate was fetched after update. **No `git apply --check`, actual reverse test, C compilation or hardware execution occurred; all remain NOT_RUN.**

## Next acceptance / regression matrix

| Scenario | Expected with 0047 v3 | Status |
|---|---|---|
| Normal partial BAR `pci_iomap(size)` followed by `pci_iounmap` | unmap exactly recorded `mapped_size`, zero mapping metadata | SOURCE CONTRACT / NOT_RUN |
| Partial BAR mapped, then PCI device destructor called without prior individual iounmap | destructor unmaps **mapped_size**, not resource BAR length; metadata reset | SOURCE CONTRACT / NOT_RUN |
| Normal i915 removal after `intel_uncore_fini_mmio` | no second unmap in `linux_pci_dev_destroy`, because `mapped=false` | SOURCE CONTRACT / NOT_RUN |
| `pci_iomap(...,0)` | requests full valid BAR as Linux API; uses UC ordinary mapping | SOURCE CONTRACT / NOT_RUN |
| AGP fallback mapping borrowed from `agp_i810_borrow` | `uncore_mmio_cleanup` avoids PCI-ownership unmap; destructor skips `mapped=false` | SOURCE CONTRACT / NOT_RUN |
| Other native DRM drivers | validate `struct pci_dev` ABI and normal/exceptions cleanup across i915, amdgpu, nouveau, radeon, vmwgfx and via | NATIVE COMPILATION NOT_RUN |
| Source patch composition | compile-safe header contracts and 0013/0014/0043/0044/0045/0046/0047 interplay | NOT_RUN |
| HP G01–G09 early console, stock-kernel recovery, actual KMS/WPA2 | independently prove before dangerous kernel/boot changes | NOT_VERIFIED |

**Independent source-risk to review later:** pinned `linux_pci_dev_init` allocates `pdev->bus` with `kmem_zalloc(..., KM_NOSLEEP)` and immediately dereferences it. This warrants a separate error-handling review, but is **not changed by 0047**; no assertion of an observed allocation failure.

The original 0045 sixteen negative source mutants remain **AUTHORED NOT_RUN** after previously refused equivalent execution; no reroute to another executor. The 300 Linux→NetBSD semantic rows are still OPEN. No HP kernel, bootloader, active C file or physical hardware state changed in this step. Canonical PRE/POST: `Agent-Governance/state/events/hp-i915-mmio-0047-v3-pci-device-destroy-lifecycle-20261020.jsonl`.
