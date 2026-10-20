# HP-I915 — 0047 v4: unwind a successful bus_space_map with unusable KVA

Date: 2026-10-20 (Europe/Berlin).  
Project: **HP-I915**, Intel Cherryview/Braswell + RTL8723BE in one recoverable NetBSD 11 amd64 kernel.  
Status: **SEPARATE C PATCH CANDIDATE, NOT INTEGRATED; SOURCE-ONLY ASSERTIONS; NO EXECUTABLE REGRESSION OR HP KERNEL TEST**.  
i915 branch baseline before this step: `3dcf5b189842ebd93d6ec0c8c9b8ae45b119a096`.  
Previous candidate 0047 v3 blob `a62b6e05b01ec72246b88a24480ee47b6b217f5b`; new v4 blob `76dd9732352dd1149b2899b1a771a9e01ebda5d5` at [the same versioned GitHub file path](../candidates/0047-netbsd11-i915-pci-mmio-mapping-size-and-agp-borrow-owner.patch). v3 is retained in normal Git history, not used as an active driver.

## Frozen sources and actual kernel contract

- [NetBSD/src `linux_pci.c:842–888`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c) Git blob `52be483d5d3410d7e2955c2c59704ee4a80b2c9b`. Original `pci_iomap` calls `bus_space_map`, then `bus_space_vaddr`, and stores `mapped=true` without checking the latter returned a usable pointer. v3 already introduced `mapped_size` and proper direct/teardown unmap size, but retained the unchecked KVA assignment.
- [NetBSD/src `intel_uncore.c:1706–1757`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/dist/drm/i915/intel_uncore.c) Git blob `3a6513360eff015eb226a2a393f07bdf9e754dba`. If `pci_iomap` gives NULL, `uncore_mmio_setup()` attempts an AGP borrowed mapping and asserts `!pdev->pd_resources[mmio_bar].mapped` on success. Returning NULL *with a retained mapping* violates that invariant.
- [NetBSD/src `bus_space.c:929–934`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/bus_space.c) Git blob `a62f6479388e2e37825ffe8abd47e01a117433a8`. NetBSD/amd64 default `bus_space_vaddr` returns `(void *)bsh` **for a memory tag**, NULL for I/O-space tags. Default `_x86_memio_map` produces a kernel VA mapping for a linear memory-space request; a successful default x86 BAR memory mapping without KVA is **not expected**. Chipset/tag override and other architecture implications require their own verification.
- [NetBSD 11 bus_space(9)](https://man.netbsd.org/NetBSD-11.0/bus_space.9): when `BUS_SPACE_MAP_LINEAR` is requested but linear mapping is impossible, `bus_space_map` **should fail**. Thus the v4 cleanup is primarily **defensive invariant enforcement**, NOT proof that a conforming amd64 bus-space driver actually returns NULL after a successful `BUS_SPACE_MAP_LINEAR` mapping.
- [NetBSD/src `linux/pci.h:170–188`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/linux/pci.h), blob `b7c8182891979230b00be3d43f70a77712f2adec`; v3's `mapped_size` field tracks the precise size of any mapped BAR resource, so the added rollback unmaps exactly that requested `size`.
- Previous [0047 v3 cleanup and DRM call-site audit](HP_I915_0047_V3_PCI_DESTROY_CLEANUP_CALLERS_20261020.md), Git blob `60076dc230233620df1fb14ebac5e96a0fe8232b`, established why both `pci_iounmap` and `linux_pci_dev_destroy` require mapped length instead of full BAR size.

## Candidate v4 — the one added fail-close branch

Only the `pci_iomap()` hunk was changed; all prior six other diff hunks and their source paths are preserved. The new condition occurs **after** a successful `bus_space_map` and setting `bst`/`kva`, but **before** `mapped_size` and `mapped` are set:

```c
pdev->pd_resources[i].kva = bus_space_vaddr(pdev->pd_resources[i].bst,
    pdev->pd_resources[i].bsh);
if (pdev->pd_resources[i].kva == NULL) {
    /* Do not retain a BAR mapping without a usable virtual address. */
    bus_space_unmap(pdev->pd_resources[i].bst,
        pdev->pd_resources[i].bsh, size);
    return NULL;
}
pdev->pd_resources[i].mapped_size = size;
pdev->pd_resources[i].mapped = true;
```

The conditional branch deallocates exactly the bus mapping that succeeded and returns without publishing `mapped=true` or a nonzero `mapped_size`. The caller's AGP-borrowed alternative is no longer presented with a stale `mapped` flag **in this synthetic return scenario**. No AGP handle is unmapped by this branch. Nothing changes on the non-NULL fast path, where the metadata proceeds exactly as v3. No new global failure state or separate `0048` patch is needed for this narrow invariant.

## Source-only acceptance matrix

| Acceptance | Result |
|---|---|
| Existing v3 Git blob read, compared under exact CAS update | **PASS**, baseline `a62b6e05b01ec72246b88a24480ee47b6b217f5b` |
| Updated 0047 candidate GitHub write + byte-identical readback | **PASS**, v4 blob `76dd9732352dd1149b2899b1a771a9e01ebda5d5` |
| All seven unified diff hunk headers vs added/deleted/context line counts | **PASS, static diff-header check only** |
| Static exact inverse of changed excerpt | **PASS, bounded source text comparison only** |
| NetBSD x86 `bus_space_vaddr` memory-tag normal behavior | **SOURCE VERIFIED**, success normally usable KVA |
| Successful map + NULL KVA actually encountered on HP | **NOT_VERIFIED**, not a demonstrated target bug |
| Real scratch `git apply --check/apply/reverse` and native compiler | **NOT_RUN** (prior equivalent source execution restricted; no executor reroute) |
| i915 0045 sixteen negative source mutants | **NOT_RUN** under prior denial |
| NetBSD combined i915+DRM/TTM+RTL kernel, real KMS/WPA2, G01–G09 recovery | **NOT_VERIFIED** |

**Other open source risk, not silently corrected here:** frozen `linux_pci_dev_init()` uses `kmem_zalloc(..., KM_NOSLEEP)` for `pdev->bus` and immediately dereferences it without an allocation-failure check, but its API returns `void` and multiple DRM consumers need a coordinated error-propagation audit. No new candidate is authorized by this observation alone.

## Follow-on work

1. Trace actual `linux_pci_dev_init` call-site contracts, failure behavior and `linux_pci_dev_destroy` ordering before designing an explicit PCI-device initialisation repair. Verify whether `KM_NOSLEEP` allocation can be safely made fallible across all consumers, or whether a carefully scoped `KM_SLEEP` change is permitted by attach context. **Do not change this code without reviewing those caller paths**.
2. Review `pci_iomap` resource index handling, BAR types, owner identity, borrowed AGP fallback and non-x86/PCI override expectations; compile under an authorized NetBSD kernel build before treating v4 as integration-ready.
3. Original 0045 sixteen-mutant source regression and combined seven-candidate git apply remain NOT_RUN; a different connector/host may not be used to circumvent a provider-denied equivalent operation. No HP kernel install/boot until **independent** G01–G09 early console and verified standard-kernel rollback, then native combined i915+DRM/TTM+RTL build and physical KMS/WPA2 release acceptance. 300 Linux→NetBSD semantic units OPEN.

Governance canonical PRE/POST: `Agent-Governance/state/events/hp-i915-mmio-0047-v4-kva-null-unwind-20261020.jsonl`.
