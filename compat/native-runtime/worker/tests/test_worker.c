#include "test_shim.h"
#include "test_kthread_header.h"
#include "test_kthread_impl.inc"

/* Adapter for the separate common scheduler CV and worker gate hook. */
static int linux_wake_up_process(struct task_struct *task)
{
	unsigned long flags;
	int woke=0;
	raw_spin_lock_irqsave(&task->lt_lock,flags);
	if(task->__state & TASK_NORMAL) {
		task->__state=TASK_RUNNING;
		task->sleeping=false;
		softint_schedule(task->lt_softint);
		woke=1;
	}
	woke|=linux_kthread_wake_locked(task);
	raw_spin_unlock_irqrestore(&task->lt_lock,flags);
	return woke;
}

struct test_work {
	struct kthread_work work;
	struct kthread_worker *worker;
	struct gate *gate;
	_Atomic unsigned calls;
	bool queue_before, queue_after;
	_Atomic bool requeued;
};
static unsigned task_state(struct task_struct *);

static void work_fn(struct kthread_work *work)
{
	struct test_work *w=container_of(work,struct test_work,work);
	assert(raw_depth==0 && sleep_depth==0);
	assert(task_state(linux_current_task())==TASK_RUNNING);
	atomic_fetch_add(&w->calls,1);
	if (w->queue_before)
		atomic_store(&w->requeued,kthread_queue_work(w->worker,work));
	if (w->gate) gate_enter(w->gate);
	if (w->queue_after)
		atomic_store(&w->requeued,kthread_queue_work(w->worker,work));
}
static void work_init(struct test_work *w, struct kthread_worker *worker,
    struct gate *gate)
{
	memset(w,0,sizeof(*w));
	kthread_init_work(&w->work,work_fn);
	w->worker=worker;
	w->gate=gate;
}

static unsigned queue_length(struct kthread_worker *worker)
{
	unsigned long flags;
	unsigned n=0;
	struct list_head *p;
	raw_spin_lock_irqsave(&worker->lock,flags);
	for(p=worker->work_list.next;p!=&worker->work_list;p=p->next) n++;
	raw_spin_unlock_irqrestore(&worker->lock,flags);
	return n;
}
static unsigned task_state(struct task_struct *task)
{
	unsigned long flags;
	unsigned state;
	raw_spin_lock_irqsave(&task->lt_lock,flags);
	state=task->__state;
	raw_spin_unlock_irqrestore(&task->lt_lock,flags);
	return state;
}
static void wait_task_state(struct task_struct *task,unsigned state)
{
	struct timespec start,now;
	clock_gettime(CLOCK_MONOTONIC,&start);
	while(task_state(task)!=state) {
		sched_yield(); clock_gettime(CLOCK_MONOTONIC,&now);
		assert(now.tv_sec-start.tv_sec<10);
	}
}
static void wait_queue(struct kthread_worker *worker, unsigned n)
{
	struct timespec start,now;
	clock_gettime(CLOCK_MONOTONIC,&start);
	while(queue_length(worker)<n) {
		sched_yield();
		clock_gettime(CLOCK_MONOTONIC,&now);
		assert(now.tv_sec-start.tv_sec<10);
	}
}
static void wait_canceling(struct kthread_worker *worker,
    struct kthread_work *work,unsigned n)
{
	unsigned long flags;
	unsigned seen;
	struct timespec start,now;
	clock_gettime(CLOCK_MONOTONIC,&start);
	do {
		raw_spin_lock_irqsave(&worker->lock,flags);
		seen=work->canceling;
		raw_spin_unlock_irqrestore(&worker->lock,flags);
		if(seen==n) return;
		sched_yield();
		clock_gettime(CLOCK_MONOTONIC,&now);
		assert(now.tv_sec-start.tv_sec<10);
	} while(true);
}
static void wait_closing(struct kthread_worker *worker)
{
	unsigned long flags;
	bool seen;
	struct timespec start,now;
	clock_gettime(CLOCK_MONOTONIC,&start);
	do {
		raw_spin_lock_irqsave(&worker->lock,flags);
		seen=worker->kw_destroying;
		raw_spin_unlock_irqrestore(&worker->lock,flags);
		if(seen) return;
		sched_yield();
		clock_gettime(CLOCK_MONOTONIC,&now);
		assert(now.tv_sec-start.tv_sec<10);
	} while(true);
}

