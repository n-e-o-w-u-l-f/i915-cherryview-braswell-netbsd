/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * Copyright (c) 2026 n-e-o-w-u-l-f
 * All rights reserved.
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
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
 * TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 * EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
 * OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
 * OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
 * ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#ifdef NATIVE_DRM_INODE_TEST
#include "native_drm_inode_model.h"
#else
#include <sys/param.h>
#include <sys/types.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/stat.h>
#include <sys/systm.h>
#endif

#include "native_drm_inode.h"

struct native_drm_inode {
	volatile unsigned int refcount;
	dev_t rdev;
	ino_t ino;
	mode_t mode;
};

int
native_drm_inode_create(dev_t rdev, ino_t ino, mode_t mode,
    struct native_drm_inode **out)
{
	struct native_drm_inode *inode;

	if (out == NULL)
		return EINVAL;
	*out = NULL;
	if ((mode & S_IFMT) != S_IFCHR)
		return EINVAL;
	ASSERT_SLEEPABLE();
	inode = kmem_zalloc(sizeof(*inode), KM_NOSLEEP);
	if (inode == NULL)
		return ENOMEM;
	/* The allocation is private until the caller publishes the result. */
	inode->refcount = 1;
	inode->rdev = rdev;
	inode->ino = ino;
	inode->mode = mode;
	*out = inode;
	return 0;
}

bool
native_drm_inode_tryget(struct native_drm_inode *inode)
{
	unsigned int count, observed;

	if (inode == NULL)
		return false;
	count = atomic_load_relaxed(&inode->refcount);
	for (;;) {
		if (count == 0 || count == UINT_MAX)
			return false;
		observed = atomic_cas_uint(&inode->refcount, count, count + 1);
		if (observed == count) {
			membar_acquire();
			return true;
		}
		count = observed;
	}
}

void
native_drm_inode_put(struct native_drm_inode *inode)
{
	unsigned int count, observed;

	if (inode == NULL)
		panic("native_drm_inode_put: NULL inode");
	/* Publish prior owner accesses before surrendering this reference. */
	membar_release();
	count = atomic_load_relaxed(&inode->refcount);
	for (;;) {
		/* This must remain fatal when diagnostic assertions are disabled. */
		if (count == 0)
			panic("native_drm_inode_put: zero reference count (underflow)");
		observed = atomic_cas_uint(&inode->refcount, count, count - 1);
		if (observed == count)
			break;
		count = observed;
	}
	if (count != 1)
		return;
	/* Match native kref release ordering before reclaiming the allocation. */
	membar_acquire();
	ASSERT_SLEEPABLE();
	kmem_free(inode, sizeof(*inode));
}

dev_t
native_drm_inode_rdev(const struct native_drm_inode *inode)
{
	KASSERT(inode != NULL);
	return inode->rdev;
}

ino_t
native_drm_inode_ino(const struct native_drm_inode *inode)
{
	KASSERT(inode != NULL);
	return inode->ino;
}

mode_t
native_drm_inode_mode(const struct native_drm_inode *inode)
{
	KASSERT(inode != NULL);
	return inode->mode;
}
