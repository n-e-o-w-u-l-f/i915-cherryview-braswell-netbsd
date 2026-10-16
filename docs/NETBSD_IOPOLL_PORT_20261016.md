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

## 2026-10-16 signed-width regression / CHV integration gate

**PRE:** In the first isolated candidate, both atomic delay paths performed
`udelay((unsigned int)__nb_pause_us)`, although Linux's API accepts
`unsigned long`. The frozen NetBSD `linux/delay.h` declares
`udelay(unsigned int)`. LP64 arguments greater than `UINT_MAX` therefore
silently truncate (for `UINT_MAX+1`, to zero), breaking the requested
delay/countdown correspondence. The original 14 C tests did not cover it.

**PATCH:** `__nb_iopoll_udelay(unsigned long)` now splits atomic busy-waits
into at most 1000us per native `udelay` call. Both pre-first-read and
per-iteration delays use it, maintaining the full `unsigned long`
parameter duration. Small sub-1ms CHV/CDCLK delays remain a single
native call. The intent is correctness of this adapter, not to endorse
multi-second busy polling in any production call site.

**POST:** Existing 14 host-C mock cases and two new edge-case checks
(`2501us` three segments; LP64 `UINT_MAX+1` no narrowing) PASSED
before commit on Legion. The long-delay test reuses the published existing
C fixture and instruments `udelay` arguments. These synthetic tests do not
prove NetBSD native DELAY timing, real kernel ABI, physical i915/KMS,
safe scheduling or fairness. Native build/integration only on HP after
recovery and G01-G09 trace prerequisites are met.
