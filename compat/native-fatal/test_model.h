/* SPDX-License-Identifier: BSD-2-Clause */
/* Pthread delegation model for the unchanged candidate C sources.
 * Tests callback/state/timeout logic, not NetBSD sleepq execution. */
#ifndef WAIT_TEST_MODEL_H
#define WAIT_TEST_MODEL_H
#include <sys/types.h>
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAXCOMLEN 16
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#ifndef __arraycount
#define __arraycount(a) (sizeof(a)/sizeof((a)[0]))
#endif
#define MUTEX_DEFAULT 0
#define IPL_VM 1
#define IPL_HIGH 2
#define KM_SLEEP 0
#define SOFTINT_CLOCK 1
#define SOFTINT_MPSAFE 0x100
#define LW_PENDSIG 0x01000000U
#define LW_SINTR 0x80U
#define LW_WEXIT 0x00100000U
#define LW_WCORE 0x00080000U
#define SOBJ_SIGKILL 0x10U
#define PRI_KERNEL_RT 63
#ifndef ERESTART
#define ERESTART 85
#endif
#define ERESTARTSYS ERESTART
#define KASSERT(x) assert(x)
#define KASSERTMSG(x,...) assert(x)
#define __init
#define __force
#define unlikely(x) (x)
#define likely(x) (x)
#define might_sleep() ASSERT_SLEEPABLE()
#define smp_mb() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define membar_sync() smp_mb()
#define smp_store_mb(x,v) do { (x)=(v); smp_mb(); } while (0)
#define atomic_load_acquire(p) __atomic_load_n((p),__ATOMIC_ACQUIRE)
#define atomic_load_relaxed(p) __atomic_load_n((p),__ATOMIC_RELAXED)
#define atomic_inc_uint(p) ((void)__atomic_add_fetch((p),1,__ATOMIC_SEQ_CST))
#define atomic_dec_uint(p) ((void)__atomic_sub_fetch((p),1,__ATOMIC_SEQ_CST))

static _Thread_local unsigned int test_raw_depth;
static _Thread_local bool test_irq;
#define ASSERT_SLEEPABLE() assert(test_raw_depth == 0 && !test_irq)
typedef struct { pthread_mutex_t lock; pthread_t owner; bool held; } kmutex_t;
typedef pthread_cond_t kcondvar_t;
typedef pthread_key_t specificdata_key_t;
struct proc { pid_t p_pid; char p_comm[MAXCOMLEN+1]; };
typedef const struct syncobj { unsigned int sobj_flag; } syncobj_t;
typedef struct lwp lwp_t;
struct lwp { syncobj_t *l_syncobj; struct proc *l_proc; volatile unsigned int l_flag;
    unsigned int signals; int l_class; int pri; kmutex_t lock; };
static _Thread_local struct proc test_proc;
static _Thread_local struct lwp test_lwp;
#define curlwp (&test_lwp)
#define curproc (&test_proc)
static inline void mutex_init(kmutex_t *m, int type, int ipl)
{ (void)type; (void)ipl; assert(pthread_mutex_init(&m->lock,NULL)==0); m->held=false; }
static inline void mutex_enter(kmutex_t *m)
{ assert(pthread_mutex_lock(&m->lock)==0); m->owner=pthread_self(); m->held=true; }
static inline void mutex_exit(kmutex_t *m)
{ m->held=false; assert(pthread_mutex_unlock(&m->lock)==0); }
static inline bool mutex_owned(kmutex_t *m)
{ return m->held && pthread_equal(m->owner,pthread_self()); }
static inline void mutex_destroy(kmutex_t *m)
{ assert(pthread_mutex_destroy(&m->lock)==0); }
typedef struct { kmutex_t sl_lock; } spinlock_t;
typedef struct { kmutex_t rsl_lock; } raw_spinlock_t;
static inline void spin_lock_init(spinlock_t *m) { mutex_init(&m->sl_lock,0,IPL_VM); }
static inline void spin_lock_destroy(spinlock_t *m) { mutex_destroy(&m->sl_lock); }
static inline void spin_lock(spinlock_t *m) { mutex_enter(&m->sl_lock); }
static inline void spin_unlock(spinlock_t *m) { mutex_exit(&m->sl_lock); }
#define spin_lock_irq spin_lock
#define spin_unlock_irq spin_unlock
#define spin_lock_irqsave(m,f) do { (f)=0; spin_lock(m); } while (0)
#define spin_unlock_irqrestore(m,f) do { (void)(f); spin_unlock(m); } while (0)
#define assert_spin_locked(m) assert(mutex_owned(&(m)->sl_lock))
static inline void raw_spin_lock_init(raw_spinlock_t *m) { mutex_init(&m->rsl_lock,0,IPL_HIGH); }
static inline void raw_spin_lock_destroy(raw_spinlock_t *m) { mutex_destroy(&m->rsl_lock); }
static inline unsigned long test_raw_enter(raw_spinlock_t *m)
{ unsigned long f=test_raw_depth; mutex_enter(&m->rsl_lock); test_raw_depth++; return f; }
#define raw_spin_lock_irqsave(m,f) ((f)=test_raw_enter(m))
static inline void raw_spin_unlock_irqrestore(raw_spinlock_t *m,unsigned long f)
{ assert(test_raw_depth==f+1); test_raw_depth=(unsigned int)f; mutex_exit(&m->rsl_lock); }

