# Native callback queues and common task candidate

Patch0032 integrates these assets with the selected worker in one native
runtime. It has not been installed or executed in a NetBSD kernel. All
compiler invocations and executable fixtures run on HP. Linux authority is
`fd179f8a05be3ccae366b9b96e176b51fbe54aab`; NetBSD authority is
`03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

The integrated admission extension reserves task lifetime before allocation
or native TLS access. `linux_task_system_quiesce` atomically closes admission
only when the count is zero; otherwise it returns EBUSY and keeps admission
open. The native module checks this before any destructive finalization.
`linux_task_system_fini` returns an error and preserves resources when busy;
the worker finalizer asserts its checked result. The source hashes below
describe the integrated, final-newline-normalized runtime. The isolated core
and admission proofs are retained separately in checkpoint evidence. These
changes do not supply external callback/code-owner rundown or arbitrary
driver entry attachment.

## Integrate these assets

| Candidate asset | Native integration location |
| --- | --- |
| `include/linux/task_netbsd.h` | `sys/external/bsd/drm2/include/linux/task_netbsd.h` |
| `include/linux/sched.h` | Replace `sys/external/bsd/drm2/include/linux/sched.h` |
| `include/linux/wait.h` | Replace `sys/external/bsd/drm2/include/linux/wait.h` |
| `include/linux/wait_bit.h` | Replace `sys/external/bsd/drm2/include/linux/wait_bit.h` |
| `linux_task.c` | Add `sys/external/bsd/drm2/linux/linux_task.c` |
| `linux_wait.c` | Add `sys/external/bsd/drm2/linux/linux_wait.c` |
| `linux_wait_var.c` | Add `sys/external/bsd/drm2/linux/linux_wait_var.c` |
| `completion-wait-include.patch` | Add the real wait dependency to native common completion |

Register all three new C units in the native DRM Linux module source lists and build manifest. Combine the worker agent's final `linux_kthread.c` and `linux/kthread.h` with this single task runtime. Do not retain a second private `struct task_struct`, TLS key, `current=curproc`, or the old inline `schedule_timeout_uninterruptible`. The common header supplies opaque `lt_kthread` storage protected by `lt_lock`; the worker supplies `linux_kthread_wake_locked` and `linux_kthread_wake`. The runtime calls the locked helper without entering the private kthread mutex or native sleep mutex.

The completion include is required by the pinned Linux completion→swait→wait include chain. Native completion remains its independently owned mutex/CV implementation. This small patch supplies the transitive wait types; it does not claim completion scheduling, FIFO, IO, or signal parity.

Root's native raw spinlock patch0024 and real list/container headers are required. Keep Linux callback entry/head field names and callback signatures intact. The selected custom i915 callbacks use those fields directly.

## Initialization and native entry ownership

The worker's `linux_kthread_init/fini` delegates to `linux_task_system_init/fini`. Call this once. Initialize `linux_wait_var_init` once during common Linux module startup before driver queues become accessible; add matching error unwind and `linux_wait_var_fini` after variable callbacks and owners are drained. The existing native `linux_wait_bit_init/fini` is a different legacy bit CV table and remains separate. It does not initialize the new keyed variable table.

Every non-kthread native LWP entering selected Linux code must call `linux_task_enter_current` at a sleepable boundary before any use of `current`, `DEFINE_WAIT`, task state, or spin/queue interlock. Handle its NULL result as allocation failure. It may allocate both task storage and native specificdata; it is deliberately not hidden inside `current`. Native workqueue callbacks and DRM ioctl/file/thread boundaries still need source-owner integration. Hardware callbacks carrying a queued wait entry wake its saved task pointer and never attach a new task.

`linux_task_alloc` returns one caller reference. `linux_task_attach_current` adds one LWP reference and publishes specificdata at a sleepable point. Native LWP exit clears the task's borrowed LWP identity under `lt_lock`, then drops its owner reference before LWP reclamation. A kthread handle retains the initial reference until native MUSTJOIN has finished and the worker has cleared `lt_kthread`. `linux_task_lwp` returns a borrowed pointer requiring a caller-owned native lifetime guard. The last `put_task_struct` must be sleepable because native `softint_disestablish` drains all CPUs before freeing the task. Arbitrary interrupt-context last-put parity is open.

Do not unload this runtime with any attached user LWP, native worker, external task handle, queued custom callback, or variable queue entry alive. `linux_task_system_busy` remains an observation. The integrated atomic admission gate rejects task creation after quiescence, and the module returns EBUSY before teardown when task owners remain. External callback/code-owner rundown and workqueue finalization order still require integration before unload acceptance.

## Queue and scheduling invariants

Linux wait.c preserves priority/head insertion, ordinary nonexclusive head insertion, exclusive tail insertion, callback order, exact key forwarding, negative callback termination, and exclusive wake budgets. Wake budget uses the flags captured before invoking a callback; a custom callback may remove and free its own entry. `finish_wait` always acquires the queue lock before unlinking, synchronizing stack lifetime with callbacks. Waiter state is published under the task raw lock and includes a full store/load barrier.

A callback changes a matching sleeping task to TASK_RUNNING under the raw IPL_HIGH task lock, then schedules its MPSAFE notifier. The notifier takes the native IPL_VM sleep mutex and signals the task CV. The waiter checks task state while holding that same sleep mutex; native CV enqueue occurs before releasing it. Thus a wake before the waiter checks is observed in state, and a later notifier cannot pass the sleep mutex until the waiter has enqueued. No raw callback takes the sleep mutex. A leftover notifier can cause a spurious wake, which the state/condition loop rechecks.

Variable queues use 256 real generic callback heads, the frozen Linux pointer-width hash constants, and exact address plus bit-index keys. `wake_up_var` supplies bit index -1. Bucket collisions do not wake ordinary waiters for a different address. The selected i915_active heap callback has its own idle predicate and may free itself while returning zero; the core traversal supports that lifetime. The new table does not alias the native legacy bit CV table.

Finite scheduler timeouts retain a signed native-width long budget across INT_MAX/2 CV slices, subtract elapsed ticks using unsigned tick-wrap arithmetic, and preserve MAX_SCHEDULE_TIMEOUT as an untimed sentinel. Condition rechecks retain Linux's zero-timeout→1 success and condition/signal race behavior. TASK_INTERRUPTIBLE uses real native catchable CV waits; TASK_UNINTERRUPTIBLE uses native noncatchable waits. The exact pinned GuC `must_wait_woken` helper is compiled in the fixture because it intentionally ignores stop during its wait; the generic `wait_woken` helper still honors kthread stop/park.

## FIFO lock audit

The task owner/lifetime lock is a native raw spin mutex at IPL_HIGH. Native `lwp_lock` follows the mutable LWP lock pointer and acquires a spin mutex; current/on-processor and runnable LWP locks are `spc_lwplock` and `spc_mutex`, allocated at IPL_SCHED in pinned `kern_runq.c:147,165`. The generic native mutex path uses `splraiseipl`; the amd64 spin fast path takes the greater of the current and requested IPL. Both keep the outer saved IPL until the spin nesting count returns to zero. Acquiring an IPL_SCHED mutex while holding the IPL_HIGH task lock does not lower IPL or block adaptively.

`linux_sched_set_fifo` holds task raw→LWP lock while changing class and native priority. `lwp_changepri` delegates to the LWP sync object's native scheduler/turnstile/sleepq priority implementation. Those native implementations do not invoke Linux task callbacks or acquire the common task lock. Native `lwp_exit` runs `lwp_thread_cleanup`, which releases p_lock, then invokes `lwp_finispecific` while still sleepable and before LWP reclamation; the common TLS owner destructor therefore does not take task raw while holding the native LWP/runqueue lock. The reviewed worker publishes task state without its raw queue lock and uses sleep/private-kthread→task raw→worker raw, with no worker raw→task edge.

This is a structural audit of the frozen paths, not a native LOCKDEBUG/SMP runtime result. Native scheduler policy/accounting equivalence, future sync object changes, and full interrupt-priority coverage remain acceptance work.

## Reproduce on HP only

Put the candidate at `/root/hp-driver-port-20261005/agent-native-wait`, preserving its final `include/linux` headers, and the worker candidate include prefix at `/root/hp-driver-port-20261005/agent-native-worker/include`. The generator uses git show against the fixed Linux pin, so sparse physical files are not required.

```sh
python3 generate_wait.py
python3 generate_wait_var.py
python3 build_native.py
python3 run_tests.py
python3 audit_wait.py
```

`build_native.py` asserts the HP hostname and derives the actual native kernel compiler command from `native-math64-drm_buddy.log`. It runs in the shared object directory only to consume existing generated headers and writes source/object/log/status files solely in the isolated candidate directory. `run_tests.py` asserts HP, compiles the actual candidate sources and extracted pinned GuC helper against the bounded pthread delegation model, and executes them with finite deadlines. The model delegates the native primitives and cannot prove actual NetBSD CV/sleepq, softint, signal, IPL, or LWP lifecycle execution.

The final proof contains native -Werror compile exit 0 for linux_task, linux_wait, linux_wait_var, and the header/macro probe; fixture compile/run exit 0; 10000 wake-versus-schedule races; deterministic callback/exclusive/key/order/negative tests; prepare/finish, before-schedule wake, GuC woken barriers, wide/tick-wrap and zero/deadline timeouts; signal/condition races; keyed hash collision/bit filtering; callback self-free; task/notifier reference drain and allocation failure. The worker agent separately reported its native combined ld -r link with this unchanged task/wait core and no unresolved shared Linux interfaces. Root must rerun integration checks with all three queue/runtime units plus the final worker.

The lexical source audit covers exactly 410 selected C units, 44 containing relevant identifiers. It recursively reads 1719 necessary headers, with 172 identifier-bearing headers and 1005 unresolved generated/architecture include paths. It strips comments and strings but is not a preprocessor/configuration/callgraph proof. These numbers do not count old or nonselected native DRM drivers as selected work.

## Explicit remaining gates

* **Fatal-only signal sleeps:** selected i915_active calls `wait_var_event_killable`. TASK_WAKEKILL scheduling currently asserts that a real fatal-only native backend is required. `cv_wait_sig` catches all deliverable signals and is not substituted. Native group-exit, cancellation/core semantics and races are unproved; signal-mask changes are not used.
* **Generic task attachment and lifecycle:** driver/workqueue boundaries, module admission/drain, native kernel runtime and arbitrary-context last-put remain open. Per-task native softint allocation can fail and is propagated; scalability is unproved.
* **Static queue initialization:** native kmutex has no public constant initializer. The header deliberately names an unresolved diagnostic token for file-scope static heads. Selected dynamic heads are supported; header/configuration paths requiring static heads remain open.
* **Bit lock/IO/full timeout owner port:** the legacy native bit functions remain their own ABI. They are not presented as full Linux bit wait or lock parity. Keyed variable waits are the implemented subset.
* **VM/mm, PID namespace, IO accounting and scheduling hints:** current->mm requires a real VM source owner; native process identity is not Linux thread/namespace parity; IO waits use the real task wait but IO accounting and sync/current-CPU migration hints remain open.
* **Poll/RCU lifetime:** callback keys and pinned poll-free bits are preserved; actual native poll registration, poll_table/__poll_t adaptation, RCU/free owners and full interrupt-priority runtime proof remain open.

No kernel build/install, boot change, reboot, commit, or external publication was performed by this candidate owner.