enum operation { FLUSH_WORK, FLUSH_WORKER, CANCEL, DESTROY };
struct call {
	enum operation op;
	struct kthread_worker *worker;
	struct kthread_work *work;
	pthread_t thread;
	_Atomic bool done;
	bool result;
};
static void *call_thread(void *arg)
{
	struct call *c=arg;
	switch(c->op) {
	case FLUSH_WORK: kthread_flush_work(c->work); break;
	case FLUSH_WORKER: kthread_flush_worker(c->worker); break;
	case CANCEL: c->result=kthread_cancel_work_sync(c->work); break;
	case DESTROY: kthread_destroy_worker(c->worker); break;
	}
	atomic_store(&c->done,true);
	return NULL;
}
static void call_start(struct call *c, enum operation op,
    struct kthread_worker *worker, struct kthread_work *work)
{
	memset(c,0,sizeof(*c));
	c->op=op; c->worker=worker; c->work=work;
	assert(pthread_create(&c->thread,NULL,call_thread,c)==0);
}
static void call_join(struct call *c)
{
	assert(pthread_join(c->thread,NULL)==0);
	assert(atomic_load(&c->done));
}
static void expect_clean(void)
{
	assert(live_mutexes==0 && live_cvs==0 && live_mem==0);
	assert(live_softints==0 && live_lwps==0);
}

static void test_create_run_and_queue_start(void)
{
	struct kthread_worker *worker=kthread_create_worker(0,"deferred-%d",1);
	struct test_work w;
	assert(!IS_ERR(worker) && !worker->kw_started);
	assert(worker->task->lt_lwp!=NULL);
	assert(linux_kthread_wake(worker->task)==1);
	assert(linux_kthread_wake(worker->task)==0);
	wait_task_state(worker->task,TASK_INTERRUPTIBLE);
	assert(linux_wake_up_process(worker->task)==1);
	kthread_destroy_worker(worker);

	worker=kthread_create_worker(0,"queued-start");
	assert(!IS_ERR(worker) && !worker->kw_started);
	work_init(&w,worker,NULL);
	assert(kthread_queue_work(worker,&w.work));
	kthread_flush_worker(worker);
	assert(w.calls==1);
	kthread_destroy_worker(worker);

	worker=kthread_create_worker(0,"never-run");
	assert(!IS_ERR(worker) && !worker->kw_started);
	kthread_destroy_worker(worker);
	worker=kthread_run_worker(0,"running");
	assert(!IS_ERR(worker) && worker->kw_started);
	kthread_destroy_worker(worker);
	assert(PTR_ERR(kthread_run_worker(KTW_FREEZABLE,"unsupported"))==-EOPNOTSUPP);
	assert(PTR_ERR(kthread_create_worker(2,"unknown"))==-EOPNOTSUPP);
	expect_clean();
}

static void test_duplicate_and_pending_cancel(void)
{
	struct gate g;
	struct test_work a,b,c,idle;
	struct call f;
	gate_init(&g);
	struct kthread_worker *worker=kthread_run_worker(0,"pending");
	work_init(&a,worker,&g); work_init(&b,worker,NULL);
	work_init(&c,worker,NULL); work_init(&idle,worker,NULL);
	assert(kthread_queue_work(worker,&a.work)); gate_wait(&g,1);
	assert(kthread_queue_work(worker,&b.work));
	assert(!kthread_queue_work(worker,&b.work));
	assert(kthread_queue_work(worker,&c.work));
	assert(kthread_cancel_work_sync(&c.work));
	assert(!kthread_cancel_work_sync(&c.work));
	assert(!kthread_cancel_work_sync(&idle.work));
	kthread_flush_work(&idle.work);
	call_start(&f,FLUSH_WORKER,worker,NULL); wait_queue(worker,2);
	assert(!atomic_load(&f.done));
	gate_open(&g); call_join(&f);
	assert(a.calls==1 && b.calls==1 && c.calls==0);
	kthread_destroy_worker(worker); gate_fini(&g); expect_clean();
}

static void test_work_flush_excludes_later_work(void)
{
	struct gate ga,gb;
	struct test_work a,b;
	struct call f;
	gate_init(&ga); gate_init(&gb);
	struct kthread_worker *worker=kthread_run_worker(0,"work-snapshot");
	work_init(&a,worker,&ga); work_init(&b,worker,&gb);
	assert(kthread_queue_work(worker,&a.work)); gate_wait(&ga,1);
	assert(kthread_queue_work(worker,&b.work));
	call_start(&f,FLUSH_WORK,worker,&a.work); wait_queue(worker,2);
	gate_open(&ga); gate_wait(&gb,1); call_join(&f);
	assert(b.calls==1);
	gate_open(&gb); kthread_destroy_worker(worker);
	gate_fini(&ga); gate_fini(&gb); expect_clean();
}

