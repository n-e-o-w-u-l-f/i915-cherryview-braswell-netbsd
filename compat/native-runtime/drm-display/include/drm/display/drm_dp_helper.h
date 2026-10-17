/* SPDX-License-Identifier: MIT */
/*
 * Linux drm/display/drm_dp_helper.h compatibility for the exact older
 * NetBSD DRM2 AUX backend. No hardware-independent success stub is used.
 * Only explicitly checked APIs are exposed here; other modern functions
 * must remain compiler failures until their provider is ported.
 */
#ifndef _NB_I915_NATIVE_DRM_DISPLAY_DP_HELPER_H_
#define _NB_I915_NATIVE_DRM_DISPLAY_DP_HELPER_H_

#include <linux/errno.h>
#include <drm/drm_dp_helper.h>

/*
 * Linux >= 6.x reports 0 for full DPCD transfers and negative errno for
 * failures. NetBSD's drm_dp_dpcd_read/write report transferred byte count.
 * A short transfer MUST be -EPROTO, not mistaken for success.
 */
static inline int
nb_i915_dp_dpcd_read_data(struct drm_dp_aux *aux, unsigned int offset,
    void *buffer, size_t size)
{
	ssize_t ret;
	size_t i;
	u8 *bytes = buffer;

	ret = drm_dp_dpcd_read(aux, offset, buffer, size);
	if (ret >= 0)
		return (size_t)ret == size ? 0 : -EPROTO;

	/* Linux's negative-read fallback, with explicit short-read failure. */
	for (i = 0; i < size; ++i) {
		ret = drm_dp_dpcd_read(aux, offset + i, &bytes[i], 1);
		if (ret < 0)
			return (int)ret;
		if (ret != 1)
			return -EPROTO;
	}
	return 0;
}

static inline int
nb_i915_dp_dpcd_write_data(struct drm_dp_aux *aux, unsigned int offset,
    void *buffer, size_t size)
{
	ssize_t ret = drm_dp_dpcd_write(aux, offset, buffer, size);
	if (ret < 0)
		return (int)ret;
	return (size_t)ret == size ? 0 : -EPROTO;
}

static inline int
nb_i915_dp_dpcd_read_byte(struct drm_dp_aux *aux,
    unsigned int offset, u8 *value)
{
	return nb_i915_dp_dpcd_read_data(aux, offset, value, 1);
}

static inline int
nb_i915_dp_dpcd_write_byte(struct drm_dp_aux *aux,
    unsigned int offset, u8 value)
{
	return nb_i915_dp_dpcd_write_data(aux, offset, &value, 1);
}

/*
 * Native NetBSD helper already implements Cherryview's 8b/10b AUX delays,
 * including DPCD_REV >= 1.4 clock recovery. The modern aux argument only
 * informs newer helpers' logging and is not needed by this implementation.
 */
static inline void
nb_i915_dp_link_train_clock_recovery_delay(const struct drm_dp_aux *aux,
    const u8 dpcd[DP_RECEIVER_CAP_SIZE])
{
	(void)aux;
	drm_dp_link_train_clock_recovery_delay(dpcd);
}

static inline void
nb_i915_dp_link_train_channel_eq_delay(const struct drm_dp_aux *aux,
    const u8 dpcd[DP_RECEIVER_CAP_SIZE])
{
	(void)aux;
	drm_dp_link_train_channel_eq_delay(dpcd);
}

#define drm_dp_dpcd_read_data(aux, offset, buffer, size) \
	nb_i915_dp_dpcd_read_data((aux), (offset), (buffer), (size))
#define drm_dp_dpcd_write_data(aux, offset, buffer, size) \
	nb_i915_dp_dpcd_write_data((aux), (offset), (buffer), (size))
#define drm_dp_dpcd_read_byte(aux, offset, value) \
	nb_i915_dp_dpcd_read_byte((aux), (offset), (value))
#define drm_dp_dpcd_write_byte(aux, offset, value) \
	nb_i915_dp_dpcd_write_byte((aux), (offset), (value))
#define drm_dp_link_train_clock_recovery_delay(aux, dpcd) \
	nb_i915_dp_link_train_clock_recovery_delay((aux), (dpcd))
#define drm_dp_link_train_channel_eq_delay(aux, dpcd) \
	nb_i915_dp_link_train_channel_eq_delay((aux), (dpcd))

#endif /* _NB_I915_NATIVE_DRM_DISPLAY_DP_HELPER_H_ */
