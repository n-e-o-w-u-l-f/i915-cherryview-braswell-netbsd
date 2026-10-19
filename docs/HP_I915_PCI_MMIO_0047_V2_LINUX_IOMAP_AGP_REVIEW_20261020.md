# HP-I915 — candidate 0047 v2: Linux pci_iomap semantics and AGP subregion lifetime

Date: 2026-10-20 (Europe/Berlin)  
Status: **SOURCE REVIEW + STAGED CANDIDATE (NOT INTEGRATED / TESTS NOT_RUN)**  
Branch: `work/hp-native-drm-stage-replay-20261015`.  
Previous i915 HEAD: `6904d6691c05384e6126dd4c842391cbc762729d`; v2 patch update commit: `0622ec150b2238f7520f4129fe99ad1c37e9aad3`.  
Frozen NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.  
Frozen Linux: `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`.

## Main output

[**Candidate 0047 v2**](../candidates/0047-netbsd11-i915-pci-mmio-mapping-size-and-agp-borrow-owner.patch) now Git blob `752325b9c84d675868f64c3e0b8969070575e0d3` (previous v1 blob `8b79001ee7e792bf14bc297ab41197361b0851c7`, retained in old Git history, not the active candidate file). It now touches **four** frozen NetBSD C/header files, in **six** source hunks, extending the original mapped-length, unmap metadata and borrowed AGP ownership fix. This patch is a proposed *source* repair only, not part of an HP kernel.

## Pinned source / API findings

