/* Immediate kthread workers, backed by a native joinable LWP. */
struct kthread_work;
typedef void (*kthread_work_func_t)(struct kthread_work *);

enum {
	KTW_FREEZABLE = 1U << 0,
};

struct kthread_work {
	struct list_head node;
	kthread_work_func_t func;
	struct kthread_worker *worker;
	unsigned int canceling;
};

struct kthread_worker {
	unsigned int flags;
	raw_spinlock_t lock;
	struct list_head work_list;
	struct task_struct *task;
	struct kthread_work *current_work;

	/* Native fields: no queue-lock -> sleep-lock acquisition. */
	spinlock_t kw_sleep_lock;
	drm_waitqueue_t kw_wq;
	void *kw_softint;
	bool kw_started;
	bool kw_destroying;
};

#define KTHREAD_WORK_INIT(work, fn) {				\
	.node = LIST_HEAD_INIT((work).node),			\
	.func = (fn),						\
}
#define DEFINE_KTHREAD_WORK(work, fn)				\
	struct kthread_work work = KTHREAD_WORK_INIT(work, fn)

static inline void
kthread_init_work(struct kthread_work *work, kthread_work_func_t func)
{
	INIT_LIST_HEAD(&work->node);
	work->func = func;
	work->worker = NULL;
	work->canceling = 0;
}

#define kthread_create_worker	linux_kthread_create_worker
#define kthread_run_worker	linux_kthread_run_worker
#define kthread_queue_work	linux_kthread_queue_work
#define kthread_cancel_work_sync	linux_kthread_cancel_work_sync
#define kthread_flush_work	linux_kthread_flush_work
#define kthread_flush_worker	linux_kthread_flush_worker
#define kthread_destroy_worker	linux_kthread_destroy_worker

struct kthread_worker *kthread_create_worker(unsigned int, const char *, ...)
	__printflike(2, 3);
struct kthread_worker *kthread_run_worker(unsigned int, const char *, ...)
	__printflike(2, 3);
bool kthread_queue_work(struct kthread_worker *, struct kthread_work *);
bool kthread_cancel_work_sync(struct kthread_work *);
void kthread_flush_work(struct kthread_work *);
void kthread_flush_worker(struct kthread_worker *);
void kthread_destroy_worker(struct kthread_worker *);

/* The scheduler calls the locked variant while holding task->lt_lock. */
int linux_kthread_wake_locked(struct task_struct *);
int linux_kthread_wake(struct task_struct *);
