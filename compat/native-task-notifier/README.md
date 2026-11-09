# Native task notifier candidate

This additive package targets the exact composed 0032 + 0035 + 0037 task C
(`375113319b162867a34263bb8fa642f5e4e1d09a71d9329e9d82e6ed5a9b8a1c`)
and task header
(`e6aca23639d618eb2f49b808c856ac55b0b0d9954406964b18e63f5d4cd5df0b`).
`generate.py` reconstructs and verifies those bytes, then emits a separate patch,
complete resulting sources, and before/after hashes into a new output directory.
Windows CRLF is normalized to canonical Git LF; no other input drift is admitted.
Old patches and immutable runtime source assets remain unchanged.

The implementation uses the actual pinned NetBSD non-per-CPU workqueue API:

* `sys/sys/workqueue.h` SHA256
  `ea7bcfc7e639d0a170411f951c66966cef9b33cd9d13422411f19eaac76284da`.
* `sys/kern/subr_workqueue.c` SHA256
  `f1a9860d7f08e736523b5c41883bc923e18e4376d1d7306951cf8e51531f1b8a`.

One MPSAFE queue, with an IPL_HIGH producer interlock, is created fallibly before
external task admission opens. Failed creation deletes the native specificdata
key and destroys the task-system lock. Task construction then uses KM_SLEEP,
an embedded work item, and initialized locks/CV; there is no per-task notifier
allocation or failure after the reservation is held.

## Lifetime argument

`lt_lock` protects reference count, notification pending/running ownership and
the repeated-wake flag. Producers publish TASK_RUNNING before scheduling. Only
the queue callback takes `lt_sleep_lock`, before `lt_lock`, matching the waiter.
It signals while holding the sleep interlock. Repeated wakes while queued are
coalesced; a wake during a callback forces its recheck before pending ownership
is cleared. A producer arriving after that clear may reenqueue the running work;
the native single worker caches list-next before callback and cannot execute two
callbacks concurrently. After the clear/unlock the old callback never dereferences
the task again.

Last put reaches zero under `lt_lock` and schedules this same embedded work. It
does not allocate, sleep or free in the producer's IRQ/RCU context. A pending or
running notify observes zero before returning its lifetime ownership, destroys
locks/CV and frees the exact task size in worker context. It releases the task
system reservation only after destruction. The callback never dereferences a
freed task; the actual native worker also does not dereference a work item after
invoking it. The workqueue code itself remains owned until queue destruction joins
the worker.

`linux_task_alloc_owner_wait(parent_spare)` requires a caller-held, exclusively
unattached, never-exited parent spare, serialized by the caller's object/VMA
lock. The parent already pins the key and queue. It adds an internal reservation
even while external admission is closed, checks count overflow, and performs
KM_SLEEP child construction without reopening admission. The parent remains
unconsumed. This is appropriate for native fork/split owners with infallible
callbacks; it does not permit a new unrelated external owner during teardown.

`linux_task_system_fini` retains its zero-reservation requirement. OPEN plus live
owners returns EBUSY without closing admission. An already QUIESCED runtime may
drain a real barrier work before rechecking zero, so a joined retained LWP's last
put can finish. It never succeeds with a remaining child/parent reservation.
Teardown is externally serialized and sleepable; barrier waits and queue join
must run outside kernconfig/module/code-owner locks needed by worker or owner
rundown. Actual owner-lock integration remains an independent native gate.
Busy observation now includes queued task destruction, explicitly extending
resource ownership through real teardown.

## Validation boundary

`tests/test_native_task_notifier_source.py` checks exact composition and negative
source-admission controls without compiling. `run_native_model.py` refuses any
execution host except unprivileged HP NetBSD11 and refuses an existing output.
It compiles the actual generated task C plus the actual file subsystem's
preallocated-entry/retained-quiesce snippets against explicit pthread delegates.
The model caches work-list next before callbacks, permits running work requeue,
rejects duplicate pending work and tracks exact allocation/free sizes.

The eight named cases cover init failure unwind, one queue for many tasks,
IRQ last-put deferred ownership, queued/running wake coalescing, final put during
notification, closed-admission internal clones, retained-LWP entry/exit/fini and
the real task wait condition under the delegated CV. Six separate processes must
abort with their exact parent/overflow/underflow diagnostics. Assertions remain
enabled even with NDEBUG supplied. All source/model/compiler/log hashes and failed
outputs are retained. No native C result is asserted by this source package.

Useful semantic mutants are removal of the pending guard (duplicate enqueue),
removal of the repeated-wake recheck, omission of final scheduling/free, wrong
free size, reopening external admission and replacing internal owner cloning with
ordinary fallible allocation. The original strict fatal controls only certify
the specified diagnostic and SIGABRT, never an arbitrary process failure.

This userland model does not establish native kernel ABI, IRQ execution, UVM
callback locking, actual specificdata/workqueue/sleepq behavior or module unload
acceptance. Native compilation of the real composed owner and its consumers is
required separately. Full kernel, installation, boot and physical GPU acceptance
remain OPEN.
