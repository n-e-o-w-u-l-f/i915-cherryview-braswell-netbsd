/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Native atomic implementation of the frozen Linux file_ref contract.
 * Reference: Linux fd179f8a include/linux/file_ref.h and fs/file.c.
 * Native file storage is reclaimed only after an RCU grace period; it is
 * not reused while an active-reference lookup can still inspect its count.
 */
#ifndef _NB_LINUX_FILE_REF_NETBSD_H_
#define _NB_LINUX_FILE_REF_NETBSD_H_
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/systm.h>

#define FILE_REF_ONEREF 0UL
#define FILE_REF_MAXREF (ULONG_MAX >> 1)
#define FILE_REF_SATURATED ((ULONG_MAX >> 3) * 5UL + 5UL)
#define FILE_REF_RELEASED ((ULONG_MAX >> 2) * 3UL + 3UL)
#define FILE_REF_DEAD ((ULONG_MAX >> 3) * 7UL + 7UL)
#define FILE_REF_NOREF ULONG_MAX

typedef struct { volatile unsigned long refcnt; } file_ref_t;

static inline void
file_ref_init(file_ref_t *ref, unsigned long count)
{
	if (count == 0 || count - 1 > FILE_REF_MAXREF)
		panic("file_ref_init: invalid initial count");
	atomic_store_relaxed(&ref->refcnt, count - 1);
}

static inline bool
file_ref_get(file_ref_t *ref)
{
	unsigned long count = atomic_load_relaxed(&ref->refcnt), old;

	for (;;) {
		if (count >= FILE_REF_RELEASED) {
			membar_sync();
			return false;
		}
		if (count >= FILE_REF_MAXREF) {
			old = atomic_cas_ulong(&ref->refcnt, count,
			    FILE_REF_SATURATED);
			if (old == count) {
				membar_sync();
				return false;
			}
		} else {
			old = atomic_cas_ulong(&ref->refcnt, count, count + 1);
			if (old == count) {
				membar_sync();
				return true;
			}
		}
		count = old;
	}
}

static inline void
file_ref_inc(file_ref_t *ref)
{
	unsigned long count = atomic_load_relaxed(&ref->refcnt), old;

	for (;;) {
		if (count >= FILE_REF_RELEASED)
			panic("file_ref_inc: reference already released");
		old = atomic_cas_ulong(&ref->refcnt, count,
		    count >= FILE_REF_MAXREF ? FILE_REF_SATURATED : count + 1);
		if (old == count)
			return;
		count = old;
	}
}

static inline bool
file_ref_put(file_ref_t *ref)
{
	unsigned long count, old;

	membar_release();
	count = atomic_load_relaxed(&ref->refcnt);
	for (;;) {
		if (count >= FILE_REF_RELEASED)
			panic("file_ref_put: imbalanced file reference");
		if (count > FILE_REF_MAXREF)
			return false; /* Saturation deliberately prevents reclamation. */
		old = atomic_cas_ulong(&ref->refcnt, count,
		    count == FILE_REF_ONEREF ? FILE_REF_DEAD : count - 1);
		if (old == count) {
			if (count != FILE_REF_ONEREF)
				return false;
			membar_acquire();
			return true;
		}
		count = old;
	}
}

static inline bool file_ref_put_close(file_ref_t *ref) { return file_ref_put(ref); }
static inline unsigned long
file_ref_read(const file_ref_t *ref)
{
	unsigned long count = atomic_load_relaxed(&ref->refcnt);
	return count >= FILE_REF_RELEASED ? 0 : count + 1;
}
static inline unsigned long
__file_ref_read_raw(const file_ref_t *ref)
{
	return atomic_load_relaxed(&ref->refcnt);
}
#endif
