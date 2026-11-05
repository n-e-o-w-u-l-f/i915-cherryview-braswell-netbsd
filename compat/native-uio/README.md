# Synchronous native I/O iterator source adapter

The actual selected `i915/gem/i915_gem_shmem.c:445` creates a synchronous `kiocb`,
sets its explicit offset, constructs an ITER_SOURCE user buffer and calls
`write_iter`. The callback must preserve negative errors and actual short writes;
the selected i915 consumer separately turns a successful short write into EIO.

This package owns `linux/uio_netbsd.h`, `linux/kiocb_netbsd.h` and `linux_uio.c`.
Only receipt-qualified Linux-owned `linux/uio.h` includes may be redirected to
this unique header. Native headers and the existing Native `struct uio` remain
unchanged. The structures are source adapters with explicit fields; no Linux
binary layout, Native iovec cast or folio/page-layout equivalence is asserted.

The provided iterator owners are UBUF and explicitly constructed kernel KVEC.
UBUF borrows the current Native vmspace only for the synchronous call and checks
that this owner still equals the executing process's vmspace. Address overflow,
user/kernel relabelling and wrong directions cannot copy or advance data.
User transfers call real Native copyin/copyout. Explicit kernel vectors are
validated with real Native kcopy, borrowed immutable until the call finishes,
and copied with kcopy. This covers kernel image/data, stacks and kmem without
guessing their allocation layout or treating a user pointer as kernel storage.

Native copyin/out/kcopy return errno rather than Linux's residual count. The
adapter tries bounded chunks; after an error it confirms the same chunk's prefix
byte by byte until the first fault. Only confirmed successful bytes advance
count and iterator position. Copies may touch a prefix before an error, as with
ordinary Linux raw usercopy; no MMIO/volatile-device-copy semantics are provided.
The borrowed kernel endpoint and vector storage must remain owned throughout.
No-fault/atomic iterator execution and async/page-pinning/BVEC/XARRAY/FOLIOQ
providers remain OPEN, and no constant-success substitutes are supplied.

Advance clamps to the remaining count. Revert checks the original owner bounds;
cross-vector restoration starts from the retained original array and handles
empty segments without moving before that array. Truncation/reexpansion cannot
grow beyond the original borrowed range. Full-copy helpers roll back iterator
progress on short copies, as the pinned source does; they do not undo memory
already copied. A callback updates `ki_pos` only after its backing store commits
the actual returned bytes. These copy helpers do not modify a file offset.

`init_sync_kiocb` clears all request fields, retains its caller-owned file pointer
and translates the actual current Native O_APPEND/O_DIRECT/O_DSYNC/O_SYNC flags
into pinned IOCB values. Native O_SYNC also guarantees data synchronization.
No stale cached Linux flag field is fabricated. `ki_complete == NULL` selects
synchronous behavior. `ki_ioprio == 0` means no explicit Linux priority override;
the owned Native backend keeps actual Native scheduling policy. Linux task
priority inheritance, asynchronous completion and unsupported IOCB policies
require separate real providers and cannot be inferred from these field values.

Primary frozen sources reviewed: Linux fd179f8 `include/linux/uio.h`,
`lib/iov_iter.c`, `include/linux/fs.h`, `include/uapi/linux/fs.h`,
`fs/read_write.c`, and the exact selected i915 shmem consumer; NetBSD03
`sys/sys/{uio,systm,fcntl}.h`, amd64 `vmparam.h`, and real
`sys/kern/subr_copy.c:103`. Native uiomove uses uio_vmspace and only advances
iovec/base/resid/offset after a successful copy; there is no uio_segflg field.
The adapter does not infer a nonexistent field. `uvm_kernacc` is not used as
an arbitrary kernel-buffer validator: its kernel_map-only policy is intended
for /dev/kmem and cannot stand in for actual fault-safe kernel copying.

`run_native_model.py` runs only on unprivileged HP NetBSD11 in a fresh output.
It compiles the actual C source against explicit memory/errno delegates, then
requires twelve named cases and six separate SIGABRT controls with their exact
diagnostics. NDEBUG does not remove assertions. Delegated user handles are
synthetic low addresses; kernel payloads have explicitly registered bounds and
permissions. Native C ABI, actual VM/copy fault behavior, FILE callback integration
and native shmem offset/residual proof remain independent gates. No build or
runtime result is claimed by this source package.
