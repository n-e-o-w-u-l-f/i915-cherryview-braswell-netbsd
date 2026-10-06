/* Userland adapters for the production worker code, not a kernel runtime. */
#ifndef TEST_SHIM_H
#define TEST_SHIM_H
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#ifndef __printflike
#define __printflike(a,b)
#endif
#define __read_mostly
#ifndef __KERNEL_RCSID
#define __KERNEL_RCSID(a,b)
#endif
#define KASSERT(x) assert(x)
#define KASSERTMSG(x,...) do { if (!(x)) fprintf(stderr,__VA_ARGS__); assert(x); } while (0)
#define IPL_VM 1
#define IPL_HIGH 2
#define MUTEX_DEFAULT 0
#define KM_SLEEP 0
#define PRI_NONE 0
#define KTHREAD_MPSAFE 1
#define KTHREAD_MUSTJOIN 2
#define KTHREAD_TS 4
#define SOFTINT_CLOCK 1
#define SOFTINT_MPSAFE 2
#define MAXCOMLEN 16
#define ERR_PTR(x) ((void *)(intptr_t)(x))
#define PTR_ERR(x) ((long)(intptr_t)(x))
#define IS_ERR(x) ((uintptr_t)(x) >= (uintptr_t)-4095)
#define ERR_CAST(x) ((void *)(x))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#include <stddef.h>

static _Atomic int live_mutexes, live_cvs, live_mem, live_softints, live_lwps;
static _Atomic int fail_create, fail_task_alloc, fail_softint;
static _Thread_local unsigned raw_depth, sleep_depth;

struct gate {
	pthread_mutex_t lock;
	pthread_cond_t cv;
	unsigned entered;
	bool open;
};

static void gate_init(struct gate *g)
{
	assert(pthread_mutex_init(&g->lock, NULL) == 0);
	assert(pthread_cond_init(&g->cv, NULL) == 0);
	g->entered = 0;
	g->open = false;
}
static void gate_enter(struct gate *g)
{
	pthread_mutex_lock(&g->lock);
	g->entered++;
	pthread_cond_broadcast(&g->cv);
	while (!g->open) pthread_cond_wait(&g->cv, &g->lock);
	pthread_mutex_unlock(&g->lock);
}
static void gate_wait(struct gate *g, unsigned n)
{
	struct timespec until;
	clock_gettime(CLOCK_REALTIME, &until);
	until.tv_sec += 10;
	pthread_mutex_lock(&g->lock);
	while (g->entered < n)
		assert(pthread_cond_timedwait(&g->cv, &g->lock, &until) == 0);
	pthread_mutex_unlock(&g->lock);
}
static void gate_open(struct gate *g)
{
	pthread_mutex_lock(&g->lock);
	g->open = true;
	pthread_cond_broadcast(&g->cv);
	pthread_mutex_unlock(&g->lock);
}
static void gate_fini(struct gate *g)
{
	assert(pthread_cond_destroy(&g->cv) == 0);
	assert(pthread_mutex_destroy(&g->lock) == 0);
}

typedef struct {
	pthread_mutex_t lock;
	_Atomic(pthread_t) owner;
	_Atomic bool owned;
	int ipl;
} kmutex_t;
typedef struct {
	pthread_cond_t cv;
	const char *name;
} kcondvar_t;
typedef kcondvar_t drm_waitqueue_t;
typedef struct { kmutex_t sl_lock; } spinlock_t;
typedef struct { kmutex_t rsl_lock; } raw_spinlock_t;
static _Atomic(struct gate *) pause_worker_wait;

