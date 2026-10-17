/* SPDX-License-Identifier: MIT */
/*
 * Incremental native NetBSD DRM2 compatibility for modern Linux i915 MST.
 *
 * Only the verified split HPD/ACK transaction is adapted here. Other modern
 * MST atomic/payload and topology APIs must be implemented separately;
 * missing symbols must remain build errors, never fabricated success.
 */
#ifndef _NB_I915_DRM_DISPLAY_MST_H_
#define _NB_I915_DRM_DISPLAY_MST_H_

#include <drm/drm_dp_mst_helper.h>

/* The native provider does not kick TX until ACK completes. */
#define drm_dp_mst_hpd_irq_handle_event(mgr, esi, ack, handled) \
	nb_i915_drm_dp_mst_hpd_irq_handle_event((mgr), (esi), (ack), (handled))
#define drm_dp_mst_hpd_irq_send_new_request(mgr) \
	nb_i915_drm_dp_mst_hpd_irq_send_new_request((mgr))

#endif /* _NB_I915_DRM_DISPLAY_MST_H_ */