static void test_worker_flush_snapshot(void)
{
	struct gate ga,gb;
	struct test_work a,b;
	struct call f;
	gate_init(&ga); gate_init(&gb);
	struct kthread_worker *worker=kthread_run_worker(0,"worker-snapshot");
	work_init(&a,worker,&ga); work_init(&b,worker,&gb);
	assert(kthread_queue_work(worker,&a.work)); gate_wait(&ga,1);
	call_start(&f,FLUSH_WORKER,worker,NULL); wait_queue(worker,1);
	assert(kthread_queue_work(worker,&b.work));
	gate_open(&ga); gate_wait(&gb,1); call_join(&f);
	gate_open(&gb); kthread_destroy_worker(worker);
	gate_fini(&ga); gate_fini(&gb); expect_clean();
}

struct self_work {
	struct kthread_work work;
	struct kthread_worker *worker;
	struct gate first,third;
	_Atomic unsigned calls;
};
static void self_requeue_fn(struct kthread_work *work)
{
	struct self_work *w=container_of(work,struct self_work,work);
	unsigned n=atomic_fetch_add(&w->calls,1)+1;
	assert(n<=3);
	if(n<=2) assert(kthread_queue_work(w->worker,work));
	if(n==1) gate_enter(&w->first);
	if(n==3) gate_enter(&w->third);
}
static void test_self_requeue_work_flush_snapshot(void)
{
	struct self_work w={0};
	struct call f;
	gate_init(&w.first); gate_init(&w.third);
	w.worker=kthread_run_worker(0,"self-snapshot");
	kthread_init_work(&w.work,self_requeue_fn);
	assert(kthread_queue_work(w.worker,&w.work)); gate_wait(&w.first,1);
	call_start(&f,FLUSH_WORK,w.worker,&w.work); wait_queue(w.worker,2);
	gate_open(&w.first); gate_wait(&w.third,1); call_join(&f);
	assert(w.calls==3);
	gate_open(&w.third); kthread_destroy_worker(w.worker);
	gate_fini(&w.first); gate_fini(&w.third); expect_clean();
}

static void test_concurrent_cancellation_and_requeue(void)
{
	struct gate g;
	struct test_work w;
	struct call cancel[4];
	unsigned removed=0;
	gate_init(&g);
	struct kthread_worker *worker=kthread_run_worker(0,"cancel-fan-in");
	work_init(&w,worker,&g); w.queue_before=true; w.queue_after=true;
	assert(kthread_queue_work(worker,&w.work)); gate_wait(&g,1);
	assert(atomic_load(&w.requeued));
	for(unsigned i=0;i<4;i++) call_start(&cancel[i],CANCEL,worker,&w.work);
	wait_canceling(worker,&w.work,4);
	assert(!kthread_queue_work(worker,&w.work));
	gate_open(&g);
	for(unsigned i=0;i<4;i++) { call_join(&cancel[i]); removed+=cancel[i].result; }
	assert(removed==1 && !atomic_load(&w.requeued));
	assert(w.calls==1 && w.work.canceling==0);
	w.gate=NULL; w.queue_before=w.queue_after=false;
	assert(kthread_queue_work(worker,&w.work)); kthread_flush_worker(worker);
	assert(w.calls==2);
	kthread_destroy_worker(worker); gate_fini(&g); expect_clean();
}

static void test_destroy_closes_and_drains(void)
{
	struct gate g;
	struct test_work a,b,c;
	struct call d;
	gate_init(&g);
	struct kthread_worker *worker=kthread_run_worker(0,"destroy-drain");
	work_init(&a,worker,&g); work_init(&b,worker,NULL); work_init(&c,worker,NULL);
	a.queue_after=true;
	assert(kthread_queue_work(worker,&a.work)); gate_wait(&g,1);
	assert(kthread_queue_work(worker,&b.work));
	call_start(&d,DESTROY,worker,NULL); wait_closing(worker);
	assert(!kthread_queue_work(worker,&c.work));
	gate_open(&g); call_join(&d);
	assert(a.calls==1 && !atomic_load(&a.requeued));
	assert(b.calls==1 && c.calls==0);
	gate_fini(&g); expect_clean();
}

