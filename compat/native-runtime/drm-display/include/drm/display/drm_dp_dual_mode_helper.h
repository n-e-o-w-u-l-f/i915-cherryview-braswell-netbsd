/* SPDX-License-Identifier: MIT */
/*
 * Modern Linux i915 DP dual-mode ABI on the existing native NetBSD DRM2
 * provider. All I2C accesses use the real NetBSD functions. Legacy users
 * continue including <drm/drm_dp_dual_mode_helper.h> unchanged.
 */
#ifndef _NB_I915_DRM_DISPLAY_DUAL_MODE_H_
#define _NB_I915_DRM_DISPLAY_DUAL_MODE_H_

#include <drm/drm_dp_dual_mode_helper.h>

struct drm_device;

/* The added dev parameter selects Linux's logging context, not I2C I/O. */
static inline enum drm_dp_dual_mode_type
nb_i915_drm_dp_dual_mode_detect(const struct drm_device *dev,
    struct i2c_adapter *adapter)
{
	(void)dev;
	return drm_dp_dual_mode_detect(adapter);
}

static inline int
nb_i915_drm_dp_dual_mode_max_tmds_clock(const struct drm_device *dev,
    enum drm_dp_dual_mode_type type, struct i2c_adapter *adapter)
{
	(void)dev;
	return drm_dp_dual_mode_max_tmds_clock(type, adapter);
}

static inline int
nb_i915_drm_dp_dual_mode_get_tmds_output(const struct drm_device *dev,
    enum drm_dp_dual_mode_type type, struct i2c_adapter *adapter,
    bool *enabled)
{
	(void)dev;
	return drm_dp_dual_mode_get_tmds_output(type, adapter, enabled);
}

static inline int
nb_i915_drm_dp_dual_mode_set_tmds_output(const struct drm_device *dev,
    enum drm_dp_dual_mode_type type, struct i2c_adapter *adapter,
    bool enable)
{
	(void)dev;
	return drm_dp_dual_mode_set_tmds_output(type, adapter, enable);
}

static inline int
nb_i915_drm_lspcon_get_mode(const struct drm_device *dev,
    struct i2c_adapter *adapter, enum drm_lspcon_mode *mode)
{
	(void)dev;
	return drm_lspcon_get_mode(adapter, mode);
}

/* The mode setter is implemented in native DRM2 .c with a real timeout. */
#define drm_dp_dual_mode_detect(dev, adapter) \
	nb_i915_drm_dp_dual_mode_detect((dev), (adapter))
#define drm_dp_dual_mode_max_tmds_clock(dev, type, adapter) \
	nb_i915_drm_dp_dual_mode_max_tmds_clock((dev), (type), (adapter))
#define drm_dp_dual_mode_get_tmds_output(dev, type, adapter, enabled) \
	nb_i915_drm_dp_dual_mode_get_tmds_output((dev), (type), (adapter), (enabled))
#define drm_dp_dual_mode_set_tmds_output(dev, type, adapter, enable) \
	nb_i915_drm_dp_dual_mode_set_tmds_output((dev), (type), (adapter), (enable))
#define drm_lspcon_get_mode(dev, adapter, mode) \
	nb_i915_drm_lspcon_get_mode((dev), (adapter), (mode))
#define drm_lspcon_set_mode(dev, adapter, mode, timeout_ms) \
	nb_i915_drm_lspcon_set_mode((dev), (adapter), (mode), (timeout_ms))

#endif /* _NB_I915_DRM_DISPLAY_DUAL_MODE_H_ */
