/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit pthread delegation, not a native NetBSD implementation or proof. */
#ifndef TASK_NOTIFIER_MODEL_H
#define TASK_NOTIFIER_MODEL_H
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <sys/types.h>
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#define KASSERT(c) assert(c)
#define KASSERTMSG(c,...) assert(c)
#define panic(...) do { fprintf(stderr, __VA_ARGS__); fputc('\n',stderr); abort(); } while (0)
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAXCOMLEN 16
#define KM_SLEEP 0
#define PRI_NONE 0
#define PRI_KERNEL_RT 63
#define IPL_HIGH 2
#define WQ_MPSAFE 1
#define LW_PENDSIG 1U
#define LW_WEXIT 2U
#define LW_WCORE 4U
#ifndef ERESTART
#define ERESTART 85
#endif
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define membar_sync() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define atomic_load_acquire(p) __atomic_load_n((p),__ATOMIC_ACQUIRE)
#define atomic_load_relaxed(p) __atomic_load_n((p),__ATOMIC_RELAXED)
#define atomic_inc_uint(p) ((void)__atomic_add_fetch((p),1,__ATOMIC_SEQ_CST))
#define atomic_dec_uint(p) ((void)__atomic_sub_fetch((p),1,__ATOMIC_SEQ_CST))
static _Thread_local unsigned int test_raw_depth;
static _Thread_local bool test_irq;
#define ASSERT_SLEEPABLE() assert(test_raw_depth==0 && !test_irq)
typedef struct { pthread_mutex_t lock; pthread_t owner; bool held; } kmutex_t;
typedef struct { kmutex_t sl_lock; } spinlock_t;
typedef struct { kmutex_t rsl_lock; } raw_spinlock_t;
typedef struct { pthread_cond_t cv; unsigned int waiters; } kcondvar_t;
typedef pthread_key_t specificdata_key_t;
struct proc { pid_t p_pid; char p_comm[MAXCOMLEN+1]; };
struct lwp { struct proc *l_proc; unsigned int l_flag, signals; int l_class, pri; kmutex_t lock; };
static _Thread_local struct proc test_proc;
static _Thread_local struct lwp test_lwp;
#define curlwp (&test_lwp)
#define curproc (&test_proc)
static void mutex_init(kmutex_t *m,int type,int ipl)
{ (void)type;(void)ipl;assert(pthread_mutex_init(&m->lock,NULL)==0);m->held=false; }
static void mutex_enter(kmutex_t *m)
{ assert(pthread_mutex_lock(&m->lock)==0);m->owner=pthread_self();m->held=true; }
static void mutex_exit(kmutex_t *m)
{ m->held=false;assert(pthread_mutex_unlock(&m->lock)==0); }
static bool mutex_owned(kmutex_t *m) { return m->held&&pthread_equal(m->owner,pthread_self()); }
static void mutex_destroy(kmutex_t *m) { assert(pthread_mutex_destroy(&m->lock)==0); }
static void spin_lock_init(spinlock_t *m) { mutex_init(&m->sl_lock,0,0); }
static void spin_lock_destroy(spinlock_t *m) { mutex_destroy(&m->sl_lock); }
static void spin_lock(spinlock_t *m) { mutex_enter(&m->sl_lock); }
static void spin_unlock(spinlock_t *m) { mutex_exit(&m->sl_lock); }
static void raw_spin_lock_init(raw_spinlock_t *m) { mutex_init(&m->rsl_lock,0,IPL_HIGH); }
static void raw_spin_lock_destroy(raw_spinlock_t *m) { mutex_destroy(&m->rsl_lock); }
static unsigned long model_raw_lock(raw_spinlock_t *m)
{ unsigned long n=test_raw_depth;mutex_enter(&m->rsl_lock);test_raw_depth++;return n; }
#define raw_spin_lock_irqsave(m,f) ((f)=model_raw_lock(m))
static void raw_spin_unlock_irqrestore(raw_spinlock_t *m,unsigned long f)
{ assert(test_raw_depth==f+1);test_raw_depth=(unsigned int)f;mutex_exit(&m->rsl_lock); }
static volatile unsigned int test_allocs,test_frees,test_keys,test_key_deletes,test_signals;
struct model_allocation { size_t size; };
static void *kmem_zalloc(size_t n,int f)
{ ASSERT_SLEEPABLE();assert(f==KM_SLEEP);struct model_allocation *p=calloc(1,sizeof(*p)+n);
  assert(p);p->size=n;atomic_inc_uint(&test_allocs);return p+1; }