static void mutex_init(kmutex_t *m, int type, int ipl)
{
	(void)type;
	assert(pthread_mutex_init(&m->lock, NULL) == 0);
	atomic_store(&m->owned, false);
	m->ipl = ipl;
	atomic_fetch_add(&live_mutexes, 1);
}
static void mutex_enter(kmutex_t *m)
{
	/* No acquisition of a CV/sleep interlock from a raw queue/state lock. */
	assert(m->ipl == IPL_HIGH || raw_depth == 0);
	assert(pthread_mutex_lock(&m->lock) == 0);
	atomic_store(&m->owner, pthread_self());
	atomic_store(&m->owned, true);
	if (m->ipl == IPL_HIGH) raw_depth++; else sleep_depth++;
}
static void mutex_exit(kmutex_t *m)
{
	assert(atomic_load(&m->owned));
	assert(pthread_equal(atomic_load(&m->owner), pthread_self()));
	if (m->ipl == IPL_HIGH) { assert(raw_depth); raw_depth--; }
	else { assert(sleep_depth); sleep_depth--; }
	atomic_store(&m->owned, false);
	assert(pthread_mutex_unlock(&m->lock) == 0);
}
static bool mutex_owned(kmutex_t *m)
{
	return atomic_load(&m->owned) &&
	    pthread_equal(atomic_load(&m->owner), pthread_self());
}
static void mutex_destroy(kmutex_t *m)
{
	assert(!atomic_load(&m->owned));
	assert(pthread_mutex_destroy(&m->lock) == 0);
	atomic_fetch_sub(&live_mutexes, 1);
}
#define mutex_spin_enter mutex_enter
#define mutex_spin_exit mutex_exit
static void spin_lock_init(spinlock_t *m) { mutex_init(&m->sl_lock, 0, IPL_VM); }
static void spin_lock(spinlock_t *m) { mutex_enter(&m->sl_lock); }
static void spin_unlock(spinlock_t *m) { mutex_exit(&m->sl_lock); }
static void spin_lock_destroy(spinlock_t *m) { mutex_destroy(&m->sl_lock); }
#define assert_spin_locked(m) assert(mutex_owned(&(m)->sl_lock))
static void raw_spin_lock_init(raw_spinlock_t *m) { mutex_init(&m->rsl_lock, 0, IPL_HIGH); }
static void raw_spin_lock_destroy(raw_spinlock_t *m) { mutex_destroy(&m->rsl_lock); }
#define raw_spin_lock_irqsave(m,f) do { (f)=0; mutex_enter(&(m)->rsl_lock); } while (0)
#define raw_spin_unlock_irqrestore(m,f) do { (void)(f); mutex_exit(&(m)->rsl_lock); } while (0)

static void cv_init(kcondvar_t *c, const char *name)
{
	assert(pthread_cond_init(&c->cv, NULL) == 0);
	c->name = name;
	atomic_fetch_add(&live_cvs, 1);
}
static void cv_wait(kcondvar_t *c, kmutex_t *m)
{
	struct gate *g;
	assert(raw_depth == 0 && m->ipl != IPL_HIGH && mutex_owned(m));
	if (!strcmp(c->name, "lnxworker") &&
	    (g = atomic_exchange(&pause_worker_wait, NULL)) != NULL)
		gate_enter(g);
	sleep_depth--;
	atomic_store(&m->owned, false);
	assert(pthread_cond_wait(&c->cv, &m->lock) == 0);
	atomic_store(&m->owner, pthread_self());
	atomic_store(&m->owned, true);
	sleep_depth++;
}
static void cv_broadcast(kcondvar_t *c) { assert(pthread_cond_broadcast(&c->cv) == 0); }
static void cv_destroy(kcondvar_t *c)
{
	assert(pthread_cond_destroy(&c->cv) == 0);
	atomic_fetch_sub(&live_cvs, 1);
}
#define DRM_SPIN_WAKEUP_ALL(c,m) do { assert_spin_locked(m); cv_broadcast(c); } while (0)

static void *kmem_zalloc(size_t n, int mode)
{
	(void)mode;
	void *p = calloc(1, n);
	assert(p);
	atomic_fetch_add(&live_mem, 1);
	return p;
}
static void kmem_free(void *p, size_t n)
{
	(void)n;
	free(p);
	atomic_fetch_sub(&live_mem, 1);
}

