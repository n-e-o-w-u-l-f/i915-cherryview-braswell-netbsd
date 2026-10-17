/* SPDX-License-Identifier: MIT */
/*
 * Native DRM VBlank callback worker for NetBSD 11.
 * dev->event_lock protects pending/ready/running/cancelling in both IRQ
 * and thread contexts. Callbacks execute outside interrupt and spinlock.
 * One MUSTJOIN kernel thread per CRTC is quiesced before DRM core teardown.
 */
#include <sys/types.h>
#include <sys/kthread.h>
#include <sys/lwp.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/list.h>
#include <linux/spinlock.h>
#include <linux/atomic.h>
#include <drm/drm_crtc.h>
#include <drm/drm_device.h>
#include <drm/drm_vblank.h>
#include <drm/drm_vblank_work.h>
#include <drm/drm_wait_netbsd.h>

static bool
nb_vblank_passed(u64 vblank_seq, u64 target)
{
	return (int64_t)(vblank_seq - target) >= 0;
}

static void
nb_vblank_ready(struct drm_vblank_crtc *vblank,
    struct drm_vblank_work *work)
{
	KASSERT(spin_is_locked(&vblank->dev->event_lock));
	if (!list_empty(&work->node))
		list_del_init(&work->node);
	work->pending_ref = false;
	list_add_tail(&work->node, &vblank->ready_work);
	DRM_SPIN_WAKEUP_ALL(&vblank->worker_wait_queue,
	    &vblank->dev->event_lock);
	DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,
	    &vblank->dev->event_lock);
}

static void
nb_vblank_worker_main(void *cookie)
{
	struct drm_vblank_crtc *vblank = cookie;
	struct drm_device *dev = vblank->dev;
	struct drm_vblank_work *work;
	int error;

	spin_lock(&dev->event_lock);
	for (;;) {
		DRM_SPIN_WAIT_NOINTR_UNTIL(error, &vblank->worker_wait_queue,
		    &dev->event_lock, vblank->worker_stopping ||
		    !list_empty(&vblank->ready_work));
		KASSERT(error == 0);
		if (vblank->worker_stopping &&
		    list_empty(&vblank->ready_work))
			break;
		work = list_first_entry(&vblank->ready_work,
		    struct drm_vblank_work, node);
		list_del_init(&work->node);
		KASSERT(!work->running);
		vblank->worker_running = true;
		work->running = true;
		DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,
		    &dev->event_lock);
		spin_unlock(&dev->event_lock);

		(*work->base.func)(&work->base);

		spin_lock(&dev->event_lock);
		work->running = false;
		vblank->worker_running = false;
		DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,
		    &dev->event_lock);
	}
	spin_unlock(&dev->event_lock);
	kthread_exit(0);
}

int
drm_vblank_worker_init(struct drm_vblank_crtc *vblank)
{
	int error;

	INIT_LIST_HEAD(&vblank->pending_work);
	INIT_LIST_HEAD(&vblank->ready_work);
	DRM_INIT_WAITQUEUE(&vblank->work_wait_queue, "drmvblwd");
	DRM_INIT_WAITQUEUE(&vblank->worker_wait_queue, "drmvblwk");
	vblank->worker_running = false;
	vblank->worker_stopping = false;
	vblank->work_thread = NULL;
	error = kthread_create(PRI_NONE, KTHREAD_MPSAFE | KTHREAD_MUSTJOIN,
	    NULL, nb_vblank_worker_main, vblank, &vblank->work_thread,
	    "drmvbl%u", vblank->pipe);
	if (error) {
		DRM_DESTROY_WAITQUEUE(&vblank->worker_wait_queue);
		DRM_DESTROY_WAITQUEUE(&vblank->work_wait_queue);
		return -error;
	}
	return 0;
}

void
drm_vblank_cancel_pending_works(struct drm_vblank_crtc *vblank)
{
	struct drm_device *dev = vblank->dev;
	struct drm_vblank_work *work, *next;

	KASSERT(spin_is_locked(&dev->event_lock));
	list_for_each_entry_safe(work, next, &vblank->pending_work, node) {
		list_del_init(&work->node);
		KASSERT(work->pending_ref);
		work->pending_ref = false;
		nb_i915_vblank_ref_put_locked(vblank);
	}
	DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue, &dev->event_lock);
}

void
drm_vblank_worker_fini(struct drm_vblank_crtc *vblank)
{
	struct drm_device *dev = vblank->dev;
	unsigned long flags;
	int error;

	spin_lock_irqsave(&dev->event_lock, flags);
	vblank->worker_stopping = true;
	drm_vblank_cancel_pending_works(vblank);
	DRM_SPIN_WAKEUP_ALL(&vblank->worker_wait_queue, &dev->event_lock);
	spin_unlock_irqrestore(&dev->event_lock, flags);
	error = kthread_join(vblank->work_thread);
	KASSERT(error == 0);
	vblank->work_thread = NULL;
	DRM_DESTROY_WAITQUEUE(&vblank->work_wait_queue);
	DRM_DESTROY_WAITQUEUE(&vblank->worker_wait_queue);
}