static void (*test_alloc_hook)(void);
static inline void *kmem_zalloc(size_t n,int flag) { (void)flag; if(test_alloc_hook)test_alloc_hook(); void *p=calloc(1,n); assert(p); return p; }
static inline void kmem_free(void *p,size_t n) { (void)n; free(p); }
static inline size_t test_strlcpy(char *d,const char *s,size_t n)
{ size_t l=strlen(s); if(n){ size_t c=MIN(l,n-1); memcpy(d,s,c); d[c]=0; } return l; }
#define strlcpy test_strlcpy
static inline int lwp_specific_key_create(specificdata_key_t *k,void(*d)(void *))
{ return pthread_key_create(k,d); }
static inline void lwp_specific_key_delete(specificdata_key_t k) { assert(pthread_key_delete(k)==0); }
static inline void *lwp_getspecific(specificdata_key_t k) { return pthread_getspecific(k); }
static inline void lwp_setspecific(specificdata_key_t k,void *v) { assert(pthread_setspecific(k,v)==0); }
static inline void lwp_lock(struct lwp *l) { mutex_enter(&l->lock); }
static inline void lwp_unlock(struct lwp *l) { mutex_exit(&l->lock); }
static inline bool lwp_locked(struct lwp *l,void *v) { (void)v;return mutex_owned(&l->lock); }
bool sleepq_fatal_pending(lwp_t *);
bool sleepq_sigwake_allowed(lwp_t *,int);
static inline void lwp_changepri(struct lwp *l,int p) { l->pri=p; }
static inline bool sleepq_dontsleep(struct lwp *l) { (void)l; return false; }
static inline int sigispending(struct lwp *l,int s)
{ unsigned int v=l->signals; if(s) return (v&(1U<<s)) ? s : 0;
  for(int i=1;i<32;i++) { if(v&(1U<<i)) return i; }
  return 0; }
static inline bool preempt_needed(void) { return false; }
static inline void preempt_point(void) { }
static inline void test_yield(void) { (void)sched_yield(); }
#define yield test_yield