struct list_head { struct list_head *next, *prev; };
#define LIST_HEAD_INIT(n) { &(n), &(n) }
static void INIT_LIST_HEAD(struct list_head *n) { n->next=n->prev=n; }
static bool list_empty(const struct list_head *n) { return n->next==n; }
static void list_add_tail(struct list_head *n, struct list_head *p)
{
	n->next=p; n->prev=p->prev; p->prev->next=n; p->prev=n;
}
static void list_del_init(struct list_head *n)
{
	n->prev->next=n->next; n->next->prev=n->prev; INIT_LIST_HEAD(n);
}
#define list_first_entry(n,t,m) container_of((n)->next,t,m)

struct test_softint {
	pthread_mutex_t lock;
	pthread_cond_t cv;
	pthread_t thread;
	void (*fn)(void *);
	void *arg;
	bool pending, closing;
};
static void *softint_thread(void *arg)
{
	struct test_softint *si=arg;
	pthread_mutex_lock(&si->lock);
	for (;;) {
		while (!si->pending && !si->closing) pthread_cond_wait(&si->cv, &si->lock);
		if (!si->pending && si->closing) break;
		si->pending=false;
		pthread_mutex_unlock(&si->lock);
		si->fn(si->arg);
		assert(raw_depth==0 && sleep_depth==0);
		pthread_mutex_lock(&si->lock);
	}
	pthread_mutex_unlock(&si->lock);
	return NULL;
}
static void *softint_establish(unsigned flags, void (*fn)(void *), void *arg)
{
	(void)flags;
	if (atomic_exchange(&fail_softint, 0)) return NULL;
	struct test_softint *si=calloc(1,sizeof(*si));
	assert(si);
	pthread_mutex_init(&si->lock,NULL);
	pthread_cond_init(&si->cv,NULL);
	si->fn=fn; si->arg=arg;
	assert(pthread_create(&si->thread,NULL,softint_thread,si)==0);
	atomic_fetch_add(&live_softints,1);
	return si;
}
static void softint_schedule(void *arg)
{
	struct test_softint *si=arg;
	assert(raw_depth>0);
	pthread_mutex_lock(&si->lock);
	assert(!si->closing);
	si->pending=true;
	pthread_cond_signal(&si->cv);
	pthread_mutex_unlock(&si->lock);
}
static void softint_disestablish(void *arg)
{
	struct test_softint *si=arg;
	assert(raw_depth==0 && sleep_depth==0);
	pthread_mutex_lock(&si->lock);
	si->closing=true;
	pthread_cond_signal(&si->cv);
	pthread_mutex_unlock(&si->lock);
	assert(pthread_join(si->thread,NULL)==0);
	pthread_cond_destroy(&si->cv);
	pthread_mutex_destroy(&si->lock);
	free(si);
	atomic_fetch_sub(&live_softints,1);
}

