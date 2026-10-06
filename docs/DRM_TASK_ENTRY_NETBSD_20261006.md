# Native DRM ioctl task entry and modern file-adapter gate

Status: IN_PROGRESS. Both complete ports and subsequent physical HP WLAN
online remain the objective. No selected unit, modern DRM dependency or OS
owner is removed from scope. No kernel was linked, installed or booted.

Linux authority: `fd179f8a05be3ccae366b9b96e176b51fbe54aab`.
NetBSD authority: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

## Source change

Patch0037 follows immutable task/runtime0032 and native fatal backend0035.
Its generator verifies the exact prior task, header and frozen native DRM
file source. It changes three full source files: the common task runtime,
its real shared header and `drm_ioctl_shim` in native `drm_cdevsw.c`.
`compat/native-entry/expected-source.json` records before/after SHA256 and
the generated patch hash. The HP full-source preparation and regression
runners include this patch/test.

`linux_task_entry_enter` checks a NULL output handle at a sleepable boundary,
reserves admission before TLS lookup/allocation, and obtains exactly one
caller reference. An existing LWP task keeps its identity and gets a new
reference; a new task retains its allocation reference for this call and
adds a separate LWP owner reference. Reservation failure returns EBUSY;
softint allocation failure rolls back and returns ENOMEM before the driver.
No allocation is hidden inside `current`, a spinlock or a wait callback.

`linux_task_entry_leave` checks the same current LWP/TLS identity, clears the
caller's handle and drops its single entry reference. TLS identity stays
alive until actual LWP exit. It is not marked TASK_DEAD at each syscall:
selected Linux code retains task/PID/VM-related identity across calls.
Natural native TLS destruction drops the LWP owner, and external task
references retain the exited object until their sleepable last release.
Atomic module admission/quiescence still rejects teardown while any task
or external reference exists; this does not supply full code-owner rundown.

The native ioctl shim calls enter before either override or core dispatch,
handles admission/allocation errors before either path, and calls leave
for successful and failed returns before preserving native restart errno
translation. Other file boundaries, native/system workqueue workers,
attach/PM paths, completion/poll callbacks and close/error ownership remain
unimplemented. The ioctl patch targets the actual frozen native wrapper;
its modern full-source compilation remains blocked as recorded below.

## HP proofs

All38 pinned source/C regression scripts pass on HP, including the new
entry test. The immutable0032 runtime fixture is reconstructed only after
validating every actual0037/0035 file hash and reversing both exact patches
in a disposable tree. Its original complete-source hashes remain mandatory.
The fatal regression compiles the current0037 task source and validates
the same source chain; no historical hash check is skipped or weakened.

The entry fixture compiles the complete actual modified task source and the
exact modified native ioctl function against explicit delegated pthread,
specificdata, softint and bounded DRM callback models. Normal and UBSan
each pass13 scenarios/383 checks: override/core fallback, success/EIO/
restart, nested calls, persistent per-LWP identity, eight parallel LWPs,
allocation/reservation rollback, closed admission, natural LWP exit,
external reference retention and safe final quiescence. Compiled semantic
controls using the old shim or omitting leave fail the identity/reference
assertions. The fixture does not execute actual NetBSD scheduler/CV/poll,
kernel TLS destruction or device hardware.

The actual native `linux_task` and `linux_module` units compile with shared
headers and native -Werror flags. Ten real kernel/runtime/provider objects
(condvar, sleepq, signal, task, wait, wait-var, kthread, module, tasklet and
legacy bit-wait) compile and link with no unresolved newly owned fatal/
task/wait interfaces. This is a relocatable object link, not a kernel link.

The entire native `drm_cdevsw.c` is also compiled against the actual modern
full-source stage. It fails with42 compiler errors/29 distinct diagnostics.
The durable report retains FAILED for that three-unit build, including the
two successful units; the separate ten-unit runtime proof is PASSED.
No old DRM header, empty VM structure, fabricated field/provider, skipped
dependency or permissive warning flag replaces this whole-adapter gate.

The initial entry fixture compilation failed on misleading loop indentation;
real braces corrected it before successful normal/UBSan execution. The
first38-script attempt stopped at script16 because its historical task hash
still expected0035. Explicit reverse0037 ->0035 ->0032 verification repaired
that source-composition gate; the fresh full38-script run then passed.
The separate whole-adapter native compilation remains FAILED.

Exact statuses, object/log hashes, compiler diagnostics and model results:
[HP evidence](evidence/HP_NATIVE_DRM_TASK_ENTRY_20261006.json).

## Full modern DRM bridge still required

| Source mismatch observed by actual HP compiler | Required native owner/adapter |
| --- | --- |
| Native `drm_open/read/poll` signatures conflict with modern Linux declarations; minor-acquire arguments changed | Real Linux file/inode/minor identity backed by native fd/device ownership and source-derived publication/unwind |
| `ioctl_override` absent; modern `drm_ioctl` takes a user argument; driver table is const | Source-derived native kernel-data ioctl dispatch and permissions/copy/lifetime bridge |
| `open_count` is atomic, not an integer | Modern atomic open/last-close ownership and cleanup order |
| Modern `event_read_lock` is a mutex; old `event_read_wq` and native `event_selq` fields are absent | Modern event/read serialization plus real native select/kqueue callback registration and rundown |
| Modern callback wait heads do not match old native CV waits | Actual callback/task wake integration with correct IRQ/IPL and stack/heap lifetime |
| `mmap_object` absent; `vm_area_struct`, poll table and `__poll_t` need real APIs | Real UVM/VM, mmap, poll types and state producers; no placeholder VM/poll objects |
| Legacy `map_hash`/lock declarations and old core cleanup/init APIs diverge | Review the frozen profile and complete registration/remove/legacy routing without silently excluding selected paths |

MM/folio/UVM, PID/IO accounting, all selected410 sources, complete native
DRM registration and removal, workqueue/code-owner lifetime, full kernel
and physical KMS/PM/recovery remain OPEN. The running HP F77 cannot execute
the new fatal backend and no physical i915 acceptance is claimed.
