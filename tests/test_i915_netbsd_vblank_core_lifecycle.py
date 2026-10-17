#!/usr/bin/env python3
"""Pinned real NetBSD VBlank core initializer/cleanup fault injection in C."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

PINS = {
 "dist/include/drm/drm_vblank.h": "41a6574745795608b43bec288f04f0ae622271e604ff8b6e6d894e754acc37a9",
 "dist/drm/drm_vblank.c": "06434bfc9f6693a1b61069c5c0e839b24671a5ba4d826fb001b0a897ceac206e",
 "drm/files.drmkms": "e507627bf8a6219ff38a79a2c6cebc98b1ee61540d354ce0eb15d2ee77785cb3",
}
def method(c,name):
    m=re.search(r"(?m)^(?:int|void)\s+"+name+r"\s*\(",c)
    assert m,name
    start=m.start();at=c.index("{",m.end());level=0
    for i in range(at,len(c)):
        if c[i]=="{":level+=1
        if c[i]=="}":
            level-=1
            if level==0:return c[start:i+1]
    raise ValueError(name)

PRE=r"""
#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include <errno.h>
struct drm_device;
struct drm_vblank_crtc {
 struct drm_device *dev;unsigned pipe;bool enabled;
 int queue,disable_timer,seqlock;bool worker_live;
};
struct drm_driver{bool get_vblank_timestamp;};
struct drm_device{
 unsigned num_crtcs;struct drm_vblank_crtc *vblank;
 int vblank_time_lock;bool vblank_disable_immediate;
 struct drm_driver *driver;
};
#define GFP_KERNEL 0
#define DRIVER_MODESET 1
#define WARN_ON(x) ((void)(x))
#define READ_ONCE(x) (x)
#define DRM_INFO(...) ((void)0)
static int li,lf,qi,qf,ti,tf,si,sf,wi,wf,ha,hf,failed,failalloc;
static void spin_lock_init(int *x){(void)x;li++;}
static void spin_lock_destroy(int *x){(void)x;lf++;}
static void DRM_INIT_WAITQUEUE(int *x,const char *s){(void)s;*x=1;qi++;}
static void DRM_DESTROY_WAITQUEUE(int *x){if(*x!=1)abort();*x=0;qf++;}
static void timer_setup(int *x,void(*f)(int *),int t)
{(void)f;(void)t;*x=1;ti++;}
static void del_timer_sync(int *x){if(*x!=1)abort();*x=0;tf++;}
static void seqlock_init(int *x){*x=1;si++;}
static void seqlock_destroy(int *x){if(*x!=1)abort();*x=0;sf++;}
static void vblank_disable_fn(int *x){(void)x;}
static int drm_core_check_feature(struct drm_device *d,int m)
{(void)d;(void)m;return 0;}
static void *kcalloc(size_t a,size_t b,int flags)
{(void)flags;if(failalloc)return NULL;ha++;return calloc(a,b);}
static void kfree(void *ptr){hf++;free(ptr);}
static int drm_vblank_worker_init(struct drm_vblank_crtc *v)
{wi++;if((int)v->pipe==failed)return -ENOMEM;v->worker_live=true;return 0;}
static void drm_vblank_worker_fini(struct drm_vblank_crtc *v)
{if(!v->worker_live)abort();v->worker_live=false;wf++;}
static void clear_state(int fail){
 li=lf=qi=qf=ti=tf=si=sf=wi=wf=ha=hf=0;
 failed=fail;failalloc=0;
}
#define ASSERT(x) do{if(!(x)){fprintf(stderr,"FAILED %s:%d %s\n",__FILE__,__LINE__,#x);abort();}}while(0)
"""
POST=r"""
int main(void){
 struct drm_driver drv={0};struct drm_device d={0};
 clear_state(-1);d.driver=&drv;
 ASSERT(drm_vblank_init(&d,2)==0 && d.num_crtcs==2);
 ASSERT(qi==2 && ti==2 && si==2 && wi==2);
 drm_vblank_cleanup(&d);
 ASSERT(qf==2 && tf==2 && sf==2 && wf==2);
 ASSERT(ha==1 && hf==1 && li==1 && lf==1 && d.vblank==NULL && d.num_crtcs==0);
 clear_state(1);d=(struct drm_device){.driver=&drv};
 ASSERT(drm_vblank_init(&d,2)==-ENOMEM);
 ASSERT(qi==qf && qi==2 && ti==tf && ti==2 && si==sf && si==2);
 ASSERT(wi==2 && wf==1 && ha==hf && ha==1 && li==lf && li==1);
 ASSERT(d.vblank==NULL && d.num_crtcs==0);
 clear_state(0);d=(struct drm_device){.driver=&drv};
 ASSERT(drm_vblank_init(&d,2)==-ENOMEM);
 ASSERT(qi==qf && qi==1 && ti==tf && ti==1 && si==sf && si==1);
 ASSERT(wi==1 && wf==0 && ha==hf && ha==1 && li==lf && li==1);
 ASSERT(d.vblank==NULL && d.num_crtcs==0);
 clear_state(-1);failalloc=1;d=(struct drm_device){.driver=&drv};
 ASSERT(drm_vblank_init(&d,2)==-ENOMEM);
 ASSERT(qi==qf && ti==tf && si==sf && wi==wf && ha==hf);
 ASSERT(li==lf && li==1 && d.vblank==NULL && d.num_crtcs==0);
 puts("NETBSD_I915_VBLANK_NATIVE_CORE_LIFECYCLE_4_SCENARIOS_PASS");
 return 0;
}
"""
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--netbsd-drm2",type=Path,required=True)
    a.add_argument("--patch",type=Path,required=True)
    opt=a.parse_args()
    with tempfile.TemporaryDirectory(prefix="native-vblank-lifecycle-test-") as td:
        temp=Path(td)
        for name,digest in PINS.items():
            original=(opt.netbsd_drm2/name).read_bytes()
            assert hashlib.sha256(original).hexdigest()==digest,name
            dest=temp/"sys/external/bsd/drm2"/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(original)
        run=subprocess.run(["patch","-s","-p1","-d",str(temp),"-i",str(opt.patch)],capture_output=True,text=True,timeout=20)
        assert run.returncode==0,run.stderr
        c=(temp/"sys/external/bsd/drm2/dist/drm/drm_vblank.c").read_text()
        assert "nb_i915_vblank_ref_put_locked" in c
        source=PRE+method(c,"drm_vblank_cleanup")+method(c,"drm_vblank_init")+POST
        p=temp/"test.c";p.write_text(source)
        exe=temp/"test"
        compile=subprocess.run(["cc","-std=gnu11","-Wall","-Wextra","-Werror",str(p),"-o",str(exe)],capture_output=True,text=True,timeout=25)
        assert compile.returncode==0,compile.stderr
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
        print(result.stdout.strip())

if __name__=="__main__":
    main()
