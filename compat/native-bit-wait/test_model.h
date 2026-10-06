/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit userspace pthread/virtual-CV declarations, never production ABI. */
#ifndef HP_BIT_WAIT_MODEL_H
#define HP_BIT_WAIT_MODEL_H
#include <sys/types.h>
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifndef __KERNEL_RCSID
#define __KERNEL_RCSID(a,b)
#endif
#define CACHE_LINE_SIZE 128
#define PAGE_SIZE 4096
#define __cacheline_aligned __attribute__((aligned(CACHE_LINE_SIZE)))
#define CTASSERT(x) _Static_assert((x), #x)
#ifndef __arraycount
#define __arraycount(a) (sizeof(a)/sizeof((a)[0]))
#endif
#ifndef NBBY
#define NBBY CHAR_BIT
#endif
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MUTEX_DEFAULT 0
#define IPL_VM 0
#define KASSERT(x) assert(x)
#define KASSERTMSG(x,...) assert(x)
_Noreturn static inline void panic(const char *fmt,...) { (void)fmt;abort(); }
#ifndef ERESTART
#define ERESTART 85
#endif
/* Checked against actual frozen/current scheduler constants by the driver. */
#define TASK_INTERRUPTIBLE 1
#define TASK_UNINTERRUPTIBLE 2
#define TASK_WAKEKILL 256
#define TASK_KILLABLE (TASK_UNINTERRUPTIBLE|TASK_WAKEKILL)
#define TASK_IDLE (TASK_UNINTERRUPTIBLE|1024)
typedef pthread_mutex_t kmutex_t;
typedef struct { pthread_cond_t cv; atomic_uint waiters; } kcondvar_t;
static _Thread_local unsigned model_calls,model_mode,model_ticks;
static _Thread_local unsigned model_acquires,model_releases,model_full;
static _Thread_local unsigned model_signal,model_spurious,model_clear_at;
static _Thread_local unsigned model_clear_elapsed;
static _Thread_local int model_error;
static _Thread_local bool model_virtual;
static _Thread_local volatile unsigned long *model_word;
static _Thread_local unsigned model_bit;
static inline void mutex_init(kmutex_t *m,int type,int ipl)
{ (void)type;(void)ipl;assert(pthread_mutex_init(m,NULL)==0); }
static inline void mutex_destroy(kmutex_t *m)
{ assert(pthread_mutex_destroy(m)==0); }
static inline void mutex_enter(kmutex_t *m)
{ assert(pthread_mutex_lock(m)==0); }
static inline void mutex_exit(kmutex_t *m)
{ assert(pthread_mutex_unlock(m)==0); }
static inline void cv_init(kcondvar_t *c,const char *name)
{ (void)name;assert(pthread_cond_init(&c->cv,NULL)==0);atomic_init(&c->waiters,0); }
static inline void cv_destroy(kcondvar_t *c)
{ assert(atomic_load(&c->waiters)==0);assert(pthread_cond_destroy(&c->cv)==0); }
static inline void cv_broadcast(kcondvar_t *c)
{ assert(pthread_cond_broadcast(&c->cv)==0); }
static inline unsigned getticks(void)
{
 if(model_virtual)return model_ticks;
 struct timespec t;assert(clock_gettime(CLOCK_MONOTONIC,&t)==0);
 return (unsigned)((uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000);
}
static inline unsigned ilog2(unsigned x)
{ assert(x);return (unsigned)(sizeof(x)*CHAR_BIT-1-__builtin_clz(x)); }
static inline int test_bit(unsigned n,const volatile unsigned long *p)
{ return (__atomic_load_n(&p[n/(sizeof(*p)*CHAR_BIT)],__ATOMIC_RELAXED)&
    (1UL<<(n%(sizeof(*p)*CHAR_BIT))))!=0; }
static inline void clear_bit(unsigned n,volatile unsigned long *p)
{ __atomic_fetch_and(&p[n/(sizeof(*p)*CHAR_BIT)],~(1UL<<(n%(sizeof(*p)*CHAR_BIT))),__ATOMIC_RELAXED); }
static inline void clear_bit_unlock(unsigned n,volatile unsigned long *p)
{ model_releases++;__atomic_thread_fence(__ATOMIC_RELEASE);clear_bit(n,p); }
#define membar_acquire() do {model_acquires++;__atomic_thread_fence(__ATOMIC_ACQUIRE);} while(0)
#define smp_mb__after_atomic() do {model_full++;__atomic_thread_fence(__ATOMIC_SEQ_CST);} while(0)
/* Signals and elapsed ticks here are injected model inputs, not native events. */
static inline int model_cv(kcondvar_t *c,kmutex_t *m,int ticks,unsigned mode)
{
 model_calls++;model_mode=mode;assert(ticks>=0 && ticks<=INT_MAX/2);
 if((mode==1 && model_signal!=0)||(mode==2 && model_signal>=2))return ERESTART;
 if(model_error){int e=model_error;model_error=0;return e;}
 if(model_virtual){
  if(model_spurious){model_spurious--;return 0;}
  unsigned elapsed=(unsigned)ticks;
  if(model_calls==model_clear_at){
   if(ticks && model_clear_elapsed<elapsed)elapsed=model_clear_elapsed;
   clear_bit(model_bit,model_word);
  }else assert(ticks>0);
  model_ticks+=elapsed;
  return ticks && model_calls!=model_clear_at ? EWOULDBLOCK : 0;
 }
 atomic_fetch_add_explicit(&c->waiters,1,memory_order_release);
 int e;
 if(!ticks)e=pthread_cond_wait(&c->cv,m);
 else {
  struct timespec t;assert(clock_gettime(CLOCK_REALTIME,&t)==0);
  t.tv_sec+=ticks/1000;t.tv_nsec+=(ticks%1000)*1000000L;
  if(t.tv_nsec>=1000000000L){t.tv_sec++;t.tv_nsec-=1000000000L;}
  e=pthread_cond_timedwait(&c->cv,m,&t);
 }
 atomic_fetch_sub_explicit(&c->waiters,1,memory_order_release);
 assert(e==0||e==ETIMEDOUT);return e==ETIMEDOUT ? EWOULDBLOCK : 0;
}
static inline void cv_wait(kcondvar_t *c,kmutex_t *m) { (void)model_cv(c,m,0,0); }
static inline int cv_wait_sig(kcondvar_t *c,kmutex_t *m) { return model_cv(c,m,0,1); }
static inline int cv_wait_sig_fatal(kcondvar_t *c,kmutex_t *m) { return model_cv(c,m,0,2); }
static inline int cv_timedwait(kcondvar_t *c,kmutex_t *m,int n) { return model_cv(c,m,n,0); }
static inline int cv_timedwait_sig(kcondvar_t *c,kmutex_t *m,int n) { return model_cv(c,m,n,1); }
static inline int cv_timedwait_sig_fatal(kcondvar_t *c,kmutex_t *m,int n) { return model_cv(c,m,n,2); }
#endif
