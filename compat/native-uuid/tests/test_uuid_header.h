/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * UUID/GUID definition
 *
 * Copyright (C) 2010, 2016 Intel Corp.
 *	Huang Ying <ying.huang@intel.com>
 */
/*	$NetBSD: uuid.h,v 1.4 2021/12/19 11:38:04 riastradh Exp $	*/

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

#ifndef _LINUX_UUID_H_
#define _LINUX_UUID_H_


/* Frozen Linux byte-array ABI; native guid_bytes remains an alias. */
#define UUID_SIZE 16

typedef struct {
	union {
		unsigned char b[UUID_SIZE];
		unsigned char guid_bytes[UUID_SIZE];
	};
} guid_t;

typedef struct {
	unsigned char b[UUID_SIZE];
} netbsd_linux_uuid_t;

#define	GUID_INIT(x, y, z, v0, v1, v2, v3, v4, v5, v6, v7) ((guid_t)	      \
{									      \
	.guid_bytes = {							      \
		[0] = (x) & 0xff,					      \
		[1] = ((x) >> 8) & 0xff,				      \
		[2] = ((x) >> 16) & 0xff,				      \
		[3] = ((x) >> 24) & 0xff,				      \
		[4] = (y) & 0xff,					      \
		[5] = ((y) >> 8) & 0xff,				      \
		[6] = (z) & 0xff,					      \
		[7] = ((z) >> 8) & 0xff,				      \
		[8] = (v0),						      \
		[9] = (v1),						      \
		[10] = (v2),						      \
		[11] = (v3),						      \
		[12] = (v4),						      \
		[13] = (v5),						      \
		[14] = (v6),						      \
		[15] = (v7),						      \
	}								      \
})

#define UUID_INIT(a, b, c, d0, d1, d2, d3, d4, d5, d6, d7)			\
((netbsd_linux_uuid_t)								\
{{ ((a) >> 24) & 0xff, ((a) >> 16) & 0xff, ((a) >> 8) & 0xff, (a) & 0xff, \
   ((b) >> 8) & 0xff, (b) & 0xff,					\
   ((c) >> 8) & 0xff, (c) & 0xff,					\
   (d0), (d1), (d2), (d3), (d4), (d5), (d6), (d7) }})

#define	UUID_STRING_LEN		36

static inline bool __attribute__((__warn_unused_result__))
uuid_is_valid(const char *uuid)
{
	unsigned i;

	for (i = 0; i < 36; i++) {
		switch (i) {
		case 8:		/* xxxxxxxx[-]xxxx-xxxx-xxxx-xxxxxxxxxxxx */
		case 12 + 1:	/* xxxxxxxx-xxxx[-]xxxx-xxxx-xxxxxxxxxxxx */
		case 16 + 2:	/* xxxxxxxx-xxxx-xxxx[-]xxxx-xxxxxxxxxxxx */
		case 20 + 3:	/* xxxxxxxx-xxxx-xxxx-xxxx[-]xxxxxxxxxxxx */
			if (uuid[i] == '-')
				continue;
			return 0;
		default:
			if ('0' <= uuid[i] && uuid[i] <= '9')
				continue;
			if ('a' <= uuid[i] && uuid[i] <= 'f')
				continue;
			if ('A' <= uuid[i] && uuid[i] <= 'F')
				continue;
			return 0;
		}
	}

	return 1;
}

extern const guid_t guid_null;
extern const netbsd_linux_uuid_t netbsd_linux_uuid_null;

static inline bool guid_equal(const guid_t *u1, const guid_t *u2)
{
	return memcmp(u1, u2, sizeof(guid_t)) == 0;
}

static inline void guid_copy(guid_t *dst, const guid_t *src)
{
	memcpy(dst, src, sizeof(guid_t));
}

static inline void import_guid(guid_t *dst, const unsigned char *src)
{
	memcpy(dst, src, sizeof(guid_t));
}

static inline void export_guid(unsigned char *dst, const guid_t *src)
{
	memcpy(dst, src, sizeof(guid_t));
}

static inline bool guid_is_null(const guid_t *guid)
{
	return guid_equal(guid, &guid_null);
}

static inline bool netbsd_linux_uuid_equal(const netbsd_linux_uuid_t *u1, const netbsd_linux_uuid_t *u2)
{
	return memcmp(u1, u2, sizeof(netbsd_linux_uuid_t)) == 0;
}

static inline void netbsd_linux_uuid_copy(netbsd_linux_uuid_t *dst, const netbsd_linux_uuid_t *src)
{
	memcpy(dst, src, sizeof(netbsd_linux_uuid_t));
}

static inline void netbsd_linux_import_uuid(netbsd_linux_uuid_t *dst, const unsigned char *src)
{
	memcpy(dst, src, sizeof(netbsd_linux_uuid_t));
}

static inline void netbsd_linux_export_uuid(unsigned char *dst, const netbsd_linux_uuid_t *src)
{
	memcpy(dst, src, sizeof(netbsd_linux_uuid_t));
}

static inline bool netbsd_linux_uuid_is_null(const netbsd_linux_uuid_t *uuid)
{
	return netbsd_linux_uuid_equal(uuid, &netbsd_linux_uuid_null);
}

/* Generation requires thread/softint context; hard-IRQ parity is OPEN. */
void netbsd_linux_generate_random_uuid(unsigned char uuid[16]);
void generate_random_guid(unsigned char guid[16]);

extern void guid_gen(guid_t *u);
extern void netbsd_linux_uuid_gen(netbsd_linux_uuid_t *u);


extern const unsigned char guid_index[16];
extern const unsigned char netbsd_linux_uuid_index[16];

int guid_parse(const char *uuid, guid_t *u);
int netbsd_linux_uuid_parse(const char *uuid, netbsd_linux_uuid_t *u);


#endif  /* _LINUX_UUID_H_ */
