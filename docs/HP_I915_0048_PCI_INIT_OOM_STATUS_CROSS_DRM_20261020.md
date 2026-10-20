# HP-I915 — Candidate 0048: NetBSD DRM PCI initialization OOM propagation across all callers

Date: 2026-10-20 (Europe/Berlin)  
Status: **UNINTEGRATED SOURCE PATCH, PINNED STATIC CHECKS PASS, NATIVE TESTS NOT_RUN**  
Development branch: `work/hp-native-drm-stage-replay-20261015`.  
Pre-step HEAD: `4209d912158bf0eb423cd85233f6f3af9d17a3ee`.  
Candidate patch commit: `c430c38ec6d418e8e81652d854b23ca36c41f088`.  
Pinned NetBSD: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

## Actual source defect and scope

The frozen [`linux_pci.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/linux/linux_pci.c) blob `52be483d5d3410d7e2955c2c59704ee4a80b2c9b`, `linux_pci_dev_init` at ~145–211, allocates `pdev->bus = kmem_zalloc(sizeof(*pdev->bus), KM_NOSLEEP)` and immediately dereferences `pdev->bus->pb_pc` without checking NULL. `linux_pci_dev_destroy` at ~995 dereferences `pdev->bus->self` before testing `pdev->bus != NULL`. This is a **source-proven conditional error-path defect** if the nonsleep allocation fails, not an observed HP out-of-memory condition.

The common API's return type is `void` in frozen [`include/linux/pci.h`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/include/linux/pci.h) blob `b7c8182891979230b00be3d43f70a77712f2adec`; a caller cannot currently distinguish a successful initialization from allocation failure. The project also uses `linux_pci_dev_init` from two `linux_pci.c` discovery helpers.

## Exactly what standalone candidate 0048 changes

[**Candidate 0048 patch**](../candidates/0048-netbsd11-drm-linux-pci-dev-init-oom-propagation.patch), Git blob `b84011509a49d889893977a237be9edca17977cf`:

1. Change the NetBSD-local `linux_pci_dev_init` prototype and implementation from `void` to `int`.
2. Keep `KM_NOSLEEP`; if the bus allocation is NULL, return `ENOMEM` **before dereferencing the pointer**, and return 0 when initialization completes. Include NetBSD errno definitions.
3. `linux_pci_dev_destroy` checks that `pdev->bus` is non-NULL before dereferencing `bus->self`, allowing teardown of a descriptor whose bus allocation failed. Existing ROM/resource cleanup semantics remain otherwise unchanged.
4. Seven DRM frontend calls in six files handle a nonzero status. Attach routines log the error and return without starting a workqueue or scheduling `config_mountroot`; Nouveau's probe/match path returns match score 0 instead of continuing with a half-initialized stack descriptor.
5. `pci_get_domain_bus_and_slot` and `pci_get_class` handle initialization failure by freeing their just-allocated `struct pci_dev` and returning NULL; `pci_get_class` still releases `from` on the shared `out:` path.

The **nine direct invocation sites** are source-pinned:

| Caller / location | Frozen Git blob | Failure handling staged |
|---|---|---|
| i915 `i915_pci_autoconf.c:148` | `9798385b02f247c08db9b16624d5ddc9d11a8ca5` | Attach log and return |
| amdgpu `amdgpu_pci.c:140` | `267ebec239968897ea45f23eafd76d8d4ba5761d` | Attach log and return |
| radeon `radeon_pci.c:193` | `9610b65b82a72dafee89c90e3824409db34bb3cd` | Attach log and return |
| nouveau `nouveau_pci.c:134,159` | `c8479ce5653e589d5dde9f8818feecb729960ca6` | Match score 0; attach log and return |
| vmwgfx `vmwgfx_pci.c:146` | `6c7bc7e077cd87e44edb4f7cf4b550b821f2f75c` | Attach log and return |
| via `via_pci.c:129` | `4093e9e1c4012665b7538dbf7941616418635ab0` | Attach log and return |
| `linux_pci.c:606,662` | `52be483d5d3410d7e2955c2c59704ee4a80b2c9b` | Free temporary pdev, return NULL |

### Match/attach sleepability boundary remains open

The pinned [`sys/kern/subr_autoconf.c`](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/subr_autoconf.c) blob `5ee8a7998b07fd570d7b1f67d23cdb814de63039`, `config_match` ~1053–1069, explicitly requires `KERNEL_LOCKED_P()` before invoking `ca_match`. This check is **not by itself a formal permission to sleep**. The existing `alloc_fake_parent_device` has a conditional `KM_SLEEP` on a PPB path, but that inherited behavior is not proof all match contexts are sleep-safe. Hence 0048 does **not** casually replace `KM_NOSLEEP` with `KM_SLEEP` or modify the PPB helper's allocation policy.

### Candidate interoperability with 0047 v4

Existing [0047 v4](../candidates/0047-netbsd11-i915-pci-mmio-mapping-size-and-agp-borrow-owner.patch), blob `76dd9732352dd1149b2899b1a771a9e01ebda5d5`, separately fixes BAR mapping/unmapping/AGP ownership and NULL KVA handling. Both 0047 and 0048 touch the same `linux_pci.c` but address different contracts. A literal old-hunk range inspection found **one overlapping original context** near `linux_pci.c:204–213` (resource initialization vs insertion of final `return 0`). **This is not proof of a semantic conflict, nor of successful combined textual application**. A composed candidate must reconcile both modifications in one function against the common NetBSD pin. `git apply --check`, apply/reverse, compiler and fault injection have **NOT_RUN**; avoid claiming that both patches apply as-is or silently promoting either.

## Static authorship and checks

- Eight files, 15 original-version unified diff hunks. Every replacement used a unique **complete-line** anchor in the exact frozen source file.
- Static full-file forward substitution and byte-identical inverse both passed for the eight files. An independent readback parse verified **all 15** diff headers' old/new line counts, old source hunks and new-position deltas against original pinned files.
- GitHub published the 0048 patch and it was fetched byte-for-byte at blob `b84011509a49d889893977a237be9edca17977cf`.
- **Two source-generator attempts rejected malformed literal anchors before any repository write:** first a multi-line selection ended inside a declaration; then a caller selection excluded its leading indentation. Failure fingerprint `DIFF-INCOMPLETE-LINE-ANCHOR`. Prevention is whole-line matching and independent hunk/header and source validation before publishing. Third corrected attempt created the patch. No partial 0048 patch was left from the two rejected checks.

## Required genuine acceptance (none executed)

1. Test `KM_NOSLEEP` bus allocation failure via a sanctioned native NetBSD mock/fault injection. Confirm `ENOMEM`, no dereference, no leaked `pdev` or fake parent and `pci_get_class` releases `from`.
2. Verify that a frontend whose attach routine returns early is safe under NetBSD `config_detach` and `pmf_device_deregister`, especially uninitialized `SIMPLEQ` fields and workqueues. Merely observing a `return` is **not** equivalent to a fully accepted detach life cycle.
3. Native compile ABI after `linux_pci_dev_init` prototype return change for i915, amdgpu, radeon, nouveau, vmwgfx, via and both helper callers.
4. Resolve the `0047` original-header overlap and check candidate composition under genuinely allowed execution, not by rerouting earlier provider-denied i915 executable source regression tests.
5. Require G01–G09 independent early console and proven standard-kernel rollback before installing or testing any combined HP i915/DRM/TTM+RTL kernel. Physical KMS and RTL WPA2 remain separate acceptance requirements.

**No operative driver C or HP kernel/bootloader/hardware changed.** Candidate 0048 is standalone and **UNINTEGRATED**, joining 0013/0014/0043/0044/0045/0046/0047; 300 Linux→NetBSD semantic rows remain OPEN. 0045's 16 previously denied negative-source mutations remain AUTHORED NOT_RUN; no equivalent reroute. Canonical PRE/POST: `Agent-Governance/state/events/hp-i915-pci-init-oom-status-0048-20261020.jsonl`.
