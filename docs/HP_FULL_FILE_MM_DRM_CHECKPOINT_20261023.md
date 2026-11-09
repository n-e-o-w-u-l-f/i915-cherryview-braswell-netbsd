# Full modern file/MM/DRM integration — unfinished checkpoint

The requested complete integration and new full kernel are **NOT COMPLETE**.
No new full kernel build has been run. Published active source remains9bd2679.

## Verified HP execution

- Independent read-only source baseline at Linuxfd179f8a was recovered from
  the existing root reference into a NEW owner-controlled shallow Git copy.
  No old tree was changed. The complete1266-file pinned DRM/i915 reference
  was materialized and hash-verified by the existing source tool on HP.
- Patch0038 extends actual pinned NetBSDfileops, sys_ioctl and descriptor
  lookup. A native callback obtains its owned Linux reference before the
  native descriptor borrow is released. The user-ioctl hook owns output,
  including output-on-error, and avoids generic double-copyout.
- The actual modified sys_generic.c and kern_descrip.c compiled on HP with
  configured native kernel flags, including Werror/nostdinc/_KERNEL, using
  the actual modified file.h/filedesc.h. They are152712/259616bytes, SHA256
  ca8140053475743028414745ee53d271dfdee18e62df0ecd80ae6d4e683f760f and
  087def4acc03cb5ce1b06827e2c4a90e4b19791972c4ec4541dd07924de1736c.
  [Actual ABI receipt](evidence/HP_NATIVE_FILEOPS_CORE_20261023.json).
  This is two-object ABI compilation, not callback runtime or full linking.

## Candidates preserved without acceptance

Explicit-path full-graph staging/namespace/API-import repairs and actual
ALLFILES/OBJS ownership checks were written. Agent-reported Python tests:
23 graph tests pass;17 path/provenance tests have2 Windows symlink skips.
These repairs were copied to HP but have NOT been executed there. There is
no new modern configured410 receipt or compiler graph result.

The canonical mmap candidate now assigns maxprot instead of reading its
uninitialized native input. A real DRM ioctl dispatcher factoring patch and
preallocated task-entry candidate are preserved. They are NOT natively
validated. The canonical adapter changed while the frozen replay digest
still guards the old source; do not bypass or arbitrarily update that guard.
Review the changed source and providers, then deliberately bind the new hash.

## Actual unfinished ownership

Modern anon_inode/shmem/address_space/file_ref lifetime, RCU-safe active
file acquisition, allocation-free deferred final release and code-owner
drain are not implemented. Native shmem takes uvm_object; modern GEM needs
a file/address_space. Mapping must support actual map-entry address/lifetime,
fork/split/unmap/protect/revocation and PTE/cache/fault semantics. Original
DRM files are replaced by an anonymous mmap singleton, so retaining only the
original descriptor is incorrect. UVM post-fo_mmap cleanup must release new
backing references on every failure; current core has early leak paths.
There are no placeholder types or success stubs closing these contracts.

## External boundary and safe state

Two code agents terminated with the actual platform response “You've hit
your usage limit”, offering upgrade/credits or retry at Oct29,2026 11:59PM
(timezone unspecified). No replacement agents/models/account/paid-service
route is used. This is a quota boundary, not a compiler failure. Existing
results and unfinished edits are retained for later verified continuation.

F77 is still running. Prior diagnostic kernel SHA256 remains
1aabcdee27654413382a1497e52e27b4ae4f4cd031ba478a47a233198fe4fbb4.
No install, boot.cfg/EFI/MMIO/radio changes or experimental boot occurred.
Materializer and native core ABI commands are terminal; no full build is
claimed to run in the background. A local WIP commit preserves all candidates
and does not publish them to the active source branch.
