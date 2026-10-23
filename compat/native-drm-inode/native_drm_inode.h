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

#ifndef _NATIVE_DRM_INODE_H_
#define _NATIVE_DRM_INODE_H_

#include <sys/types.h>

/*
 * A native character-device identity and its allocation/reference owner.
 * This is not a Linux VFS inode, vnode, address_space or mapping provider.
 * Identity is immutable after creation. No driver callbacks are invoked.
 */
struct native_drm_inode;

/*
 * create is sleepable and returns one owned reference on success. The mode
 * must describe a character device; permission bits are retained unchanged.
 * For a non-NULL out argument, *out is NULL on every error. Errors are native
 * errno values, not Linux ERR_PTR values. The caller owns publication.
 */
int native_drm_inode_create(dev_t, ino_t, mode_t, struct native_drm_inode **);

/*
 * tryget requires an existing reference or independent protection of the
 * allocation's lifetime. It does not make an unprotected pointer safe and
 * cannot resurrect a zero count or increment UINT_MAX. Success acquires one
 * additional reference; failure changes neither count nor ownership.
 */
bool native_drm_inode_tryget(struct native_drm_inode *);

/*
 * Drop exactly one owned reference. Last put is sleepable and frees the
 * allocation. NULL and a zero count are unconditional programmer errors.
 * Neither native nor Linux file/descriptor/close ownership is implied.
 */
void native_drm_inode_put(struct native_drm_inode *);

/* Accessors require a live owned reference (or independent lifetime guard). */
dev_t native_drm_inode_rdev(const struct native_drm_inode *);
ino_t native_drm_inode_ino(const struct native_drm_inode *);
mode_t native_drm_inode_mode(const struct native_drm_inode *);

#endif /* _NATIVE_DRM_INODE_H_ */