struct free_work {
	struct kthread_work work;
	_Atomic unsigned *calls;
	size_t pagesize;
};
static void free_own_work_fn(struct kthread_work *work)
{
	struct free_work *w=container_of(work,struct free_work,work);
	_Atomic unsigned *calls=w->calls;
	size_t pagesize=w->pagesize;
	atomic_fetch_add(calls,1);
	assert(munmap(w,pagesize)==0);
	/* Any worker dereference of work from here must fault. */
}
static void test_callback_unmaps_its_own_work(void)
{
	_Atomic unsigned calls=0;
	size_t pagesize=(size_t)sysconf(_SC_PAGESIZE);
	struct free_work *w=mmap(NULL,pagesize,PROT_READ|PROT_WRITE,
	    MAP_ANON|MAP_PRIVATE,-1,0);
	assert(w!=MAP_FAILED);
	w->calls=&calls; w->pagesize=pagesize;
	kthread_init_work(&w->work,free_own_work_fn);
	struct kthread_worker *worker=kthread_run_worker(0,"self-unmap");
	assert(kthread_queue_work(worker,&w->work));
	kthread_flush_worker(worker); assert(calls==1);
	kthread_destroy_worker(worker); expect_clean();
}

static void test_no_lost_check_sleep_wakeup(void)
{
	struct gate pause;
	struct test_work w;
	gate_init(&pause); atomic_store(&pause_worker_wait,&pause);
	struct kthread_worker *worker=kthread_run_worker(0,"wakeup-handoff");
	gate_wait(&pause,1);
	work_init(&w,worker,NULL);
	assert(kthread_queue_work(worker,&w.work));
	/* Consumer holds sleep lock after check; notifier is forced to wait. */
	gate_open(&pause);
	kthread_flush_worker(worker); assert(w.calls==1);
	kthread_destroy_worker(worker); gate_fini(&pause); expect_clean();
}

static void test_park_queue_unpark(void)
{
	struct test_work w;
	struct call f;
	struct kthread_worker *worker=kthread_create_worker(0,"parked");
	kthread_park(worker->task);
	assert(task_state(worker->task)==TASK_PARKED);
	work_init(&w,worker,NULL);
	assert(kthread_queue_work(worker,&w.work));
	call_start(&f,FLUSH_WORKER,worker,NULL); wait_queue(worker,2);
	assert(w.calls==0 && !atomic_load(&f.done));
	kthread_unpark(worker->task); call_join(&f); assert(w.calls==1);
	kthread_park(worker->task);
	kthread_destroy_worker(worker); expect_clean();
}

static int legacy_fn(void *arg)
{
	assert(linux_current_task()!=NULL);
	return *(int *)arg;
}
static void test_creation_failure_cleanup_and_legacy(void)
{
	atomic_store(&fail_softint,1);
	assert(PTR_ERR(kthread_run_worker(0,"softint-fail"))==-ENOMEM); expect_clean();
	atomic_store(&fail_task_alloc,1);
	assert(PTR_ERR(kthread_run_worker(0,"task-fail"))==-ENOMEM); expect_clean();
	atomic_store(&fail_create,1);
	assert(PTR_ERR(kthread_run_worker(0,"native-fail"))==-ENOMEM); expect_clean();
	spinlock_t lock; drm_waitqueue_t cv;
	int value=42;
	spin_lock_init(&lock); cv_init(&cv,"legacy");
	struct task_struct *task=kthread_run(legacy_fn,&value,"legacy",&lock,&cv);
	assert(!IS_ERR(task)); assert(kthread_stop(task)==42);
	atomic_store(&fail_create,1);
	assert(PTR_ERR(kthread_run(legacy_fn,&value,"legacy-fail",&lock,&cv))==-ENOMEM);
	cv_destroy(&cv); spin_lock_destroy(&lock); expect_clean();
}

