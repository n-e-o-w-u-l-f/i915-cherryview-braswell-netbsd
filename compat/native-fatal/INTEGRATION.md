# Real native fatal-only CV and signal wake policy

Patch0035 adds native fatal-only CV entry points and a real SOBJ_SIGKILL policy
to NetBSD sleepq. Four actual signal-post/stop wake sites respect that policy;
ordinary pending signals remain pending. SIGKILL and native exit/core predicates
feed Linux TASK_WAKEKILL. No process/LWP layout or signal mask is replaced.

The patch changes NetBSD core kernel sources. A module compiled with this patch
requires that new kernel backend; the running F77 recovery kernel cannot supply
these APIs. Native CV/sleepq/signal-post/group-exit/ptrace execution, cold/panic
sleep behavior, full kernel link, code-owner rundown and hardware remain OPEN.

The model executes staged Linux task/wait/variable-wait C and the actual native
fatal predicate/wake-filter bodies against explicit pthread/CV delegation.
Native object and relocatable-link checks compile the actual shared source and
headers without a candidate include override. They are bounded build evidence,
not native scheduler execution or full port acceptance.
