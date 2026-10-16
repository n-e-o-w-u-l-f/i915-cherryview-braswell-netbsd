/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * NetBSD LinuxKPI direct-polling adapter for the pinned i915 port.
 *
 * Reconstructed from the observable Linux polling API contract. This is an
 * isolated, non-installed candidate. The actual NetBSD compiler, link and
 * runtime contracts must be verified on the HP target before integration.
 */
#ifndef _LINUX_IOPOLL_H_
#define _LINUX_IOPOLL_H_

#include <sys/errno.h>
#include <sys/types.h>

#include <asm/processor.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/ktime.h>
#include <linux/time.h>
#include <linux/types.h>

/*
 * A zero timeout polls until success. For a nonzero timeout, the test is
 * performed before every operation, but the final operation/condition still
 * gets to win if the deadline has just expired.
 *
 * Use monotonic elapsed unsigned nanoseconds. This avoids the signed
 * overflow in ktime_add_us() for a very large caller timeout and works
 * with NetBSD's ktime_t (int64_t ns), which has no ktime_compare() helper.
 * A timeout too large to represent in ns is saturated, not wrapped.
 */
#define __nb_poll_ns_budget(us)						\
	((uint64_t)(us) > UINT64_MAX / NSEC_PER_USEC ?		\
	    UINT64_MAX : (uint64_t)(us) * NSEC_PER_USEC)

#define poll_timeout_us(op, cond, sleep_us, timeout_us, before)		\
({									\
	const uint64_t __nb_limit_us = (uint64_t)(timeout_us);		\
	const unsigned long __nb_pause_us = (unsigned long)(sleep_us);	\
	const uint64_t __nb_limit_ns = __nb_poll_ns_budget(__nb_limit_us); \
	const uint64_t __nb_start_ns = (uint64_t)ktime_get();		\
	int __nb_result = -ETIMEDOUT;					\
	might_sleep_if(__nb_pause_us != 0);				\
	if ((before) && __nb_pause_us != 0)				\
		usleep_range((__nb_pause_us >> 2) + 1, __nb_pause_us);	\
	for (;;) {							\
		const bool __nb_expired = __nb_limit_us != 0 &&		\
		    ((uint64_t)ktime_get() - __nb_start_ns) > __nb_limit_ns; \
		barrier();						\
		op;							\
		if (cond) {						\
			__nb_result = 0;				\
			break;						\
		}							\
		if (__nb_expired)					\
			break;						\
		if (__nb_pause_us != 0)				\
			usleep_range((__nb_pause_us >> 2) + 1,	\
			    __nb_pause_us);				\
		cpu_relax();						\
	}								\
	__nb_result;							\
})

/*
 * NetBSD's udelay(unsigned int) is narrower than Linux's polling delay
 * (unsigned long). Bound each busy-wait to 1ms to preserve elapsed duration
 * without silent LP64 truncation or a huge single DELAY() request.
 */
static inline void
__nb_iopoll_udelay(unsigned long usec)
{
	while (usec != 0) {
		unsigned int slice = usec > 1000UL ? 1000U : (unsigned int)usec;
		udelay(slice);
		usec -= slice;
	}
}

/*
 * Atomic variant: no clock queries (also works while timekeeping is
 * suspended). Count the requested delay in nanoseconds and charge one
 * nanosecond per CPU-relax iteration, as in the Linux API.
 *
 * Use a saturating unsigned budget plus a separate expiration bit rather
 * than signed subtraction, so a huge timeout or delay cannot overflow into
 * an immediate success/failure or loop indefinitely due to underflow.
 * NetBSD's udelay() takes unsigned int; the helper splits wider
 * unsigned-long delays into bounded 1ms segments.
 */