struct scheduler_work {
	struct kthread_work work;
	_Atomic bool entered, stopped;
};
static void scheduler_sleeping_work_fn(struct kthread_work *base)
{
	struct scheduler_work *work=container_of(base,struct scheduler_work,work);
	struct task_struct *task=linux_current_task();
	unsigned long flags;
	spin_lock(&task->lt_sleep_lock);
	for(;;) {
		raw_spin_lock_irqsave(&task->lt_lock,flags);
		task->sleeping=true;
		task->__state=TASK_INTERRUPTIBLE;
		raw_spin_unlock_irqrestore(&task->lt_lock,flags);
		/* Linux wait preparation publishes sleep state before condition check. */
		if(kthread_should_stop()) {
			raw_spin_lock_irqsave(&task->lt_lock,flags);
			task->sleeping=false;
			task->__state=TASK_RUNNING;
			raw_spin_unlock_irqrestore(&task->lt_lock,flags);
			break;
		}
		atomic_store(&work->entered,true);
		cv_wait(&task->lt_sleep_cv,&task->lt_sleep_lock.sl_lock);
	}
	spin_unlock(&task->lt_sleep_lock);
	atomic_store(&work->stopped,true);
}
static void test_stop_wakes_common_scheduler_cv(void)
{
	struct scheduler_work work={0};
	struct kthread_worker *worker=kthread_run_worker(0,"task-cv-stop");
	kthread_init_work(&work.work,scheduler_sleeping_work_fn);
	assert(kthread_queue_work(worker,&work.work));
	struct timespec start,now;
	clock_gettime(CLOCK_MONOTONIC,&start);
	while(!atomic_load(&work.entered)) {
		sched_yield(); clock_gettime(CLOCK_MONOTONIC,&now);
		assert(now.tv_sec-start.tv_sec<10);
	}
	/* Stop owns the same task, but its kt_wq is not the callback's task CV. */
	assert(kthread_stop(worker->task)==0);
	assert(atomic_load(&work.stopped));
	assert(worker->task==NULL && worker->current_work==NULL);
	softint_disestablish(worker->kw_softint);
	cv_destroy(&worker->kw_wq);
	spin_lock_destroy(&worker->kw_sleep_lock);
	raw_spin_lock_destroy(&worker->lock);
	kmem_free(worker,sizeof(*worker));
	expect_clean();
}

struct producer {
	struct kthread_worker *worker;
	struct test_work *works;
	unsigned begin,end,removed;
};
static void *producer_fn(void *arg)
{
	struct producer *p=arg;
	for(unsigned i=p->begin;i<p->end;i++) {
		assert(kthread_queue_work(p->worker,&p->works[i].work));
		if(i%2==0) p->removed+=kthread_cancel_work_sync(&p->works[i].work);
	}
	return NULL;
}
static void test_queue_cancel_stress(void)
{
	for(unsigned round=0;round<60;round++) {
		struct test_work works[64];
		struct producer p[4]; pthread_t threads[4];
		unsigned calls=0,removed=0;
		struct kthread_worker *worker=kthread_run_worker(0,"stress-%u",round);
		for(unsigned i=0;i<64;i++) work_init(&works[i],worker,NULL);
		for(unsigned i=0;i<4;i++) {
			p[i]=(struct producer){worker,works,i*16,(i+1)*16,0};
			assert(pthread_create(&threads[i],NULL,producer_fn,&p[i])==0);
		}
		for(unsigned i=0;i<4;i++) {
			assert(pthread_join(threads[i],NULL)==0); removed+=p[i].removed;
		}
		kthread_flush_worker(worker);
		for(unsigned i=0;i<64;i++) { assert(works[i].calls<=1); calls+=works[i].calls; }
		assert(calls+removed==64);
		kthread_destroy_worker(worker); expect_clean();
	}
}

int main(void)
{
	alarm(120);
	assert(linux_kthread_init()==0);
#define RUN(fn) do { fn(); printf("PASS %s\n",#fn); fflush(stdout); } while(0)
	RUN(test_create_run_and_queue_start);
	RUN(test_duplicate_and_pending_cancel);
	RUN(test_work_flush_excludes_later_work);
	RUN(test_worker_flush_snapshot);
	RUN(test_self_requeue_work_flush_snapshot);
	RUN(test_concurrent_cancellation_and_requeue);
	RUN(test_destroy_closes_and_drains);
	RUN(test_callback_unmaps_its_own_work);
	RUN(test_no_lost_check_sleep_wakeup);
	RUN(test_park_queue_unpark);
	RUN(test_creation_failure_cleanup_and_legacy);
	RUN(test_stop_wakes_common_scheduler_cv);
	RUN(test_queue_cancel_stress);
	linux_kthread_fini();
	puts("PASS native-worker userland adapters; kernel execution remains OPEN");
	return 0;
}
