#!/usr/bin/env python3
"""Run genuine NetBSD VBlank provider C functions with real POSIX threads.

Source-extracted C11/UBSan, pthread mutex/cond substitutes for NetBSD IRQ
spinlock/wait. Not a NetBSD kernel compiler, real interrupt or scheduling
class test. Fails closed if the immutable candidate changes unexpectedly.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

PINNED_SHA256 = "fe31c46d491a4b93589d6c8308895266de22ee66913864ddde8b1234c29b12be"
METHODS = (
    "nb_vblank_passed",
    "nb_vblank_ready",
    "nb_vblank_worker_main",
    "drm_vblank_worker_init",
    "drm_vblank_cancel_pending_works",
    "drm_vblank_worker_fini",
    "drm_handle_vblank_works",
    "drm_vblank_work_init",
    "drm_vblank_work_schedule",
    "drm_vblank_work_cancel_sync",
    "nb_vblank_flush_fence_func",
    "nb_vblank_flush_ready_locked",
    "drm_vblank_work_flush",
    "drm_vblank_work_flush_all",
)


def extract(source: str, name: str) -> str:
    m = re.search(r"(?m)^(?:static\s+)?(?:bool|void|int)\s*\n" +
                  re.escape(name) + r"\(", source)
    if m is None:
        raise AssertionError("missing provider function: " + name)
    pos = source.index("{", m.end())
    depth = 0
    for i in range(pos, len(source)):
        if source[i] == "{":
            depth += 1
        if source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[m.start():i + 1]
    raise AssertionError("unbalanced source function: " + name)


PRELUDE = r"""
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <time.h>
#include <stddef.h>
#include <unistd.h>
typedef uint64_t u64;
struct list_head { struct list_head *next, *prev; };
#define INIT_LIST_HEAD(h) do { (h)->next=(h); (h)->prev=(h); } while (0)
static bool list_empty(const struct list_head *h) { return h->next==h; }
static void list_add_tail(struct list_head *p,struct list_head *h) {
    p->next=h; p->prev=h->prev; h->prev->next=p; h->prev=p;
}
static void list_del_init(struct list_head *p) {
    p->prev->next=p->next; p->next->prev=p->prev; INIT_LIST_HEAD(p);
}
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define list_first_entry(h,t,m) container_of((h)->next,t,m)
#define list_for_each_entry_safe(p,n,h,m) \
 for (struct list_head *__it=(h)->next,*__next; \
      __it!=(h) && ((__next=__it->next), \
       (p)=container_of(__it,__typeof__(*(p)),m), \
       (n)=__next==(h)?NULL:container_of(__next,__typeof__(*(n)),m),true); \
      __it=__next)
struct kthread_work {void (*func)(struct kthread_work *);};
struct drm_device;
struct drm_vblank_crtc;
struct drm_vblank_work {
    struct kthread_work base;
    struct drm_vblank_crtc *vblank;
    struct list_head node;
    u64 count; int cancelling; bool pending_ref,running;
};
struct lwp {pthread_t tid;};
struct drm_vblank_crtc {
    struct drm_device *dev; unsigned pipe;
    u64 count; unsigned inmodeset;
    struct list_head pending_work, ready_work;
    pthread_cond_t work_wait_queue, worker_wait_queue;
    bool worker_stopping,worker_running;
    struct lwp *work_thread;
};
struct drm_device { pthread_mutex_t event_lock; struct drm_vblank_crtc *vblank; };
struct drm_crtc { struct drm_device *dev; unsigned idx; };
#define PRI_NONE 0
#define KTHREAD_MPSAFE 1
#define KTHREAD_MUSTJOIN 2
#define KASSERT(e) assert(e)
#define atomic64_read(p) (*(p))
#define spin_is_locked(l) ((void)(l),true)
#define spin_lock(l) do {int _e=pthread_mutex_lock(l);assert(!_e);}while(0)
#define spin_unlock(l) do {int _e=pthread_mutex_unlock(l);assert(!_e);}while(0)
#define spin_lock_irqsave(l,f) do{(f)=0;spin_lock(l);}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);spin_unlock(l);}while(0)
#define DRM_INIT_WAITQUEUE(q,n) do{(void)(n);assert(!pthread_cond_init(q,NULL));}while(0)
#define DRM_DESTROY_WAITQUEUE(q) do{assert(!pthread_cond_destroy(q));}while(0)
#define DRM_SPIN_WAKEUP_ALL(q,l) do{(void)(l);assert(!pthread_cond_broadcast(q));}while(0)
#define DRM_SPIN_WAIT_NOINTR_UNTIL(e,q,l,c) \
 do{while(!(c)){assert(!pthread_cond_wait(q,l));}(e)=0;}while(0)
