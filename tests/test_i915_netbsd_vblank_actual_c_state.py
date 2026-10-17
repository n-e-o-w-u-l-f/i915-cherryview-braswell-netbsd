#!/usr/bin/env python3
"""Compile and exercise selected actual NetBSD VBlank provider C state handlers.

Mocks IRQ primitives and hardware; does NOT establish real kernel timing.
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

NAMES=("nb_vblank_passed","nb_vblank_ready",
       "drm_vblank_cancel_pending_works","drm_handle_vblank_works",
       "drm_vblank_work_init","drm_vblank_work_schedule",
       "drm_vblank_work_cancel_sync")

def extract(src,name):
    pattern=r"(?m)^(?:static\s+)?(?:struct drm_crtc\s*\*|bool|void|int)\s*\n"+re.escape(name)+r"\("
    match=re.search(pattern,src)
    assert match,name
    begin=src.index("{",match.end())
    depth=0
    for i in range(begin,len(src)):
        if src[i]=="{":depth+=1
        elif src[i]=="}":
            depth-=1
            if not depth:return src[match.start():i+1]
    raise AssertionError("unclosed "+name)

MOCK=r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint64_t u64;
struct list_head { struct list_head *next,*prev; };
#define container_of(ptr,ty,member) ((ty *)((char *)(ptr)-offsetof(ty,member)))
#define INIT_LIST_HEAD(h) do{(h)->next=(h);(h)->prev=(h);}while(0)
static inline bool list_empty(const struct list_head *h){return h->next==h;}
static inline void list_add_tail(struct list_head *p,struct list_head *h){
 p->next=h;p->prev=h->prev;h->prev->next=p;h->prev=p;
}
static inline void list_del_init(struct list_head *p){
 p->next->prev=p->prev;p->prev->next=p->next;INIT_LIST_HEAD(p);
}
#define list_for_each_entry_safe(p,n,head,member) \
 for(struct list_head *__it=(head)->next,*__next; \
 __it!=(head) && ((__next=__it->next),\
 (p)=container_of(__it,__typeof__(*(p)),member), \
 (n)=(__next==(head)?NULL:container_of(__next,__typeof__(*(n)),member)),true); \
 __it=__next)
struct kthread_work{void(*func)(struct kthread_work *);};
struct drm_vblank_crtc;
struct drm_vblank_work{
 struct kthread_work base;
 struct drm_vblank_crtc *vblank;
 u64 count;int cancelling;struct list_head node;
 bool pending_ref,running;
};
struct drm_device{int event_lock;struct drm_vblank_crtc *vblank;};
struct drm_crtc{struct drm_device *dev;unsigned index;};
struct drm_vblank_crtc{
 struct drm_device *dev;unsigned pipe;
 u64 count;unsigned inmodeset;
 bool worker_stopping,worker_running;
 struct list_head pending_work,ready_work;
 int work_wait_queue,worker_wait_queue;
};
static struct drm_crtc g_crtc;
static int refs,gets,put_calls,fail_get;
static unsigned drm_crtc_index(struct drm_crtc *c){return c->index;}
static int nb_i915_vblank_ref_get_locked(struct drm_vblank_crtc *c){
 (void)c;
 if(fail_get){int err=fail_get;fail_get=0;return err;}
 refs++;gets++;return 0;
}
static void nb_i915_vblank_ref_put_locked(struct drm_vblank_crtc *c){
 (void)c;if(refs<=0)abort();refs--;put_calls++;
}
static bool spin_is_locked(int *l){return *l>0;}
#define spin_lock_irqsave(l,f) do{(f)=0;(*(l))++;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);(*(l))--;}while(0)
#define KASSERT(x) do{if(!(x))abort();}while(0)
#define DRM_SPIN_WAKEUP_ALL(q,l) do{(void)(q);(void)(l);}while(0)
#define DRM_SPIN_WAIT_NOINTR_UNTIL(e,q,l,cond) do{(void)(q);(void)(l);if(!(cond))abort();(e)=0;}while(0)
#define atomic64_read(p) (*(p))
"""
MAIN=r"""
static void dummy(struct kthread_work *w){(void)w;}
static void setup(struct drm_device *d,struct drm_vblank_crtc *v,u64 count){
 *d=(struct drm_device){0};*v=(struct drm_vblank_crtc){0};
 g_crtc=(struct drm_crtc){.dev=d,.index=0};d->vblank=v;
 v->dev=d;v->count=count;INIT_LIST_HEAD(&v->pending_work);
 INIT_LIST_HEAD(&v->ready_work);
 gets=0;put_calls=0;refs=0;fail_get=0;
}
#define CHECK(n,test) do{if(!(test)){fprintf(stderr,"case %d failed\n",n);return n;}}while(0)
int main(void){
 struct drm_device dev;struct drm_vblank_crtc v;
 struct drm_vblank_work a,b;
 setup(&dev,&v,10);drm_vblank_work_init(&a,&g_crtc,dummy);
 CHECK(1,drm_vblank_work_schedule(&a,12,false)==1 && refs==1 && a.pending_ref);
 CHECK(2,drm_vblank_work_schedule(&a,12,false)==0 && refs==1);
 CHECK(3,drm_vblank_work_schedule(&a,13,false)==1 && refs==1 && a.count==13);
 dev.event_lock++;v.count=12;drm_handle_vblank_works(&v);dev.event_lock--;
 CHECK(4,list_empty(&v.ready_work) && !list_empty(&v.pending_work) && refs==1);
 dev.event_lock++;v.count=13;drm_handle_vblank_works(&v);dev.event_lock--;
 CHECK(5,list_empty(&v.pending_work) && !list_empty(&v.ready_work) && refs==0);
 CHECK(6,drm_vblank_work_cancel_sync(&a) && list_empty(&a.node) && refs==0);
 CHECK(7,drm_vblank_work_schedule(&a,8,false)==1 && refs==0 && !list_empty(&v.ready_work));
 CHECK(8,drm_vblank_work_cancel_sync(&a) && list_empty(&v.ready_work));
 CHECK(9,drm_vblank_work_schedule(&a,8,true)==1 && a.count==14 && refs==1);
 CHECK(10,drm_vblank_work_cancel_sync(&a) && refs==0 && list_empty(&v.pending_work));
 fail_get=-EIO;
 CHECK(11,drm_vblank_work_schedule(&a,15,false)==-EIO && refs==0 && list_empty(&a.node));
 a.cancelling=1;
 CHECK(12,drm_vblank_work_schedule(&a,15,false)==0 && refs==0);
 a.cancelling=0;v.worker_stopping=true;
 CHECK(13,drm_vblank_work_schedule(&a,15,false)==0 && refs==0);
 v.worker_stopping=false;v.inmodeset=1;
 CHECK(14,drm_vblank_work_schedule(&a,15,false)==0 && refs==0);
 v.inmodeset=0;drm_vblank_work_init(&b,&g_crtc,dummy);
 CHECK(15,drm_vblank_work_schedule(&a,17,false)==1 &&
          drm_vblank_work_schedule(&b,18,false)==1 && refs==2);
 dev.event_lock++;v.count=17;drm_handle_vblank_works(&v);dev.event_lock--;
 CHECK(16,refs==1 && !list_empty(&v.ready_work));
 dev.event_lock++;drm_vblank_cancel_pending_works(&v);dev.event_lock--;
 CHECK(17,refs==0 && list_empty(&v.pending_work));
 CHECK(18,drm_vblank_work_cancel_sync(&a) && !drm_vblank_work_cancel_sync(&b));
 CHECK(19,nb_vblank_passed(0,UINT64_MAX) && !nb_vblank_passed(UINT64_MAX,0));
 CHECK(20,refs==0 && gets==put_calls);
 /* CRTC already freed: native DRM VBlank core must still release IRQ refs. */
 v.count=19;
 CHECK(21,drm_vblank_work_schedule(&a,21,false)==1 && refs==1);
 g_crtc.dev=NULL;
 dev.event_lock++;drm_vblank_cancel_pending_works(&v);dev.event_lock--;
 CHECK(22,refs==0 && list_empty(&v.pending_work));
 puts("NETBSD_I915_VBLANK_22_SOURCE_STATE_CASES_PASS");
 return 0;
}
"""

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--provider-c",type=Path,required=True)
    o=arg.parse_args()
    src=o.provider_c.read_text()
    assert "kthread_join(vblank->work_thread)" in src
    assert "DRM_SPIN_WAIT_NOINTR_UNTIL" in src
    unit=MOCK+"\n".join(extract(src,n) for n in NAMES)+MAIN
    with tempfile.TemporaryDirectory(prefix="netbsd-vblank-pinned-functions-") as td:
        c=Path(td)/"test.c";c.write_text(unit)
        exe=Path(td)/"test"
        cc=subprocess.run(["cc","-std=gnu11","-Wall","-Wextra","-Werror",str(c),"-o",str(exe)],capture_output=True,text=True,timeout=30)
        assert cc.returncode==0,cc.stderr
        test=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        assert test.returncode==0,(test.returncode,test.stdout,test.stderr)
        print(test.stdout.strip())
        print("C fixture only; actual IRQ/kthread timing remains unverified")

if __name__=="__main__":
    main()
