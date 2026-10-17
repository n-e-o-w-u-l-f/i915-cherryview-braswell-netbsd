/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * Isolated Cherryview IOSF transaction contract.
 * Pinned Linux VLV source-derived port/operation mapping. NetBSD kernel
 * integration requires proven sb_lock ownership and the existing
 * static vlv_sideband_rw() transport; this file performs NO MMIO.
 */
#ifndef _NB_I915_VLV_IOSF_TRANSACTION_H_
#define _NB_I915_VLV_IOSF_TRANSACTION_H_

#include <linux/types.h>
#include <sys/errno.h>
#include <stddef.h>

#include "nb_i915_vlv_iosf_unit_bridge.h"

#define NB_IOSF_SB_MRD_NP 0x00U
#define NB_IOSF_SB_MWR_NP 0x01U
#define NB_IOSF_SB_CRRDDA_NP 0x06U
#define NB_IOSF_SB_CRWRDA_NP 0x07U

struct nb_i915_vlv_iosf_route {
	u32 devfn;
	u32 port;
	u32 opcode;
};

typedef int (*nb_i915_vlv_iosf_transport)(void *ctx, u32 devfn,
    u32 port, u32 opcode, u32 addr, u32 *value);

static inline int
nb_i915_vlv_iosf_route(unsigned int unit, int write,
    struct nb_i915_vlv_iosf_route *out)
{
	struct nb_i915_vlv_iosf_route r = { 0U, 0U, 0U };
	if (out == NULL || (write != 0 && write != 1))
		return -EINVAL;

	/* Modern Linux unit_to_port(); GPIO intentionally has no port. */
	switch (unit) {
	case NB_I915_MOD_BUNIT: r.port = 0x03U; break;
	case NB_I915_MOD_CCK: r.port = 0x14U; break;
	case NB_I915_MOD_CCU: r.port = 0xa9U; break;
	case NB_I915_MOD_DPIO: r.port = 0x12U; break;
	case NB_I915_MOD_DPIO_2: r.port = 0x1aU; break;
	case NB_I915_MOD_FLISDSI: r.port = 0x1bU; break;
	case NB_I915_MOD_GPIO: return -EOPNOTSUPP;
	case NB_I915_MOD_NC: r.port = 0x11U; break;
	case NB_I915_MOD_PUNIT: r.port = 0x04U; break;
	default: return -EINVAL;
	}

	/* Linux DPIO_DEVFN and PCI_DEVFN(0,0) are both zero here. */
	r.devfn = 0U;
	if (unit == NB_I915_MOD_DPIO || unit == NB_I915_MOD_DPIO_2)
		r.opcode = write ? NB_IOSF_SB_MWR_NP : NB_IOSF_SB_MRD_NP;
	else
		r.opcode = write ? NB_IOSF_SB_CRWRDA_NP :
		    NB_IOSF_SB_CRRDDA_NP;

	*out = r;
	return 0;
}

/*
 * Caller MUST own the old NetBSD sb_lock, holding PUNIT acquisition
 * where necessary. held_units must reflect actual verified ownership,
 * not merely a fabricated bitset. This is NOT a replacement mutex.
 * Do not access HW when the old enum cannot express the unit.
 * Read results are only published after a successful transport.
 */
static inline int
nb_i915_vlv_iosf_transact(unsigned int unit, int write, u32 addr,
    u32 *value, unsigned long held_units,
    nb_i915_vlv_iosf_transport exchange, void *ctx)
{
	struct nb_i915_vlv_iosf_route route;
	unsigned int legacy;
	u32 val;
	int err;

	if (exchange == NULL || value == NULL || (write != 0 && write != 1))
		return -EINVAL;
	if (unit > NB_I915_MOD_PUNIT)
		return -EINVAL;
	err = nb_i915_vlv_iosf_legacy_unit(unit, &legacy);
	if (err != 0)
		return err; /* DPIO_2 fail-closed until lock owner is ported. */
	if ((held_units & (1UL << unit)) == 0)
		return -EPERM;
	err = nb_i915_vlv_iosf_route(unit, write, &route);
	if (err != 0)
		return err;

	val = write ? *value : 0;
	err = exchange(ctx, route.devfn, route.port, route.opcode, addr, &val);
	if (err == 0 && !write)
		*value = val;
	return err;
}
#endif /* _NB_I915_VLV_IOSF_TRANSACTION_H_ */