struct lwp {
	pthread_t thread;
	void (*fn)(void *);
	void *arg;
};
static _Thread_local struct lwp *test_curlwp;
#define curlwp test_curlwp
struct task_struct {
	raw_spinlock_t lt_lock;
	void *lt_kthread;
	struct lwp *lt_lwp;
	_Atomic unsigned lt_refs;
	spinlock_t lt_sleep_lock;
	kcondvar_t lt_sleep_cv;
	void *lt_softint;
	unsigned __state;
	bool sleeping;
};
#define TASK_RUNNING 0u
#define TASK_INTERRUPTIBLE 1u
#define TASK_UNINTERRUPTIBLE 2u
#define TASK_PARKED 0x40u
#define TASK_NORMAL (TASK_INTERRUPTIBLE | TASK_UNINTERRUPTIBLE)
static int linux_wake_up_process(struct task_struct *);
static _Thread_local struct task_struct *test_current_task;
static int linux_task_system_init(void) { return 0; }
static int linux_task_system_fini(void) { assert(live_mem==0); return 0; }
static void task_notify(void *arg)
{
	struct task_struct *task=arg;
	spin_lock(&task->lt_sleep_lock);
	cv_broadcast(&task->lt_sleep_cv);
	spin_unlock(&task->lt_sleep_lock);
}
static struct task_struct *linux_task_alloc(void)
{
	if (atomic_exchange(&fail_task_alloc,0)) return NULL;
	struct task_struct *t=kmem_zalloc(sizeof(*t),0);
	raw_spin_lock_init(&t->lt_lock);
	spin_lock_init(&t->lt_sleep_lock);
	cv_init(&t->lt_sleep_cv,"lnxtask");
	t->lt_softint=softint_establish(SOFTINT_CLOCK|SOFTINT_MPSAFE,task_notify,t);
	if(t->lt_softint==NULL) {
		cv_destroy(&t->lt_sleep_cv);
		spin_lock_destroy(&t->lt_sleep_lock);
		raw_spin_lock_destroy(&t->lt_lock);
		kmem_free(t,sizeof(*t));
		return NULL;
	}
	atomic_init(&t->lt_refs,1);
	return t;
}
static void linux_get_task_struct(struct task_struct *t) { assert(atomic_fetch_add(&t->lt_refs,1)>0); }
static void linux_put_task_struct(struct task_struct *t)
{
	unsigned n=atomic_fetch_sub(&t->lt_refs,1);
	assert(n>0);
	if (n==1) {
		assert(t->lt_kthread==NULL);
		softint_disestablish(t->lt_softint);
		cv_destroy(&t->lt_sleep_cv);
		spin_lock_destroy(&t->lt_sleep_lock);
		raw_spin_lock_destroy(&t->lt_lock);
		kmem_free(t,sizeof(*t));
	}
}
#define get_task_struct linux_get_task_struct
#define put_task_struct linux_put_task_struct
static void linux_task_attach_current(struct task_struct *t)
{
	assert(raw_depth==0 && sleep_depth==0 && test_current_task==NULL);
	get_task_struct(t);
	t->lt_lwp=curlwp;
	test_current_task=t;
}
static struct task_struct *linux_current_task(void) { return test_current_task; }
static void linux_set_current_state(unsigned state)
{
	unsigned long flags;
	struct task_struct *task=linux_current_task();
	assert(task && raw_depth==0);
	raw_spin_lock_irqsave(&task->lt_lock,flags);
	task->__state=state;
	raw_spin_unlock_irqrestore(&task->lt_lock,flags);
}
static void *native_kthread_entry(void *arg)
{
	struct lwp *l=arg;
	test_curlwp=l;
	l->fn(l->arg);
	abort();
}
static int kthread_create(int pri, int flags, void *ci, void (*fn)(void *),
    void *arg, struct lwp **lp, const char *fmt, ...)
{
	(void)pri; (void)ci; (void)fmt;
	assert(flags & KTHREAD_MUSTJOIN);
	if (atomic_exchange(&fail_create,0)) return ENOMEM;
	struct lwp *l=calloc(1,sizeof(*l));
	assert(l);
	l->fn=fn; l->arg=arg;
	*lp=l;
	assert(pthread_create(&l->thread,NULL,native_kthread_entry,l)==0);
	atomic_fetch_add(&live_lwps,1);
	return 0;
}
static _Noreturn void kthread_exit(int ret)
{
	assert(ret==0 && raw_depth==0 && sleep_depth==0);
	struct task_struct *t=test_current_task;
	test_current_task=NULL;
	t->lt_lwp=NULL;
	put_task_struct(t);
	pthread_exit(NULL);
}
static int kthread_join(struct lwp *l)
{
	assert(raw_depth==0 && sleep_depth==0);
	assert(pthread_join(l->thread,NULL)==0);
	free(l);
	atomic_fetch_sub(&live_lwps,1);
	return 0;
}
static void preempt_point(void) { assert(raw_depth==0 && sleep_depth==0); sched_yield(); }
#endif
