/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _LINUX_MM_ABI_TYPES_NETBSD_H_
#define _LINUX_MM_ABI_TYPES_NETBSD_H_
/* Linux fd179f8a page offsets are unsigned long.  The native NetBSD pgoff_t
 * is a signed voff_t and deliberately retains its separate system ABI.
 */
typedef unsigned long linux_pgoff_t;
#endif
