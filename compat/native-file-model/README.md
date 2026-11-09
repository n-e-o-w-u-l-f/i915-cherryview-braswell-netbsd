# Production FILE / descriptor / poll lifetime model

This model compiles the unchanged `linux_file.c`, `linux_fd.c`, `linux_poll.c`
and actual FILE/ref/FD/poll headers. It delegates only the external Native
kernel/runtime boundaries. It does not replace production function bodies with
a second implementation. The exact added fd_get_linux_file helper is extracted
unchanged from Native0038 and its patch/helper hashes are recorded; mocking
that ordering would make its borrowed-descriptor test circular.

The eleven named cases exercise encoded file_ref values and saturation, 200
concurrent get/last-put races with exactly one final owner, exact EMPTY_FD on
invalid descriptors, reservation construction failure/abort/install, CLOEXEC,
shared-anon owner busy rejection before teardown,
owned Linux reference acquisition before the Native borrowed descriptor drops,
position unlock/reference balance, actual queued final put, driver release then
RCU grace then shell free then module release, zero-event native rescan after
poll registration, actual event bit translation, NOTE_SUBMIT exclusion of driver
callbacks and event_size, POLLFREE lifetime and allocation-error readiness.

The workqueue and RCU delegates are controlled explicitly. Last fput runs in a
model IRQ context and must neither allocate nor free. Running release work must
leave shell/module ownership held. A model RCU read-side section blocks callback
execution. RCU callback may only enqueue retirement; it cannot release the
module. Retirement frees the shell before module_rele and retains file_live
through that call. Fini returns EBUSY at each prior phase.

The borrowed-FD delegate can close the last Native container at fd_putfile. It
requires an independently owned Linux reference already exists. This makes
reordering the actual Native0038 callback behind the borrowed drop observable.
The invalid-FD controls require word==0, not just a masked NULL pointer, so the
prior CLONED_FD(NULL) bug is detectable. Native poll selnotify(events==0) records
a rescan and carries no fabricated readiness/error bits.

Six strict separate-process controls require SIGABRT and their exact production
reference/reservation/install diagnostic. NDEBUG cannot compile assertions out.
The runner executes only on unprivileged HP NetBSD11, accepts a fresh output,
records input/compiler/log hashes, and preserves failures.

Native task, inode, credential, page/commit/anon subsystems, allocation, locks,
specificdata, descriptor storage, RCU/workqueue scheduling and selinfo/knote are
explicit delegates. Their real Native ABI/runtime correctness is independent;
the model establishes only reached production FILE state/reference/callback
ordering under those stated contracts. It does not certify Native concurrent
FD-table internals, actual kernel RCU grace detection or GPU acceptance.
The fixture's supplied stack inode is an explicit delegate, not an object
created by the public admitted linux_inode_alloc constructor. The real standalone
inode admission/final-drain contract requires its separate source-bound proof.
