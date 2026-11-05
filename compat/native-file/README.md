# Native FILE/page owner

This directory is source for the isolated modern DRM/i915 adapter. It is not
installed by placing global LinuxKPI headers ahead of the Native headers.
Imported Linux-owned includes/tags are explicitly redirected; Native struct
file, struct page, pgoff_t, UVM pager class and allocation layout remain Native.

Reference pins:

* NetBSD: 03d918f6d0e81fa05b8f1160eca0628ad39988a6
* Linux: fd179f8a05be3ccae366b9b96e176b51fbe54aab

## Actual owners

* linux_file.c owns encoded atomic references, a preallocated real task-entry
  spare per file, callback-module pin, native credential, inode, poll owner,
  final-release work, RCU grace period, and a separate native shell-retirement
  worker. Arbitrary release/module_rele never run in the global RCU GC thread.
  The live charge remains until module_rele returns.
* linux_fd.c reserves the actual native file and FD slot before void fd_install.
  fd_affix transfers the Linux reference without allocation. fd_get_linux_file
  must use the actual optional native fileops callback while the native file
  is borrowed. Dup/fork retain native file_t ownership normally.
* linux_poll.c installs actual Linux callback wait entries and Native selinfo
  registrations. Knotes own file references. NOTE_SUBMIT only uses cached hints;
  it cannot call the driver under a driver's event/wait locks. Process rescans
  query real readiness. Native and Linux write-event bits are translated.
* linux_inode.c owns a real UAO object and a native mapping registry. Its GFP
  policy controls actual future UAO allocation freelists. Existing pages are
  not falsely described as migrated by changing a policy mask.
* linux_page.c owns real native page wires and UAO references through a sidecar.
  Native struct page storage is never enlarged or cast to a Linux folio.
  Last put only enqueues embedded work; sleepable Native unwire/detach/free
  runs later. The real linux_folio handle currently represents one base page.
* linux_shmem.c uses real UAO-backed files and actual copy/uio/page providers.
  Write iterators copy through a private bounce buffer; only confirmed bytes
  reach the page, ki_pos and i_size. Read/write progress survives later errors.
* linux_shmem_commit.c owns a conservative NetBSD component admission budget
  for non-NORESERVE files, including grow, failed-write rollback, shrink and
  destruction. It samples Native free RAM/free swap and preserves kernel/pager
  headroom. This is not global Linux vm_committed_as, preallocated physical
  pages, reserved swap slots, or protection against later system-wide pressure.

The injected native_aobj_grow.inc supplies same-object UAO growth and a locked
future-allocation freelist policy. It keeps Native pgoff_t. Public size guards
match the actual Native int page-index limit. Root must compose it into the
exact pinned Native uvm_aobj.c and add actual public Native declarations.

## Required lifecycle composition

Common initialization must create the task/RCU runtime before
linux_file_system_init. That function creates the file/page queues, native FD
reservation owner, commit ledger and shared anonymous inode. A live file,
construction, FD reservation or page sidecar prevents admission teardown.

Common finalization must call linux_file_system_fini before ordinary task
quiesce and RCU teardown. It first refuses live charges, then quiesces its
retained native file worker and joins it. The actual task-notifier backend
must drain the retained LWP's deferred last put before destroying its key.
No queue drain is performed while holding a lock needed by release or
module_rele. Native loaded driver callback code needs a real owner; built-in
THIS_MODULE=0 is not a loadable-module pin.

## Explicit remaining gates

Source existence is not component/kernel compile, link, native semantic
validation, boot acceptance, or successful GPU runtime.

* Nondefault Linux shmem mounts have no fabricated vfsmount owner. The audited
  current native profile leaves CONFIG_TRANSPARENT_HUGEPAGE undefined.
* Mapped/native-mlock discard needs the actual per-entry Native revocation
  owner. Current unmapped range discard preflights every page and refuses
  busy, loaned or unowned wires before changing page data. Detached pinned
  pages retain their physical bytes until the true final native put.
* Partial-byte hole edges prepare actual cached/swapped edge pages, then zero
  only the requested bytes after full-page preflight; holes need no allocation.
  Native semantic validation is still required. The selected whole-object
  purge must propagate real failure
  before marking MADV_PURGED. i915-shmem-native-owner.patch binds this and
  Native UAO clean/deactivate to the frozen selected source.
* Universal logical EOF checks belong before Native COW/amap/pager fault
  lookup. No UAO-only check is claimed to cover existing private COW pages.
* Modern scatterlist, higher-order/pinned-user pages, allocator folio handles,
  local highmem maps and TTM writeback/reclaim require their actual owners.
  A base-page handle must never silently stand in for a higher-order extent.
* Generic read_iter/write_iter definitions do not assert asynchronous Linux
  I/O, direct I/O, atomic I/O, Linux I/O priority, LRU or xarray layout parity.