void
drm_handle_vblank_works(struct drm_vblank_crtc *vblank)
{
	struct drm_device *dev = vblank->dev;
	struct drm_vblank_work *work, *next;
	u64 vblank_seq = atomic64_read(&vblank->count);

	KASSERT(spin_is_locked(&dev->event_lock));
	list_for_each_entry_safe(work, next, &vblank->pending_work, node) {
		if (!nb_vblank_passed(vblank_seq, work->count))
			continue;
		KASSERT(work->pending_ref);
		nb_i915_vblank_ref_put_locked(vblank);
		nb_vblank_ready(vblank, work);
	}
}

void
drm_vblank_work_init(struct drm_vblank_work *work, struct drm_crtc *crtc,
    void (*func)(struct kthread_work *))
{
	INIT_LIST_HEAD(&work->node);
	work->base.func = func;
	work->vblank = &crtc->dev->vblank[drm_crtc_index(crtc)];
	work->count = 0;
	work->cancelling = 0;
	work->pending_ref = false;
	work->running = false;
}

int
drm_vblank_work_schedule(struct drm_vblank_work *work, u64 target,
    bool nextonmiss)
{
	struct drm_vblank_crtc *vblank = work->vblank;
	struct drm_device *dev = vblank->dev;
	unsigned long flags;
	u64 vblank_seq;
	bool passed;
	int error = 0;

	spin_lock_irqsave(&dev->event_lock, flags);
	if (vblank->worker_stopping || work->cancelling ||
	    vblank->inmodeset)
		goto out;
	if (!list_empty(&work->node) && work->count == target)
		goto out;
	/* Hold one real IRQ reference until dispatch/cancellation. */
	if (!work->pending_ref) {
		error = nb_i915_vblank_ref_get_locked(vblank);
		if (error < 0)
			goto out;
		work->pending_ref = true;
	}
	vblank_seq = atomic64_read(&vblank->count);
	passed = nb_vblank_passed(vblank_seq, target);
	if (passed && nextonmiss)
		target = vblank_seq + 1;
	work->count = target;
	if (!list_empty(&work->node))
		list_del_init(&work->node);
	if (nextonmiss || !passed)
		list_add_tail(&work->node, &vblank->pending_work);
	else {
		nb_i915_vblank_ref_put_locked(vblank);
		nb_vblank_ready(vblank, work);
	}
	error = 1;
out:
	spin_unlock_irqrestore(&dev->event_lock, flags);
	return error;
}

bool
drm_vblank_work_cancel_sync(struct drm_vblank_work *work)
{
	struct drm_vblank_crtc *vblank = work->vblank;
	struct drm_device *dev = vblank->dev;
	unsigned long flags;
	bool cancelled = false;
	int error;

	spin_lock_irqsave(&dev->event_lock, flags);
	work->cancelling++;
	if (!list_empty(&work->node)) {
		list_del_init(&work->node);
		if (work->pending_ref)
			nb_i915_vblank_ref_put_locked(vblank);
		work->pending_ref = false;
		cancelled = true;
	}
	DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue, &dev->event_lock);
	DRM_SPIN_WAIT_NOINTR_UNTIL(error, &vblank->work_wait_queue,
	    &dev->event_lock, !work->running);
	KASSERT(error == 0);
	KASSERT(work->cancelling > 0);
	work->cancelling--;
	spin_unlock_irqrestore(&dev->event_lock, flags);
	return cancelled;
}

void
drm_vblank_work_flush(struct drm_vblank_work *work)
{
	struct drm_vblank_crtc *vblank = work->vblank;
	struct drm_device *dev = vblank->dev;
	unsigned long flags;
	int error;

	spin_lock_irqsave(&dev->event_lock, flags);
	DRM_SPIN_WAIT_NOINTR_UNTIL(error, &vblank->work_wait_queue,
	    &dev->event_lock,
	    list_empty(&work->node) && !work->running);
	KASSERT(error == 0);
	spin_unlock_irqrestore(&dev->event_lock, flags);
}

void
drm_vblank_work_flush_all(struct drm_crtc *crtc)
{
	struct drm_device *dev = crtc->dev;
	struct drm_vblank_crtc *vblank =
	    &dev->vblank[drm_crtc_index(crtc)];
	unsigned long flags;
	int error;

	spin_lock_irqsave(&dev->event_lock, flags);
	DRM_SPIN_WAIT_NOINTR_UNTIL(error, &vblank->work_wait_queue,
	    &dev->event_lock,
	    list_empty(&vblank->pending_work) &&
	    list_empty(&vblank->ready_work) &&
	    !vblank->worker_running);
	KASSERT(error == 0);
	spin_unlock_irqrestore(&dev->event_lock, flags);
}
