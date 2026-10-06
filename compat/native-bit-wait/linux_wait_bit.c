/*	$NetBSD: linux_wait_bit.c,v 1.5 2021/12/19 12:36:09 riastradh Exp $	*/

/*-
 * Copyright (c) 2018 The NetBSD Foundation, Inc.
 * All rights reserved.
 *
 * This code is derived from software contributed to The NetBSD Foundation
 * by Taylor R. Campbell.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE NETBSD FOUNDATION, INC. AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
 * TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE FOUNDATION OR CONTRIBUTORS
 * BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD: linux_wait_bit.c,v 1.5 2021/12/19 12:36:09 riastradh Exp $");

#include <sys/param.h>
#include <sys/types.h>
#include <sys/bitops.h>
#include <sys/condvar.h>
#include <sys/mutex.h>
#include <sys/systm.h>

#include <linux/bitops.h>
#include <linux/sched.h>
#include <linux/wait_bit.h>

static struct {
	struct waitbitentry {
		kmutex_t	lock;
		kcondvar_t	cv;
	}		ent;
	char		pad[CACHE_LINE_SIZE - sizeof(struct waitbitentry)];
} waitbittab[PAGE_SIZE/CACHE_LINE_SIZE] __cacheline_aligned;
CTASSERT(sizeof(waitbittab) == PAGE_SIZE);
CTASSERT(sizeof(waitbittab[0]) == CACHE_LINE_SIZE);

int
linux_wait_bit_init(void)
{
	size_t i;

	for (i = 0; i < __arraycount(waitbittab); i++) {
		mutex_init(&waitbittab[i].ent.lock, MUTEX_DEFAULT, IPL_VM);
		cv_init(&waitbittab[i].ent.cv, "waitbit");
	}

	return 0;
}

void
linux_wait_bit_fini(void)
{
	size_t i;

	for (i = 0; i < __arraycount(waitbittab); i++) {
		cv_destroy(&waitbittab[i].ent.cv);
		mutex_destroy(&waitbittab[i].ent.lock);
	}
}

static inline size_t
wait_bit_hash(const volatile unsigned long *bitmap, unsigned bit)
{
	/* Try to avoid cache line collisions.  */
	const volatile unsigned long *word = bitmap + bit/(NBBY*sizeof(*word));

	return ((uintptr_t)word >> ilog2(CACHE_LINE_SIZE)) %
	    __arraycount(waitbittab);
}

static struct waitbitentry *
wait_bit_enter(const volatile unsigned long *bitmap, unsigned bit)
{
	struct waitbitentry *wbe = &waitbittab[wait_bit_hash(bitmap, bit)].ent;

	mutex_enter(&wbe->lock);

	return wbe;
}

static void
wait_bit_exit(struct waitbitentry *wbe)
{

	mutex_exit(&wbe->lock);
}

/*
 * Native CV delegation for the frozen Linux ordinary/fatal task-state policy.
 * Zero ticks denotes the unbounded API, never an expired timed wait.
 */
static int
wait_bit_sleep(struct waitbitentry *wbe, int flags, int ticks)
{
	if (flags & TASK_INTERRUPTIBLE)
		return ticks ? cv_timedwait_sig(&wbe->cv, &wbe->lock, ticks) :
		    cv_wait_sig(&wbe->cv, &wbe->lock);
	if (flags & TASK_WAKEKILL)
		return ticks ? cv_timedwait_sig_fatal(&wbe->cv, &wbe->lock,
		    ticks) : cv_wait_sig_fatal(&wbe->cv, &wbe->lock);
	if (ticks)
		return cv_timedwait(&wbe->cv, &wbe->lock, ticks);
	cv_wait(&wbe->cv, &wbe->lock);
	return 0;
}

/* A successful clear-bit observation has the Linux ACQUIRE contract. */
static bool
wait_bit_test_acquire(const volatile unsigned long *bitmap, unsigned bit)
{
	bool set = test_bit(bit, bitmap) != 0;

	if (!set)
		membar_acquire();
	return set;
}

/*
 * Publish preceding writes before clearing the flag, and order the clear
 * before waking waiters. The shared bucket lock prevents a missed CV wake.
 */
void
clear_and_wake_up_bit(int bit, volatile unsigned long *bitmap)
{
	struct waitbitentry *wbe;

	wbe = wait_bit_enter(bitmap, bit);
	clear_bit_unlock(bit, bitmap);
	smp_mb__after_atomic();
	cv_broadcast(&wbe->cv);
	wait_bit_exit(wbe);
}

/*
 * Linux return contract: zero on clear, -EINTR for a mode-permitted signal.
 * TASK_KILLABLE must choose the real fatal-only backend despite containing
 * TASK_UNINTERRUPTIBLE. Ordinary signals remain pending and do not end it.
 */
int
wait_on_bit(const volatile unsigned long *bitmap, unsigned bit, int flags)
{
	struct waitbitentry *wbe;
	int error, ret = 0;

	if (!wait_bit_test_acquire(bitmap, bit))
		return 0;
	wbe = wait_bit_enter(bitmap, bit);
	while (wait_bit_test_acquire(bitmap, bit)) {
		error = wait_bit_sleep(wbe, flags, 0);
		if (error) {
			KASSERTMSG(error == EINTR || error == ERESTART,
			    "error=%d", error);
			ret = -EINTR;
			break;
		}
	}
	/* A new owner may set the bit again after our successful observation. */
	wait_bit_exit(wbe);
	return ret;
}

/*
 * Zero on clear, -EINTR on a mode-permitted signal, -EAGAIN on expiry.
 * A native CV slice expiry is not expiry of a wider Linux timeout budget.
 * Each native slice fits within the signed tick counter's half range, so
 * unsigned end-start subtraction remains correct across native tick wrap.
 */
int
wait_on_bit_timeout(const volatile unsigned long *bitmap, unsigned bit,
    int flags, unsigned long timeout)
{
	struct waitbitentry *wbe;
	int error, ret = 0;

	if (!wait_bit_test_acquire(bitmap, bit))
		return 0;
	wbe = wait_bit_enter(bitmap, bit);
	while (wait_bit_test_acquire(bitmap, bit)) {
		unsigned starttime, endtime;
		int slice;

		if (timeout == 0) {
			ret = -EAGAIN;
			break;
		}
		slice = MIN(timeout, INT_MAX/2);
		starttime = getticks();
		error = wait_bit_sleep(wbe, flags, slice);
		endtime = getticks();
		timeout -= MIN(timeout, (endtime - starttime));

		if (error == EINTR || error == ERESTART) {
			ret = -EINTR;
			break;
		}
		KASSERTMSG(error == 0 || error == EWOULDBLOCK,
		    "error=%d", error);
		/* Recheck the bit and full remaining budget after every CV wake. */
	}
	wait_bit_exit(wbe);
	return ret;
}
