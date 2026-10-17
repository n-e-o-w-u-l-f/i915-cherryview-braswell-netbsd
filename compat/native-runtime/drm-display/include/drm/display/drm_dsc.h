/* SPDX-License-Identifier: MIT */
/*
 * NetBSD DRM2 compatibility for Linux i915's DSC layout definitions.
 * Verified against pinned:
 *   Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab
 *   NetBSD 03d918f6d0e81fa05b8f1160eca0628ad39988a6
 *
 * The four DSC structures (rc_range_parameters, config,
 * picture_parameter_set, pps_infoframe) have identical non-comment
 * declarations and member layouts in those two headers. Reuse the
 * native NetBSD DRM2 types and existing real DSC implementation; do
 * not create a second conflicting enum, struct, or exported symbol.
 *
 * This does not claim new DSC calculations or modern DRM DP/AUX APIs:
 * those have separate providers and must be compiled/linked separately.
 */
#ifndef _NB_I915_MODERN_DRM_DISPLAY_DSC_H_
#define _NB_I915_MODERN_DRM_DISPLAY_DSC_H_

#include <drm/drm_dsc.h>

#endif /* _NB_I915_MODERN_DRM_DISPLAY_DSC_H_ */
