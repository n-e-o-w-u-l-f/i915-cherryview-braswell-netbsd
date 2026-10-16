/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * Cherryview / Valleyview Linux->NetBSD IOSF unit number boundary.
 *
 * Standalone, source-only candidate: translates the modern Linux
 * enum vlv_iosf_sb_unit and lock-mask representation to the eight
 * entries of frozen NetBSD intel_sideband.h. No direct MMIO here.
 *
 * Never cast the enum or pass BIT(modern_unit) to older NetBSD:
 * Linux inserted DPIO_2 at index 4, shifting four later units.
 * DPIO_2 has no known NetBSD legacy unit and is rejected.
 */
#ifndef _NB_I915_VLV_IOSF_UNIT_BRIDGE_H_
#define _NB_I915_VLV_IOSF_UNIT_BRIDGE_H_

#include <sys/errno.h>

/* Snapshot of the pinned Linux enum, NOT included with NetBSD's old enum. */
enum nb_i915_vlv_modern_unit {
	NB_I915_MOD_BUNIT = 0,
	NB_I915_MOD_CCK = 1,
	NB_I915_MOD_CCU = 2,
	NB_I915_MOD_DPIO = 3,
	NB_I915_MOD_DPIO_2 = 4,
	NB_I915_MOD_FLISDSI = 5,
	NB_I915_MOD_GPIO = 6,
	NB_I915_MOD_NC = 7,
	NB_I915_MOD_PUNIT = 8,
};

/* Snapshot of the NetBSD 03d918f6 intel_sideband.h enum. */
enum nb_i915_vlv_legacy_unit {
	NB_I915_LEG_BUNIT = 0,
	NB_I915_LEG_CCK = 1,
	NB_I915_LEG_CCU = 2,
	NB_I915_LEG_DPIO = 3,
	NB_I915_LEG_FLISDSI = 4,
	NB_I915_LEG_GPIO = 5,
	NB_I915_LEG_NC = 6,
	NB_I915_LEG_PUNIT = 7,
};

static inline int
nb_i915_vlv_iosf_legacy_unit(unsigned int modern, unsigned int *legacy)
{
	unsigned int result;
	if (legacy == 0)
		return -EINVAL;

	switch (modern) {
	case NB_I915_MOD_BUNIT:
		result = NB_I915_LEG_BUNIT;
		break;
	case NB_I915_MOD_CCK:
		result = NB_I915_LEG_CCK;
		break;
	case NB_I915_MOD_CCU:
		result = NB_I915_LEG_CCU;
		break;
	case NB_I915_MOD_DPIO:
		result = NB_I915_LEG_DPIO;
		break;
	case NB_I915_MOD_DPIO_2:
		return -EOPNOTSUPP;
	case NB_I915_MOD_FLISDSI:
		result = NB_I915_LEG_FLISDSI;
		break;
	case NB_I915_MOD_GPIO:
		result = NB_I915_LEG_GPIO;
		break;
	case NB_I915_MOD_NC:
		result = NB_I915_LEG_NC;
		break;
	case NB_I915_MOD_PUNIT:
		result = NB_I915_LEG_PUNIT;
		break;
	default:
		return -EINVAL;
	}

	*legacy = result;
	return 0;
}

/*
 * Translate get/put lock masks before interacting with the older
 * vlv_iosf_sb_get/put(struct drm_i915_private *, old_bitmask).
 * Return an error without changing the output on unsupported input.
 * This does not translate read/write unit identifiers into IOSF ports
 * and does not implement error propagation or IRQ/preemption handling.
 */
static inline int
nb_i915_vlv_iosf_legacy_mask(unsigned long modern, unsigned long *legacy)
{
	const unsigned long valid = (1UL << (NB_I915_MOD_PUNIT + 1)) - 1UL;
	unsigned long converted = 0;
	unsigned int index, target;
	int error;

	if (legacy == 0 || (modern & ~valid) != 0)
		return -EINVAL;

	for (index = NB_I915_MOD_BUNIT; index <= NB_I915_MOD_PUNIT;
	    index++) {
		if ((modern & (1UL << index)) == 0)
			continue;
		error = nb_i915_vlv_iosf_legacy_unit(index, &target);
		if (error != 0)
			return error;
		converted |= 1UL << target;
	}

	*legacy = converted;
	return 0;
}
#endif /* _NB_I915_VLV_IOSF_UNIT_BRIDGE_H_ */