| Component | Verified pinned source | Required semantics and v2 handling |
|---|---|---|
| Linux [`drivers/pci/iomap.c`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/drivers/pci/iomap.c) Git blob `ea86c282a3869b8e276618544c49430828c0ff68`, `pci_iomap_range` ~29–54 and `pci_iomap` ~123–129 | **`maxlen=0` maps the full valid BAR**. For MEM, `pci_iomap_range` invokes `ioremap(start,len)`, while the separate WC API uses `ioremap_wc`. Linux checks BAR start and remaining length. |
| NetBSD [`linux/linux_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c) blob `52be483d5d3410d7e2955c2c59704ee4a80b2c9b`, `pci_iomap` ~842–866 | Before v2 it handed literal `size=0` to `bus_space_map` and propagated `pd_resources[i].flags`. **v2 normalizes zero to resource size**, rejects invalid zero BAR base/length, and requests `BUS_SPACE_MAP_LINEAR` without automatically forwarding `PREFETCHABLE` as WC. This is a portability-level behavior change that requires regression review for other users of the compat layer. |
| NetBSD [`sys/arch/x86/x86/bus_space.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/bus_space.c) blob `a62f6479388e2e37825ffe8abd47e01a117433a8`, ~433–446 and `bus_space_subregion` ~642–648 | Default memory map is **UC** (`PMAP_NOCACHE`); `BUS_SPACE_MAP_PREFETCHABLE` selects **WC**. `bus_space_subregion` on frozen x86 simply computes `*nbshp=bsh+offset` and ignores `size`. Neither fact proves the actual HP BAR attribute. |
| NetBSD [`sys/dev/pci/agp_i810.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/agp_i810.c) blob `fd0727d4a9dddcf84cedd43a3489d8e51cfc4baf`, `agp_i810_borrow` ~784–801 | Borrow function validates requested offset+length against the existing AGP-owned region but passes **`agp_i810_vga_regsize - size`** to `bus_space_subregion` rather than requested `size`. **v2 passes `size`**, preserving pointer arithmetic on this x86 implementation but repairing the API argument contract. No evidence that the old argument caused a real x86 run-time fault, because x86 ignores `size`. |
| NetBSD [`intel_uncore.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/intel_uncore.c) blob `3a6513360eff015eb226a2a393f07bdf9e754dba`, ~1706–1755 | i915 maps 2 MiB of register BAR for Gen≥5, then borrows an AGP-owned mapping only after `pci_iomap` failure. v2 preserves original 0047 fix not to call `pci_iounmap` on an AGP-borrowed mapping. |
| NetBSD [`include/linux/pci.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/linux/pci.h) blob `b7c8182891979230b00be3d43f70a77712f2adec` | v2 preserves original addition of `mapped_size`, enabling `pci_iounmap` to pass precisely the `bus_space_map` length and clear the mapped-state metadata after removal. |

## Why this is a driver-relevant fix, not a generic barrier patch

The original `0047` audit identified two *specific* lifetime errors: `pci_iomap` mapped a requested partial BAR but `pci_iounmap` unmapped the full resource size; and i915 cleaned up an AGP-owned borrowed map by looking for a PCI-owned KVA entry (which can fail its assertion). v2 additionally corrects the Linux compat `maxlen=0` and uncached `pci_iomap` contract. **Do not confuse any of these with an absent Cherryview IRQ `POSTING_READ`: the previous pinned IRQ review disproved that hypothesis.**

The Linux `pci_iomap` API is not identical to a WC mapping even when PCI hardware marks a memory BAR `PREFETCHABLE`; blindly forwarding that flag as a bus-space WC attribute changes memory ordering versus the ordinary Linux `ioremap` path. The code now requests the ordinary, uncached mapping on x86. Do not apply the same choice to unrelated explicitly WC mappings such as GTT/aperture; they are outside `pci_iomap`'s ordinary UC contract.

## Static construction evidence (not executable patch validation)

- **Source inputs:** exact NetBSD pinned Git blobs listed above, not current upstream tip; Linux API examined at exactly the pinned Linux reference.
- **Six unique anchored replacements:** `pci.h` one, `linux_pci.c` three, `intel_uncore.c` one, `agp_i810.c` one. Each original full-line snippet matched exactly once in the respective entire frozen input file.
- **Text-only property:** every replacement was checked with an exact inverse against the full original file; no source collisions or overlapping diff context windows were found. The complete v2 patch was published to GitHub with blob `752325b9c84d675868f64c3e0b8969070575e0d3` and then read back byte-identically.
- **Unrun:** `git apply --check` / application / reverse, C compiler, native NetBSD kernel build, actual MMIO mapping tests, AGP ownership teardown, physical HP KMS/RTL/WPA2 and the prior 0045 sixteen-negative source regression are all **NOT_RUN / NOT VERIFIED**. Source snippet uniqueness and diff header arithmetic do not establish successful patch application.

## Release and cross-platform gates

1. Independently verify all `pci_iomap` callers in DRM/TTM and whether any caller depends on the old accidental PREFETCHABLE/WC behavior. A general PCI compatibility-layer correction must not silently regress unrelated devices.
2. Review the actual `pci_iomap` / `pci_iounmap` unwind with small, deliberately varied BAR sizes: size==0, partial size, equal size, failed mapping, borrowed AGP and repeated setup/cleanup; do this **only** on genuinely authorized execution paths, without rerouting the provider-denied equivalent i915 source tests.
3. Confirm `agp_i810_borrow()` is never mistaken for ownership of the original MMIO map, and that the updated subregion size satisfies the cross-architecture API contract; actual target x86 ignores the subregion `size` parameter.
4. Under a truly authorized native NetBSD build, verify updated `struct pci_dev` ABI across its kernel compilation units and combine with DRM/TTM/i915/RTL. Source review is not C linkage.
5. Before HP install/boot, independently prove G01–G09 early console and a functioning standard-kernel fallback, then separately verify physical KMS and RTL WPA2. **300 source semantic rows still OPEN**, all candidates 0013–0047 remain unintegrated.

Original v1 report: [`HP_I915_NETBSD_PCI_MMIO_MAPPING_LIFETIME_0047_20261020.md`](HP_I915_NETBSD_PCI_MMIO_MAPPING_LIFETIME_0047_20261020.md) describes the **historical v1** candidate blob, not this v2. Ledger: `Agent-Governance/state/events/hp-i915-pci-mmio-0047-linux-abi-followup-20261020.jsonl`.
