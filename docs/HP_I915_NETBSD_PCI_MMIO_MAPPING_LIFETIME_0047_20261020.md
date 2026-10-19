# HP-I915 — 0047 NetBSD PCI MMIO mapping length and borrowed AGP ownership

Date: 2026-10-20 (Europe/Berlin)  
Review type: **PINNED SOURCE-IDENTIFIED BUG + UNINTEGRATED PATCH CANDIDATE; NO EXECUTABLE ACCEPTANCE**  
Project: NetBSD 11/amd64 Intel Cherryview/Braswell i915 DRM/KMS + RTL8723BE, HP TPN-W121.  
i915 branch before this step: `1367503902dbcf228accf3996bc4cf3ca29113ea`; new standalone candidate commit `eb3c41558cecdae089b1b47f6c65bdd19f03b05c`.  
Pinned NetBSD upstream: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Candidate: [0047 — MMIO mapped size and borrowed ownership](../candidates/0047-netbsd11-i915-pci-mmio-mapping-size-and-agp-borrow-owner.patch), Git blob `8b79001ee7e792bf14bc297ab41197361b0851c7`.

## Frozen source of truth

| Source | Exact blob | Relevant lines / verified contract |
|---|---|---|
| [`include/linux/pci.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/linux/pci.h) | `b7c8182891979230b00be3d43f70a77712f2adec` | `struct pci_dev.pd_resources`, ~161–190: `size` is PCI resource/BAR size; fields have `bst,bsh,kva,mapped` but **no length of a partial `bus_space_map`**. |
| [`linux/linux_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c) | `52be483d5d3410d7e2955c2c59704ee4a80b2c9b` | `linux_pci_dev_init` ~182–215 records full resource size from `pci_mapreg_info`; `pci_iomap` ~842–869 maps **the caller's size**; `pci_iounmap` ~872–884 unmaps **full resource.size** and only clears `kva`. |
| [`intel_uncore.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/intel_uncore.c) | `3a6513360eff015eb226a2a393f07bdf9e754dba` | `uncore_mmio_setup` ~1706–1745 chooses **2 MiB** mapping for Intel GEN≥5 (512 KiB for older), and uses `agp_i810_borrow` only if `pci_iomap` returns NULL. `uncore_mmio_cleanup` ~1748–1753 always calls `pci_iounmap`, regardless of borrowed map ownership. |
| [`agp_i810.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/agp_i810.c) | `fd0727d4a9dddcf84cedd43a3489d8e51cfc4baf` | `agp_i810_borrow()` ~785–800 returns a `bus_space_subregion` of an **existing AGP-owned** MMIO mapping without registering `pdev->pd_resources[i].kva`. Source comment warns borrowing is legacy kludge. |
| [`arch/x86/x86/bus_space.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/bus_space.c) | `a62f6479388e2e37825ffe8abd47e01a117433a8` | ~433–447 default MMIO is `PMAP_NOCACHE` (UC), PREFETCHABLE is WC, CACHEABLE is WB; ~880–925 `bus_space_barrier` emits x86 LFENCE/SFENCE/MFENCE as requested. |
| [`sys/dev/pci/pci_map.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/pci_map.c) | `a8b22d9ee257367f86eb2a71dfd5960cf20d4828` | `pci_mapreg_info` returns BAR size and PREFETCHABLE flag (when applicable); actual HP BAR flags and size **not read**. |

## Two independent source-confirmed mapping lifecycle defects

### Defect A — wrong length passed to PCI MMIO unmap

Original NetBSD `pci_iomap(pdev, i, size)` uses:

```c
bus_space_map(..., size, BUS_SPACE_MAP_LINEAR | pdev->pd_resources[i].flags, &bsh);
```

Original `pci_iounmap(pdev, kva)` then calls:

```c
bus_space_unmap(bst, bsh, pdev->pd_resources[i].size);
```

These sizes are **not guaranteed equal**: `pd_resources[i].size` is the discovered PCI BAR resource length from `pci_mapreg_info`, whereas `pci_iomap` has an independent caller-supplied `size` with only `resource.size < size` rejected. In i915, modern display generations request 2 MiB intentionally, reserving other BAR portions (e.g., GTT) for separate mappings. On a BAR larger than the requested segment, the original unmap size does not match the actual mapped length. **Specific HP BAR size, collision/recovery effect and any crash are unknown; do not manufacture a panic report.** The mapping API inconsistency is provable independent of hardware.

