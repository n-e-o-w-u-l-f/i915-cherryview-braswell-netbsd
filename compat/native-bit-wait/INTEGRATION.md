# Existing native bit wait policy

Patch0036 corrects the actual shared NetBSD linux_wait_bit.c provider. It binds
TASK_WAKEKILL to the real patch0035 fatal CV backend, returns the frozen Linux
zero-on-success result, keeps the full unsigned timeout budget across bounded
native CV slices and native tick wrap, and supplies release/clear/wake and
successful-observation acquire ordering. The actual bucket lock still closes
the check/sleep versus clear/broadcast missed-wakeup window. Post-success bit
assertions are removed because a new owner can legitimately acquire the bit.

Production uses the real NetBSD mutex/CV/atomic/barrier providers. An installed
new core kernel is required for fatal CV support; F77 is not a provider.
The HP-only model executes the complete actual staged C through explicit
pthread/CV and virtual-time declarations, not native sleepq execution. Native
shared-source compilation/link and model source-dependency proof are separate.

The existing native ABI is retained. This does not implement Linux keyed
wake_bit_function/bit_waitqueue, custom action/lock/IO APIs, native IO accounting,
full init/fini admission or code-owner drain, native scheduler/signal/timeout
execution, full410 or a kernel link. Those gates remain OPEN.
