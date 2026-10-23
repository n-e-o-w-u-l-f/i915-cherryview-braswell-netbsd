# Required native mapping integration

This is an implementation contract derived from the frozen Linux and NetBSD
sources, not an implemented VM provider or a completed acceptance gate. No
empty `vm_area_struct`, stack-only VMA, anonymous fallback, or constant-success
fault operation may stand in for the owners below.

Linux authority: `fd179f8a05be3ccae366b9b96e176b51fbe54aab`.
NetBSD authority: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

## Observed contracts

`i915_gem_mman.c:i915_gem_object_mmap` obtains a GEM reference during lookup,
selects CPU/GTT/cache protection and VM operations, and transfers its mapping
to the shared anonymous singleton with `vma_set_file`. It deliberately avoids
retaining the original DRM descriptor file: contexts, handles and requests
must still be released when that descriptor is closed. The singleton's
`f_mapping` is the device anonymous inode's `i_mapping` so mappings can later
be revoked. Its final release drops a device reference.

`vm_open`/`vm_close` retain/release the GEM object for each VMA. The initial
successful mmap already owns its lookup reference; the native bridge must not
call `vm_open` a second time for that initial reference. Clone and split
operations must balance new VMA references, including rollback on failure.

The CPU fault maps a whole VMA through `remap_io_sg`; the GTT fault can map a
range through `remap_io_mapping`. Both use actual `vm_start`, `vm_end`,
`vm_pgoff`, protection and mapping identity. A single synthetic page result
cannot stand in for those mapping operations or their later revocation.

NetBSD `sys_mmap` calls `fo_mmap` before selecting the final address. Its
`maxprot` argument is an uninitialized output parameter. The canonical DRM
adapter therefore assigns it rather than applying `&=` to it. PaX restrictions
are applied after the hook. UVM map entries, rather than the existing file
hook, own the final address interval and subsequent split/fork/protect changes.

NetBSD's special `pgo_fault` starts with map/AMAP/object locks held, must release
all of them itself, and must perform `pmap_update`. Linux driver fault
callbacks can take sleeping reservation locks, allocate, retry and install
several PTEs. They cannot be called directly while retaining those UVM locks.

Several existing native mmap error paths also fail to release the object
obtained from `fo_mmap`: PaX errors after the hook and early validation failures
inside `uvm_mmap`. The native source itself records this unresolved ownership
contract. A new file/VMA reference cannot safely be attached to those paths
without explicit transfer and cleanup.

## Required native core changes

1. **Mapping transaction and commit.** Extend the native mapping boundary so
   an owned preparation can validate offsets, length, descriptor permissions
   and requested protections before publication, then run the Linux mmap
   callback with the actual selected range and stable native VM-space
   identity. Every exit before publication must destroy the preparation.
   Every published interval must have exactly one map-entry owner. The Linux
   callback's replacement `vm_file`, resulting `vm_ops`, private data and
   maximum protections are part of that committed state.
2. **Map-entry lifecycle.** Add reviewed insert, fork/clone, split, protect,
   remove and VM-space destruction integration. Each resulting interval has
   correct adjusted offset, flags, MM identity and balanced GEM/file lifetime.
   Do not use `pgo_reference` as a substitute: it has no map-entry/range/MM
   argument and is also used for temporary address-hint references.
3. **Address-space registry and invalidation.** The inode-owned mapping tracks
   actual live intervals under a real lock. `unmap_mapping_range` and the i915
   GTT/CPU revocation paths remove applicable PTEs from every affected native
   pmap, synchronize translations, and exclude stale fault reinstallation.
   The registry must also survive descriptor passing and VM-space teardown.
4. **Fault transaction.** Retain the map-entry/mapping owner, capture interval
   and generation, release native locks in the required order, enter a real
   Linux task context, invoke the selected driver operation, and verify the
   entry/generation again before accepting any PTE changes. Correctly unwind
   allocation, unplug, protection and retry failures. `VM_FAULT_NOPAGE` is not
   evidence of a successful mapping when no PTE was installed.
5. **Mapping producers.** Implement the selected `remap_io_sg`,
   `remap_io_mapping`, PFN/page insertion and unmap functions against actual
   native pmap operations, with bounds, physical-page ownership, cache mode,
   encryption/protection translation and wired/page lifetime preserved. Do
   not manufacture anonymous RAM for a GTT/MMIO mapping.
6. **Backing storage and process MM.** Implement real shmem/page/folio/UVM
   backing for GEM and its `f_mapping`, plus the selected `vm_mmap` path and
   retained native process/MM identity. The old native `vm_mmap` returning
   `-ENODEV` cannot satisfy the selected legacy GEM mmap ioctl.

The ioctl kernel-buffer dispatcher is a separate source-owned component in
`compat/native-drm`. Its completion does not close any mapping item here.

## Required evidence

Native kernel-header compilation and complete symbol-owner/link evidence must
precede an experimental image claim. Mapping tests must exercise partial
unmap, fork, descriptor close before last mapping, singleton replacement,
protection reductions, address-hint retries, every post-preparation failure,
fault/unmap races, revocation/refault and device removal. A C model of buffer
or reference arithmetic is useful but cannot establish real UVM/PTE behavior.

Kernel installation, EFI/boot configuration changes and a physical boot remain
outside source/build acceptance and require the existing recovery prerequisites.
