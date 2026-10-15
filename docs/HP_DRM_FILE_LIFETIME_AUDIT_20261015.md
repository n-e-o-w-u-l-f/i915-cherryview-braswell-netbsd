# HP DRM native open/close lifetime review — 2026-10-15

Status: SOURCE-CONTRACT REVIEW, not a validated panic fix. Target is the
HP Cherryview 8086:22b1 on NetBSD 11 amd64.

## Confirmed: native fd_clone() and its KASSERT

Exact frozen NetBSD/src at
`03d918f6d0e81fa05b8f1160eca0628ad39988a6`:
`sys/kern/kern_descrip.c` implements `fd_clone()` by filling and
affixing the opened file descriptor and returning `EMOVEFD`
unconditionally. Therefore the native
`compat/native-drm/drm_cdevsw.c:drm_native_open()` assertion
`KASSERT(error == EMOVEFD)` matches this native contract.
Treating this assertion as the blackscreen/panic cause without new
evidence would be incorrect; introducing a return/cleanup branch
after the successful `fd_affix` risks ownership corruption.

Confirmed source-only model on Legion: 3/3 positive/mutated cases.
No full pinned runner, HP ABI compiler, or hardware KMS test followed.
The model's first two attempted fixtures had testing-only mistakes
(regex escaping and truncated function input); these were diagnosed
and corrected before the passing model, and no failing candidate
was committed to the repository.

## Open P0: close/release LWP identity

Published native DRM `drm_native_close()` performs
`linux_file_fd_detach(file)`, then `fput(file)`, without a
`linux_task_entry_enter/leave` pair. Other native file entries
explicitly establish current LWP task identity.

Frozen Linux at
`fd179f8a05be3ccae366b9b96e176b51fbe54aab`:
`drm_release()` calls `drm_close_helper()`, which in turn calls
`drm_file_free()`; the latter references `current->comm` and
`task_pid_nr(current)`. This is a potential mismatch if the NetBSD
shim calls its `release` callback on a previously unentered LWP.

**Not yet proved:** Whether the actual staged NetBSD
`linux_file_fd_detach` or `fput` implementation supplies a task
context, or whether the close path crashes. The staged providers
must be inspected on HP. Adding a naive enter that returns early
on `ENOMEM` or `EBUSY` could leak a file that NetBSD has already
closed, making it an unsafe speculative fix.

## Next required evidence

Verify staged `linux_file.c` and `fput` release ownership, native
last-close semantics, module quiescence, and task/PID lifetimes.
Then implement guaranteed final close and exact fault-injection
tests on the HP's native ABI, only after reference semantics are
established. This concern is separate from the still-unlocalized
F83/F84 display-blackout boundary G04–G09. No new kernel boot or
register change may precede independent early-console/recovery
verification.
