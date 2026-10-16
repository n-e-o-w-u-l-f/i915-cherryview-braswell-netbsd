# NetBSD LinuxKPI iopoll — candidate adapter, 2026-10-16

**State:** isolated BSD-2-Clause source candidate with 14 host-C mock
regressions PASS. NOT integrated into the kernel, and not a validated
physical Cherryview/Braswell KMS driver.

## Exact pinned reference

Linux: torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab,
include/linux/iopoll.h (GPL-2.0-only; this file is not copied).
NetBSD: NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6,
sys/external/bsd/drm2/include/linux/ktime.h and delay.h, and
sys/external/bsd/drm2/include/asm/processor.h.

The 323-unit source dependency audit identifies 19 i915 translation
units directly including linux/iopoll.h, which is not present in the
frozen NetBSD drm2/common include roots. The pinned reference uses
poll_timeout_us in display/intel_cdclk.c for VLV/CHV clock readiness;
the 50 ms limit and 500 us delay are real call-site arguments.

## Reconstructed contract

A zero timeout does not expire. For a finite timeout, each iteration
checks expiration BEFORE sampling, then evaluates the operation and
condition; a successful final sample wins over an expired deadline.
Return 0 on condition true, -ETIMEDOUT if expired and still false.
`read_poll_timeout` and `readx_poll_timeout` save each sampled value.

This NetBSD implementation uses ktime_get() (monotonic nanoseconds).
It does not call the unavailable ktime_compare(). Elapsed unsigned
nanoseconds and saturated timeout multiplication avoid signed deadline
overflow on huge timeouts. The atomic variant does not invoke timekeeping
and uses a saturated countdown for requested delays and one ns per
relax iteration, matching the finite-budget ordering.

The native LinuxKPI delay.h maps usleep_range() onto NetBSD DELAY():
THIS IS A BUSY WAIT rather than Linux's may-sleep timer semantics.
The candidate preserves this backend contract explicitly; full
sleeping-latency/IRQ/WLAN fairness parity remains OPEN. The atomic
variant expects an unsigned-int-representable delay because NetBSD
udelay(unsigned int) is narrower than Linux's macro argument.
Any giant parameter must be audited before broad production use.

## Source-only regression and integration boundary

Source: compat/native-runtime/iopoll/include/linux/iopoll.h
Test: tests/test_i915_netbsd_iopoll_contract.py

The test builds a synthetic userspace executable with stubbed monotonic
time, delays and MMIO readers, and verifies 14 cases on Legion,
including zero/finite timeout, final success after expiry, both
atomic/non-atomic variants, optional pre-delay, accessor sample storage,
and huge finite deadline. It is NOT a NetBSD kernel build and does
not prove real PCI MMIO, DP/DPIO/PLL, interrupt safety or panic freedom.

Proposed HP-only integration destination:
sys/external/bsd/drm2/include/linux/iopoll.h

Before applying on HP: reconcile exact include ownership and DRM
build manifests; test compiler -Werror and real CHV display call sites;
audit NetBSD DELAY busy-wait impact; perform full DRM/TTM/323-unit
compile/link and stable independent early-console recovery gate.
Do not turn this source-only candidate into an F83/F84 kernel boot.