#define poll_timeout_us_atomic(op, cond, delay_us, timeout_us, before)	\
({									\
	const uint64_t __nb_limit_us = (uint64_t)(timeout_us);		\
	const unsigned long __nb_pause_us = (unsigned long)(delay_us);	\
	const uint64_t __nb_pause_ns = __nb_poll_ns_budget(__nb_pause_us); \
	uint64_t __nb_remain_ns = __nb_poll_ns_budget(__nb_limit_us); \
	bool __nb_overrun = false;					\
	int __nb_result = -ETIMEDOUT;					\
	if ((before) && __nb_pause_us != 0) {			\
		__nb_iopoll_udelay(__nb_pause_us);		\
		if (__nb_limit_us != 0) {			\
			__nb_overrun = __nb_pause_ns > __nb_remain_ns; \
			__nb_remain_ns = __nb_overrun ? 0 :	\
			    __nb_remain_ns - __nb_pause_ns;	\
		}							\
	}								\
	for (;;) {							\
		const bool __nb_expired = __nb_limit_us != 0 && __nb_overrun; \
		barrier();						\
		op;							\
		if (cond) {						\
			__nb_result = 0;				\
			break;						\
		}							\
		if (__nb_expired)					\
			break;						\
		if (__nb_pause_us != 0) {			\
			__nb_iopoll_udelay(__nb_pause_us);		\
			if (__nb_limit_us != 0) {		\
				__nb_overrun = __nb_pause_ns > __nb_remain_ns; \
				__nb_remain_ns = __nb_overrun ? 0 : \
				    __nb_remain_ns - __nb_pause_ns; \
			}						\
		}							\
		cpu_relax();						\
		if (__nb_limit_us != 0) {			\
			if (__nb_remain_ns == 0)			\
				__nb_overrun = true;		\
			else						\
				__nb_remain_ns--;		\
		}							\
	}								\
	__nb_result;							\
})

/* The accessor is evaluated once per iteration; val holds the last sample. */
#define read_poll_timeout(op, val, cond, sleep, limit, before, ...)	\
	poll_timeout_us((val) = op(__VA_ARGS__), cond, sleep, limit, before)

#define read_poll_timeout_atomic(op, val, cond, delay, limit, before, ...) \
	poll_timeout_us_atomic((val) = op(__VA_ARGS__), cond, delay, limit, before)

#define readx_poll_timeout(op, addr, val, cond, sleep, limit)	\
	read_poll_timeout(op, val, cond, sleep, limit, false, addr)

#define readx_poll_timeout_atomic(op, addr, val, cond, delay, limit) \
	read_poll_timeout_atomic(op, val, cond, delay, limit, false, addr)

#define readb_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readb, addr, val, cond, delay, limit)
#define readb_poll_timeout_atomic(addr, val, cond, delay, limit)	\
	readx_poll_timeout_atomic(readb, addr, val, cond, delay, limit)
#define readw_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readw, addr, val, cond, delay, limit)
#define readw_poll_timeout_atomic(addr, val, cond, delay, limit)	\
	readx_poll_timeout_atomic(readw, addr, val, cond, delay, limit)
#define readl_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readl, addr, val, cond, delay, limit)
#define readl_poll_timeout_atomic(addr, val, cond, delay, limit)	\
	readx_poll_timeout_atomic(readl, addr, val, cond, delay, limit)
#define readq_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readq, addr, val, cond, delay, limit)
#define readq_poll_timeout_atomic(addr, val, cond, delay, limit)	\
	readx_poll_timeout_atomic(readq, addr, val, cond, delay, limit)

#define readb_relaxed_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readb_relaxed, addr, val, cond, delay, limit)
#define readb_relaxed_poll_timeout_atomic(addr, val, cond, delay, limit) \
	readx_poll_timeout_atomic(readb_relaxed, addr, val, cond, delay, limit)
#define readw_relaxed_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readw_relaxed, addr, val, cond, delay, limit)
#define readw_relaxed_poll_timeout_atomic(addr, val, cond, delay, limit) \
	readx_poll_timeout_atomic(readw_relaxed, addr, val, cond, delay, limit)
#define readl_relaxed_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readl_relaxed, addr, val, cond, delay, limit)
#define readl_relaxed_poll_timeout_atomic(addr, val, cond, delay, limit) \
	readx_poll_timeout_atomic(readl_relaxed, addr, val, cond, delay, limit)
#define readq_relaxed_poll_timeout(addr, val, cond, delay, limit)	\
	readx_poll_timeout(readq_relaxed, addr, val, cond, delay, limit)
#define readq_relaxed_poll_timeout_atomic(addr, val, cond, delay, limit) \
	readx_poll_timeout_atomic(readq_relaxed, addr, val, cond, delay, limit)

#endif /* _LINUX_IOPOLL_H_ */