Original unmap also clears only `kva` and leaves `mapped=true`, making the metadata inconsistent for teardown/re-entry.

### Defect B — borrowed AGP handle passed to the wrong owner for cleanup

Original `uncore_mmio_setup` on NetBSD:

```c
uncore->regs = pci_iomap(pdev, mmio_bar, mmio_size);
if (!uncore->regs) {
    if (agp_i810_borrow(..., &uncore->regs_bsh)) {
        KASSERT(!pdev->pd_resources[mmio_bar].mapped);
        uncore->regs = bus_space_vaddr(..., uncore->regs_bsh);
    }
}
```

The fallback obtains a **borrowed** AGP mapping. It does not populate `pdev->pd_resources[mmio_bar].kva`. Nonetheless original `uncore_mmio_cleanup` unconditionally calls `pci_iounmap(pdev, uncore->regs)`, whose `kva` search ends with `KASSERT(i < PCI_NUM_RESOURCES)` if no resource matches. This is a **source-proven unmatched-ownership failure path**, conditional on entering the AGP borrow fallback. Whether HP Cherryview ever uses that fallback is UNKNOWN.

## Candidate 0047 — scope and static acceptance

The single candidate changes exactly three NetBSD-specific source files:

1. `include/linux/pci.h`: add `pd_resources[i].mapped_size` of type `bus_size_t`.
2. `linux/linux_pci.c`: initialize and store the *actual* `pci_iomap` request length; unmap with `mapped_size`; clear `mapped_size`, `kva` and `mapped` afterward.
3. `intel_uncore.c`: in the NetBSD-only teardown branch, **skip PCI unmap for `!pd_resources[mmio_bar].mapped`** (borrowed AGP mapping owned elsewhere); preserve the original `pci_iounmap` path for successful normal PCI mappings.

Source generation found a **unique full-line anchor per edit** across the three exact pinned blobs, produced five unified diff hunks (one header, three PCI compat, one uncore cleanup), and statically verified each local substitution has a byte-identical textual inverse. The GitHub patch candidate was retrieved byte-for-byte after publication. **This is not an executed `git apply --check`, compilation, linked kernel, automated regression or physical HP test.**

The project candidates 0013–0046 remain unchanged/unintegrated. 0047 is an **additional unintegrated candidate** and must participate in the complete combined source/ABI acceptance, not be taken to HP independently.

## Remaining engineering and release checks — all not run

| Scope | Required verification |
|---|---|
| `pci_iomap` normal mapping | PCI BAR greater than 2 MiB → map precisely 2 MiB → unmap precisely 2 MiB and reset metadata; repeat mapping without stale state. |
| BAR flags and PCI register ordering | Observe `pd_resources[0].flags` and effective PAT on the real HP. Default map UC; PREFETCHABLE may select WC. **Do not assert UC or require extra `bus_space_barrier` without actual device flags.** |
| Borrowed AGP lifetime | When `pci_iomap` is denied/fails but `agp_i810_borrow` succeeds, the uncore teardown must **not** attempt `pci_iounmap`, and must **not** unmap the AGP owner's handle. Test actual source/device assumptions before install. |
| Cross-module C ABI | Recompile NetBSD `linux_pci.c`, all users of `struct pci_dev` with the added field, and i915 `intel_uncore.c`; static patch does not prove ABI/binary compatibility. |
| AGP subregion contract | Independently verify `agp_i810_borrow()` `bus_space_subregion` length argument (`agp_i810_vga_regsize - size` versus requested `size`) on the exact x86 implementation. No change to global AGP code in 0047. |
| Native combined kernel / HP | Full DRM/TTM+i915+RTL native build/link, real KMS and WPA2; pending. Never use earlier `LINKED` observations as proof this new patch compiles or boots. |
| Recovery | G01–G09 independent early console and verified working standard-kernel fallback **before** any HP kernel install/boot. |
| Prior test denial | The original 0045 16-negative source mutations and equivalent denied executable regression remain `NOT_RUN`; do not reroute to another machine or tool. |

**No HP hardware, kernel, bootloader or live installed driver was touched.** This step is source candidate authoring plus source audit; 300 Linux→NetBSD semantic rows remain OPEN until a dedicated row is separately accepted. Canonical PRE/POST: `Agent-Governance/state/events/hp-i915-netbsd-pci-mmio-map-unmap-0047-20261020.jsonl`.
