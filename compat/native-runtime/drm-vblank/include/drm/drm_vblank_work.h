/* SPDX-License-Identifier: MIT */
/* NetBSD DRM2 VBlank work: IRQ-safe scheduling, joinable kernel thread. */
#ifndef _DRM_VBLANK_WORK_H_
#define _DRM_VBLANK_WORK_H_
#include <linux/types.h>
#include <linux/list.h>
struct drm_crtc;
struct drm_vblank_crtc;

/* Pinned NetBSD LinuxKPI does not supply kthread_worker. */
struct kthread_work {
	void (*func)(struct kthread_work *);
};
struct drm_vblank_work {
	struct kthread_work base;
	struct drm_vblank_crtc *vblank;
	u64 count;
	int cancelling;
	struct list_head node;
	bool pending_ref;
	bool running;
};
#define to_drm_vblank_work(_w) \
	container_of((_w), struct drm_vblank_work, base)

void drm_vblank_work_init(struct drm_vblank_work *, struct drm_crtc *,
    void (*)(struct kthread_work *));
int drm_vblank_work_schedule(struct drm_vblank_work *, u64, bool);
bool drm_vblank_work_cancel_sync(struct drm_vblank_work *);
void drm_vblank_work_flush(struct drm_vblank_work *);
void drm_vblank_work_flush_all(struct drm_crtc *);
int drm_vblank_worker_init(struct drm_vblank_crtc *);
void drm_vblank_worker_fini(struct drm_vblank_crtc *);
void drm_handle_vblank_works(struct drm_vblank_crtc *);
void drm_vblank_cancel_pending_works(struct drm_vblank_crtc *);
#endif