static void kmem_free(void *v,size_t n)
{ ASSERT_SLEEPABLE();struct model_allocation *p=(struct model_allocation *)v-1;
  assert(n==p->size);atomic_inc_uint(&test_frees);free(p); }
static size_t model_strlcpy(char *d,const char *s,size_t n)
{ size_t z=strlen(s);if(n){size_t c=MIN(z,n-1);memcpy(d,s,c);d[c]=0;}return z; }
#define strlcpy model_strlcpy
static int lwp_specific_key_create(specificdata_key_t *k,void(*fn)(void *))
{ int e=pthread_key_create(k,fn);if(!e)atomic_inc_uint(&test_keys);return e; }
static void lwp_specific_key_delete(specificdata_key_t k)
{ assert(pthread_key_delete(k)==0);atomic_inc_uint(&test_key_deletes); }
static void *lwp_getspecific(specificdata_key_t k) { return pthread_getspecific(k); }
static void lwp_setspecific(specificdata_key_t k,void *p) { ASSERT_SLEEPABLE();assert(pthread_setspecific(k,p)==0); }
static void lwp_lock(struct lwp *l) { mutex_enter(&l->lock); }
static void lwp_unlock(struct lwp *l) { mutex_exit(&l->lock); }
static void lwp_changepri(struct lwp *l,int p) { l->pri=p; }
static bool sleepq_dontsleep(struct lwp *l) { (void)l;return false; }
static int sigispending(struct lwp *l,int s) { return s?(int)(l->signals&(1U<<s)):(int)l->signals; }
static bool sleepq_fatal_pending(struct lwp *l)
{ return (l->l_flag&(LW_WEXIT|LW_WCORE))!=0 || sigispending(l,SIGKILL)!=0; }
static bool preempt_needed(void) { return false; }
static void preempt_point(void) { }
static void model_yield(void) { (void)sched_yield(); }
#define yield model_yield
static unsigned int getticks(void)
{ struct timespec t;assert(clock_gettime(CLOCK_MONOTONIC,&t)==0);
  return (unsigned int)((uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000); }
static void (*test_signal_hook)(void);
static void cv_init(kcondvar_t *c,const char *name)
{ (void)name;c->waiters=0;assert(pthread_cond_init(&c->cv,NULL)==0); }
static void cv_destroy(kcondvar_t *c) { assert(c->waiters==0);assert(pthread_cond_destroy(&c->cv)==0); }
static bool cv_has_waiters(kcondvar_t *c) { return c->waiters!=0; }
static void cv_signal(kcondvar_t *c)
{ atomic_inc_uint(&test_signals);if(test_signal_hook)test_signal_hook();assert(pthread_cond_signal(&c->cv)==0); }
static int model_cv_wait(kcondvar_t *c,kmutex_t *m,int ticks,bool intr,bool fatal)
{ if(intr&&(fatal?sleepq_fatal_pending(curlwp):sigispending(curlwp,0)!=0))return ERESTART;
  int e;c->waiters++;m->held=false;
  if(!ticks)e=pthread_cond_wait(&c->cv,&m->lock);
  else {struct timespec t;assert(clock_gettime(CLOCK_REALTIME,&t)==0);
    t.tv_sec+=ticks/1000;t.tv_nsec+=(ticks%1000)*1000000L;
    if(t.tv_nsec>=1000000000L){t.tv_sec++;t.tv_nsec-=1000000000L;}
    e=pthread_cond_timedwait(&c->cv,&m->lock,&t);}
  m->held=true;m->owner=pthread_self();c->waiters--;assert(e==0||e==ETIMEDOUT);return e==ETIMEDOUT?EWOULDBLOCK:0; }
static void cv_wait(kcondvar_t *c,kmutex_t *m) { (void)model_cv_wait(c,m,0,false,false); }
static int cv_wait_sig(kcondvar_t *c,kmutex_t *m) { return model_cv_wait(c,m,0,true,false); }
static int cv_wait_sig_fatal(kcondvar_t *c,kmutex_t *m) { return model_cv_wait(c,m,0,true,true); }
static int cv_timedwait(kcondvar_t *c,kmutex_t *m,int n) { return model_cv_wait(c,m,n,false,false); }
static int cv_timedwait_sig(kcondvar_t *c,kmutex_t *m,int n) { return model_cv_wait(c,m,n,true,false); }
static int cv_timedwait_sig_fatal(kcondvar_t *c,kmutex_t *m,int n) { return model_cv_wait(c,m,n,true,true); }

/* Native's non-per-CPU batch contract: one worker, no callback concurrency,
 * cache next before invoking a callback which may free its embedded work. */
struct work { void *wk_dummy; };
struct workqueue { pthread_mutex_t lock;pthread_cond_t cv;pthread_t thread;
    struct work *head,*tail;bool paused,busy,stop;void(*fn)(struct work *,void *);void *arg; };
static bool test_wq_fail;
static volatile unsigned int test_wq_creates,test_wq_destroys,test_enqueues;
static void *model_wq_thread(void *v)
{ struct workqueue *q=v;assert(pthread_mutex_lock(&q->lock)==0);
  for(;;){while((!q->head||q->paused)&&!q->stop)assert(pthread_cond_wait(&q->cv,&q->lock)==0);
    if(!q->head&&q->stop)break;
    struct work *w=q->head;q->head=q->tail=NULL;q->busy=true;
    assert(pthread_mutex_unlock(&q->lock)==0);
    while(w){struct work *next=w->wk_dummy;q->fn(w,q->arg);w=next;}
    assert(pthread_mutex_lock(&q->lock)==0);q->busy=false;assert(pthread_cond_broadcast(&q->cv)==0);}
  assert(pthread_mutex_unlock(&q->lock)==0);return NULL; }
static int workqueue_create(struct workqueue **out,const char *name,
    void(*fn)(struct work *,void *),void *arg,int pri,int ipl,int flags)
{ ASSERT_SLEEPABLE();(void)name;assert(pri==PRI_NONE&&ipl==IPL_HIGH&&flags==WQ_MPSAFE);
  atomic_inc_uint(&test_wq_creates);if(test_wq_fail)return EAGAIN;
  struct workqueue *q=calloc(1,sizeof(*q));assert(q);q->fn=fn;q->arg=arg;
  assert(pthread_mutex_init(&q->lock,NULL)==0);assert(pthread_cond_init(&q->cv,NULL)==0);
  assert(pthread_create(&q->thread,NULL,model_wq_thread,q)==0);*out=q;return 0; }
static void workqueue_enqueue(struct workqueue *q,struct work *w,void *cpu)
{ assert(cpu==NULL&&test_raw_depth!=0);assert(pthread_mutex_lock(&q->lock)==0);assert(!q->stop);
  for(struct work *p=q->head;p;p=p->wk_dummy)assert(p!=w);
  w->wk_dummy=NULL;if(q->tail)q->tail->wk_dummy=w;else q->head=w;q->tail=w;
  atomic_inc_uint(&test_enqueues);assert(pthread_cond_broadcast(&q->cv)==0);assert(pthread_mutex_unlock(&q->lock)==0); }
static void workqueue_wait(struct workqueue *q,struct work *w)
{ ASSERT_SLEEPABLE();assert(!pthread_equal(q->thread,pthread_self()));assert(pthread_mutex_lock(&q->lock)==0);
  for(;;){bool pending=false;for(struct work *p=q->head;p;p=p->wk_dummy)pending|=p==w;
    if(!pending&&!q->busy)break;
    assert(pthread_cond_wait(&q->cv,&q->lock)==0);}
  assert(pthread_mutex_unlock(&q->lock)==0); }
static void workqueue_destroy(struct workqueue *q)
{ ASSERT_SLEEPABLE();assert(pthread_mutex_lock(&q->lock)==0);assert(q->head==NULL);
  q->stop=true;assert(pthread_cond_broadcast(&q->cv)==0);assert(pthread_mutex_unlock(&q->lock)==0);
  assert(pthread_join(q->thread,NULL)==0);assert(pthread_mutex_destroy(&q->lock)==0);
  assert(pthread_cond_destroy(&q->cv)==0);free(q);atomic_inc_uint(&test_wq_destroys); }
static void model_pause(struct workqueue *q,bool pause)
{ assert(pthread_mutex_lock(&q->lock)==0);q->paused=pause;assert(pthread_cond_broadcast(&q->cv)==0);
  assert(pthread_mutex_unlock(&q->lock)==0); }
struct task_struct;
int linux_kthread_wake_locked(struct task_struct *);
#endif