static int references,gets,ref_puts, fail_next_get;
static int nb_i915_vblank_ref_get_locked(struct drm_vblank_crtc *v) {
    (void)v;
    if (fail_next_get) {int e=fail_next_get;fail_next_get=0;return e;}
    references++;gets++;return 0;
}
static void nb_i915_vblank_ref_put_locked(struct drm_vblank_crtc *v) {
    (void)v;assert(references>0);references--;ref_puts++;
}
static unsigned drm_crtc_index(struct drm_crtc *c) {return c->idx;}
void drm_handle_vblank_works(struct drm_vblank_crtc *);
void drm_vblank_work_flush(struct drm_vblank_work *);
void drm_vblank_work_flush_all(struct drm_crtc *);
bool drm_vblank_work_cancel_sync(struct drm_vblank_work *);
struct launch {void (*fn)(void *);void *ctx;};
static void *entry(void *p) {
    struct launch item=*(struct launch*)p;free(p);
    item.fn(item.ctx);return NULL;
}
static int kthread_create(int pri,int options,void *unused,
    void (*func)(void *),void *cookie,struct lwp **thread,
    const char *name,unsigned pipe) {
    (void)pri;(void)options;(void)unused;(void)name;(void)pipe;
    struct launch *ctx=malloc(sizeof(*ctx));
    struct lwp *l=malloc(sizeof(*l));
    if (!ctx || !l) {free(ctx);free(l);return ENOMEM;}
    *ctx=(struct launch){func,cookie};
    int err=pthread_create(&l->tid,NULL,entry,ctx);
    if (err) {free(ctx);free(l);return err;}
    *thread=l;return 0;
}
static int kthread_join(struct lwp *l) {
    assert(l);int err=pthread_join(l->tid,NULL);free(l);return err;
}
#define kthread_exit(e) pthread_exit(NULL)
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_wake=PTHREAD_COND_INITIALIZER;
static int entered, release_callback;
static atomic_int callbacks,flushed;
static void simple(struct kthread_work *w) {
    (void)w;atomic_fetch_add(&callbacks,1);
}
static void blocked(struct kthread_work *w) {
    (void)w;
    pthread_mutex_lock(&gate);
    entered++;
    pthread_cond_broadcast(&gate_wake);
    while(!release_callback) pthread_cond_wait(&gate_wake,&gate);
    pthread_mutex_unlock(&gate);
    atomic_fetch_add(&callbacks,1);
}
static void gate_reset(void) {
    pthread_mutex_lock(&gate);entered=0;release_callback=0;pthread_mutex_unlock(&gate);
}
static void gate_entered(void) {
    pthread_mutex_lock(&gate);
    while(!entered) pthread_cond_wait(&gate_wake,&gate);
    pthread_mutex_unlock(&gate);
}
static void gate_release(void) {
    pthread_mutex_lock(&gate);release_callback=1;
    pthread_cond_broadcast(&gate_wake);pthread_mutex_unlock(&gate);
}
static void setup(struct drm_device *dev,struct drm_vblank_crtc *v,
    struct drm_crtc *crtc) {
    *dev=(struct drm_device){0};*v=(struct drm_vblank_crtc){0};
    assert(!pthread_mutex_init(&dev->event_lock,NULL));
    dev->vblank=v;v->dev=dev;v->pipe=0;v->count=10;
    *crtc=(struct drm_crtc){.dev=dev,.idx=0};
    references=gets=ref_puts=fail_next_get=0;
    atomic_store(&callbacks,0);atomic_store(&flushed,0);
}
struct job {struct drm_vblank_work *work; struct drm_crtc *crtc; bool all;bool cancel;bool cancelled;};
static void *wait_job(void *ptr) {
    struct job *job=ptr;
    if(job->cancel) job->cancelled=drm_vblank_work_cancel_sync(job->work);
    else if(job->all) drm_vblank_work_flush_all(job->crtc);
    else drm_vblank_work_flush(job->work);
    atomic_store(&flushed,1);
    return NULL;
}
static void simulate_irq(struct drm_vblank_crtc *v,u64 seq) {
    spin_lock(&v->dev->event_lock);
    v->count=seq;drm_handle_vblank_works(v);
    spin_unlock(&v->dev->event_lock);
}
"""

MAIN = r"""
int main(void) {
    alarm(12);
    struct drm_device d;
    struct drm_vblank_crtc v;
    struct drm_crtc c;
    struct drm_vblank_work a,b;
    struct job j;
    pthread_t waiter;

    setup(&d,&v,&c);
    assert(drm_vblank_worker_init(&v)==0);
    drm_vblank_work_init(&a,&c,simple);
    assert(drm_vblank_work_schedule(&a,12,false)==1);
    spin_lock(&d.event_lock);
    assert(references==1 && a.pending_ref && !list_empty(&v.pending_work));
    spin_unlock(&d.event_lock);
    j=(struct job){.work=&a,.crtc=&c};
    assert(!pthread_create(&waiter,NULL,wait_job,&j));
    simulate_irq(&v,12);
    assert(!pthread_join(waiter,NULL));
    spin_lock(&d.event_lock);
    assert(references==0 && atomic_load(&callbacks)==1 && !a.running);
    spin_unlock(&d.event_lock);
    puts("VBLANK_PTHREAD_PENDING_IRQ_FLUSH_OK");

    gate_reset();atomic_store(&flushed,0);
    drm_vblank_work_init(&b,&c,blocked);
    assert(drm_vblank_work_schedule(&b,12,false)==1);
    gate_entered();
    j=(struct job){.crtc=&c,.all=true};
    assert(!pthread_create(&waiter,NULL,wait_job,&j));
    assert(atomic_load(&flushed)==0);
    gate_release();
    assert(!pthread_join(waiter,NULL));
    assert(atomic_load(&flushed)==1);
    puts("VBLANK_PTHREAD_RUNNING_ALL_FLUSH_FENCE_OK");

    gate_reset();atomic_store(&flushed,0);
    drm_vblank_work_init(&b,&c,blocked);
    assert(drm_vblank_work_schedule(&b,12,false)==1);
    gate_entered();
    j=(struct job){.work=&b,.cancel=true};
    assert(!pthread_create(&waiter,NULL,wait_job,&j));
    gate_release();
    assert(!pthread_join(waiter,NULL));
    assert(!j.cancelled);
    spin_lock(&d.event_lock);
    assert(references==0);
    spin_unlock(&d.event_lock);
    puts("VBLANK_PTHREAD_RUNNING_CANCEL_JOIN_OK");

    drm_vblank_work_init(&a,&c,simple);
    assert(drm_vblank_work_schedule(&a,999,false)==1);
    assert(drm_vblank_work_cancel_sync(&a));
    spin_lock(&d.event_lock);
    assert(references==0 && !a.pending_ref && list_empty(&v.pending_work));
    spin_unlock(&d.event_lock);
    puts("VBLANK_PTHREAD_PENDING_CANCEL_REF_DROP_OK");

    fail_next_get=-ENOMEM;
    assert(drm_vblank_work_schedule(&a,999,false)==-ENOMEM);
    spin_lock(&d.event_lock);
    assert(references==0 && !a.pending_ref && list_empty(&a.node));
    spin_unlock(&d.event_lock);
    puts("VBLANK_PTHREAD_FAILED_IRQ_REF_GET_OK");

    assert(drm_vblank_work_schedule(&a,999,false)==1);
    drm_vblank_worker_fini(&v);
    assert(!v.work_thread && v.worker_stopping);
    spin_lock(&d.event_lock);
    assert(references==0 && !a.pending_ref && list_empty(&v.pending_work));
    spin_unlock(&d.event_lock);
    assert(drm_vblank_work_schedule(&a,999,false)==0);
    assert(gets==ref_puts);
    assert(!pthread_mutex_destroy(&d.event_lock));
    puts("VBLANK_PTHREAD_TEARDOWN_QUIESCENCE_OK");
    return 0;
}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-c", type=Path, required=True)
    args = parser.parse_args()
    data = args.provider_c.read_bytes()
    if hashlib.sha256(data).hexdigest() != PINNED_SHA256:
        raise AssertionError("native provider source hash changed")
    source = data.decode("utf-8")
    methods = "\n\n".join(extract(source, name) for name in METHODS)
    with tempfile.TemporaryDirectory(prefix="i915-vblank-thread-") as t:
        root = Path(t)
        c = root / "fixture.c"
        executable = root / "fixture"
        c.write_text(PRELUDE + "\n" + methods + "\n" + MAIN)
        build = subprocess.run(
            ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-omit-frame-pointer", "-pthread",
             str(c), "-o", str(executable)], capture_output=True, text=True)
        if build.returncode:
            raise AssertionError("native function mock C compile failed:\n" +
                                 build.stderr[:2800])
        run = subprocess.run([str(executable)], capture_output=True,
                             text=True, timeout=18)
        if run.returncode:
            raise AssertionError("source-extracted threaded fixture failed (" +
                                 str(run.returncode) + "): " +
                                 run.stdout[-1200:] + "\n" + run.stderr[-1500:])
        expected = [
            "VBLANK_PTHREAD_PENDING_IRQ_FLUSH_OK",
            "VBLANK_PTHREAD_RUNNING_ALL_FLUSH_FENCE_OK",
            "VBLANK_PTHREAD_RUNNING_CANCEL_JOIN_OK",
            "VBLANK_PTHREAD_PENDING_CANCEL_REF_DROP_OK",
            "VBLANK_PTHREAD_FAILED_IRQ_REF_GET_OK",
            "VBLANK_PTHREAD_TEARDOWN_QUIESCENCE_OK",
        ]
        for label in expected:
            if label not in run.stdout:
                raise AssertionError("missing runtime case " + label)
        print(run.stdout.strip())
        print("I915_NETBSD_VBLANK_EXTRACTED_C11_PTHREAD_6_LIFECYCLE_CASES_PASS")
        print("LIMIT: host pthread substitutions, not a NetBSD HP native kernel/IRQ test")


if __name__ == "__main__":
    main()