static bool test_virtual_time;
static unsigned int test_ticks;
static unsigned int test_slices;
static void (*test_wait_hook)(bool, int);
static inline unsigned int getticks(void)
{ if(test_virtual_time) return test_ticks; struct timespec t; assert(clock_gettime(CLOCK_MONOTONIC,&t)==0);
  return (unsigned int)((uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000); }
static inline void cv_init(kcondvar_t *c,const char *s) { (void)s; assert(pthread_cond_init(c,NULL)==0); }
static inline void cv_destroy(kcondvar_t *c) { assert(pthread_cond_destroy(c)==0); }
static inline bool cv_has_waiters(kcondvar_t *c) { (void)c; return false; }
static inline void cv_signal(kcondvar_t *c) { assert(pthread_cond_signal(c)==0); }
static inline int test_cv_wait(kcondvar_t *c,kmutex_t *m,int ticks,bool intr,bool fatal)
{
    if(test_wait_hook) test_wait_hook(intr,ticks);
    if(intr && (fatal ? sleepq_fatal_pending(curlwp) : sigispending(curlwp,0)!=0)) return ERESTART;
    if(test_virtual_time && ticks) { test_slices++; test_ticks+=(unsigned int)ticks; return EWOULDBLOCK; }
    m->held=false;
    int e;
    if(!ticks) e=pthread_cond_wait(c,&m->lock);
    else { struct timespec t; assert(clock_gettime(CLOCK_REALTIME,&t)==0);
        t.tv_sec+=ticks/1000; t.tv_nsec+=(ticks%1000)*1000000L;
        if(t.tv_nsec>=1000000000L){t.tv_sec++;t.tv_nsec-=1000000000L;}
        e=pthread_cond_timedwait(c,&m->lock,&t); }
    m->owner=pthread_self();m->held=true;
    assert(e==0 || e==ETIMEDOUT); return e==ETIMEDOUT ? EWOULDBLOCK : 0;
}
static inline void cv_wait(kcondvar_t *c,kmutex_t *m) { (void)test_cv_wait(c,m,0,false,false); }
static inline int cv_wait_sig(kcondvar_t *c,kmutex_t *m) { return test_cv_wait(c,m,0,true,false); }
static inline int cv_timedwait(kcondvar_t *c,kmutex_t *m,int n) { return test_cv_wait(c,m,n,false,false); }
static inline int cv_timedwait_sig(kcondvar_t *c,kmutex_t *m,int n) { return test_cv_wait(c,m,n,true,false); }

static inline int cv_wait_sig_fatal(kcondvar_t *c,kmutex_t *m) { return test_cv_wait(c,m,0,true,true); }
static inline int cv_timedwait_sig_fatal(kcondvar_t *c,kmutex_t *m,int n) { return test_cv_wait(c,m,n,true,true); }

struct test_softint { pthread_mutex_t lock; pthread_cond_t cv; pthread_t thread;
    bool pending,stop; void(*fn)(void *);void *cookie; };
static bool test_softint_fail;
static void *test_softint_run(void *v)
{ struct test_softint *s=v; assert(pthread_mutex_lock(&s->lock)==0);
  for(;;){while(!s->pending&&!s->stop)assert(pthread_cond_wait(&s->cv,&s->lock)==0);
    if(s->stop&&!s->pending) { break; }
    s->pending=false;assert(pthread_mutex_unlock(&s->lock)==0);
    s->fn(s->cookie);assert(pthread_mutex_lock(&s->lock)==0);}
  assert(pthread_mutex_unlock(&s->lock)==0);return NULL; }
static inline void *softint_establish(unsigned int f,void(*fn)(void *),void *v)
{ (void)f; if(test_softint_fail)return NULL;struct test_softint *s=calloc(1,sizeof(*s));assert(s);
  assert(pthread_mutex_init(&s->lock,NULL)==0);assert(pthread_cond_init(&s->cv,NULL)==0);
  s->fn=fn;s->cookie=v;assert(pthread_create(&s->thread,NULL,test_softint_run,s)==0);return s; }
static inline void softint_schedule(void *v)
{ assert(test_raw_depth!=0); struct test_softint *s=v;assert(pthread_mutex_lock(&s->lock)==0);
  assert(!s->stop);s->pending=true;assert(pthread_cond_signal(&s->cv)==0);assert(pthread_mutex_unlock(&s->lock)==0); }
static inline void softint_disestablish(void *v)
{ struct test_softint *s=v;assert(pthread_mutex_lock(&s->lock)==0);s->stop=true;
  assert(pthread_cond_signal(&s->cv)==0);assert(pthread_mutex_unlock(&s->lock)==0);
  assert(pthread_join(s->thread,NULL)==0);assert(pthread_cond_destroy(&s->cv)==0);
  assert(pthread_mutex_destroy(&s->lock)==0);free(s); }

struct list_head { struct list_head *next,*prev; };
#define LIST_HEAD_INIT(n) { &(n), &(n) }
#define INIT_LIST_HEAD(p) do { (p)->next=(p);(p)->prev=(p); } while(0)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_entry(p,t,m) container_of(p,t,m)
#define list_first_entry(h,t,m) list_entry((h)->next,t,m)
#define list_next_entry(p,m) list_entry((p)->m.next,typeof(*(p)),m)
static inline bool list_empty(const struct list_head *h) { return h->next==h; }
static inline bool list_is_singular(const struct list_head *h) { return !list_empty(h)&&h->next==h->prev; }
static inline void list_add(struct list_head *p,struct list_head *h)
{ p->next=h->next;p->prev=h;h->next->prev=p;h->next=p; }
static inline void list_add_tail(struct list_head *p,struct list_head *h) { list_add(p,h->prev); }
static inline void list_del(struct list_head *p) { p->prev->next=p->next;p->next->prev=p->prev; }
static inline void list_del_init(struct list_head *p) { list_del(p);INIT_LIST_HEAD(p); }
#define list_for_each_entry(p,h,m) for((p)=list_first_entry(h,typeof(*(p)),m);&(p)->m!=(h);(p)=list_next_entry(p,m))
#define list_for_each_entry_safe_from(p,n,h,m) for((n)=list_next_entry(p,m);&(p)->m!=(h);(p)=(n),(n)=list_next_entry(n,m))

struct lock_class_key;
struct task_struct;
int linux_kthread_wake_locked(struct task_struct *);
static int test_should_stop;
static inline int kthread_should_stop(void) { return test_should_stop; }
static inline int kthread_should_park(void) { return 0; }
#endif
