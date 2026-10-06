#!/usr/bin/env python3
"""Test production object allocators on HP with an explicit kmem ledger model.

The whole production slab/overflow headers are included. Pool/RCU/VM models
only permit parsing and are not exercised or claimed as implementations.
Separate real native kernel header/object compilation is required.
"""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import tempfile

KMEM=r'''
#ifndef MODEL_KMEM_H
#define MODEL_KMEM_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/param.h>
#include <sys/bitops.h>
#define ISSET(value,mask) ((value)&(mask)) /* native kernel bit-mask model */
#define KM_SLEEP 1
#define KM_NOSLEEP 2
#define CACHE_LINE_SIZE 64
#define PR_PSERIALIZE 4
#define PR_WAITOK 8
#define PR_NOWAIT 16
typedef void *pool_cache_t;
void *pool_cache_init(size_t,size_t,size_t,int,const char *,void *,int,
 int (*)(void *,void *,int),void (*)(void *,void *),void *);
void pool_cache_destroy(pool_cache_t);
void *pool_cache_get(pool_cache_t,int);
void pool_cache_put(pool_cache_t,void *);
void pool_cache_reclaim(pool_cache_t);
struct model_allocation { void *ptr; size_t size; };
static struct model_allocation ledger[32];
static unsigned allocation_calls,free_calls,last_flags,live_allocations;
static bool fail_next;
static void *model_alloc(size_t size,int flags,bool zero){
 allocation_calls++;last_flags=(unsigned)flags;
 if(fail_next){fail_next=false;return NULL;}
 assert(size<1024*1024);
 void *p=malloc(size);assert(p);memset(p,zero?0:0xa5,size);
 unsigned slot;for(slot=0;slot<32 && ledger[slot].ptr;slot++);
 assert(slot<32);ledger[slot]=(struct model_allocation){p,size};live_allocations++;
 return p;
}
static void model_free(void *p,size_t size){
 unsigned slot;for(slot=0;slot<32 && ledger[slot].ptr!=p;slot++);
 assert(slot<32 && ledger[slot].size==size);ledger[slot].ptr=NULL;
 free_calls++;live_allocations--;free(p);
}
static inline void *kmem_intr_alloc(size_t n,int f){return model_alloc(n,f,false);}
static inline void *kmem_intr_zalloc(size_t n,int f){return model_alloc(n,f,true);}
static inline void kmem_intr_free(void *p,size_t n){model_free(p,n);}
static inline void *kmem_alloc(size_t n,int f){return model_alloc(n,f,false);}
static inline void kmem_free(void *p,size_t n){model_free(p,n);}
#endif
'''

C=r'''
#include <linux/slab.h>
struct item { uint64_t value; unsigned char data[16]; };
static unsigned expression_calls;
static struct item *unevaluated(void){expression_calls++;return NULL;}
static uint64_t rng=0x243f6a8885a308d3ULL;
static uint64_t next(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static void bytes(const void *p,size_t n,unsigned char value){
 const unsigned char *b=p;for(size_t i=0;i<n;i++)assert(b[i]==value);
}
int main(void){
 assert(default_gfp()==GFP_KERNEL && default_gfp(GFP_ATOMIC)==GFP_ATOMIC);
 for(unsigned i=0;i<20000;i++){
  size_t a=(size_t)next(),b=(size_t)next();
  __uint128_t mul=(__uint128_t)a*b,add=(__uint128_t)a+b;
  assert(size_mul(a,b)==(mul>SIZE_MAX?SIZE_MAX:(size_t)mul));
  assert(size_add(a,b)==(a==SIZE_MAX || b==SIZE_MAX || add>SIZE_MAX?SIZE_MAX:(size_t)add));
  assert(size_sub(a,b)==(a==SIZE_MAX || b==SIZE_MAX || a<b?SIZE_MAX:a-b));
 }
 assert(size_mul(SIZE_MAX,0)==0 && size_mul(0,SIZE_MAX)==0);
 assert(size_add(SIZE_MAX,0)==SIZE_MAX && size_sub(SIZE_MAX,SIZE_MAX)==SIZE_MAX);
 assert(size_sub(0,1)==SIZE_MAX && size_sub(4,4)==0);
 struct item *p=kmalloc_obj(struct item);
 _Static_assert(__builtin_types_compatible_p(__typeof__(p),struct item *),"typed object");
 assert(p && last_flags==KM_SLEEP && ((uintptr_t)p%__alignof__(struct item))==0);
 bytes(p,sizeof(*p),0xa5);kfree(p);
 p=kzalloc_obj(*unevaluated());assert(p && expression_calls==0);bytes(p,sizeof(*p),0);kfree(p);
 p=kmalloc_obj(struct item,GFP_ATOMIC);assert(p && last_flags==KM_NOSLEEP);kfree(p);
 unsigned count=0,flag_calls=0;
 p=kzalloc_objs(struct item,++count,(flag_calls++,GFP_NOWAIT));
 assert(p && count==1 && flag_calls==1 && last_flags==KM_NOSLEEP);bytes(p,sizeof(*p),0);kfree(p);
 for(size_t n=1;n<=64;n++){
  p=kmalloc_objs(struct item,n);assert(p);bytes(p,sizeof(*p)*n,0xa5);kfree(p);
  p=kzalloc_objs(*p,n);assert(p);bytes(p,sizeof(*p)*n,0);kfree(p);
 }
 unsigned before=allocation_calls;
 assert(kmalloc_objs(struct item,SIZE_MAX/sizeof(struct item)+1)==NULL);
 assert(kzalloc_objs(struct item,SIZE_MAX)==NULL);
 assert(kmalloc(SIZE_MAX,GFP_KERNEL)==NULL);
 assert(kzalloc(SIZE_MAX-sizeof(struct linux_malloc),GFP_KERNEL)==NULL);
 assert(allocation_calls==before && live_allocations==0);
 fail_next=true;assert(kzalloc_obj(struct item,GFP_NOWAIT)==NULL && !fail_next);
 p=kmalloc_obj(struct item);memset(p,0x3c,sizeof(*p));
 unsigned frees=free_calls;before=allocation_calls;
 assert(krealloc(p,SIZE_MAX,GFP_KERNEL)==NULL);
 assert(free_calls==frees && allocation_calls==before && live_allocations==1);bytes(p,sizeof(*p),0x3c);
 fail_next=true;assert(krealloc(p,sizeof(*p)*2,GFP_NOWAIT)==NULL);
 assert(free_calls==frees && live_allocations==1);bytes(p,sizeof(*p),0x3c);
 void *grown=krealloc(p,sizeof(*p)*2,GFP_KERNEL|__GFP_ZERO);assert(grown);
 bytes(grown,sizeof(*p),0x3c);bytes((unsigned char *)grown+sizeof(*p),sizeof(*p),0);
 assert(free_calls==frees+1 && live_allocations==1);
 void *shrunk=krealloc(grown,8,GFP_KERNEL);assert(shrunk);bytes(shrunk,8,0x3c);kfree(shrunk);
 void *from_null=krealloc(NULL,16,GFP_KERNEL|__GFP_ZERO);assert(from_null);bytes(from_null,16,0);kfree(from_null);
 before=free_calls;kfree(NULL);assert(free_calls==before && live_allocations==0);
 return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',action='store_true');a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking tests are HP/NetBSD only')
    stage=Path('/root/hp-driver-port-20261005/netbsd-full-linux/sys/external/bsd/common/include/linux')
    with tempfile.TemporaryDirectory(prefix='i915-typed-alloc-') as name:
        t=Path(name)
        for rel in ['linux','sys','lib/libkern','uvm']:(t/rel).mkdir(parents=True)
        (t/'sys/kmem.h').write_text(KMEM)
        (t/'lib/libkern/libkern.h').write_text('#include <stddef.h>\n#define KASSERT(e) assert(e)\n#define KASSERTMSG(e,...) assert(e)\n#define CTASSERT(e) _Static_assert(e,#e)\n')
        (t/'uvm/uvm_extern.h').write_text('#define PAGE_SIZE 4096\n#define IPL_VM 5\n')
        (t/'linux/rcupdate.h').write_text('/* Explicit parsing-only RCU model; no RCU path is executed. */\n')
        (t/'linux/compiler.h').write_text('#include <linux/compiler_attributes.h>\n')
        headers=['slab.h','overflow.h','gfp.h','size_arithmetic.h','typed_alloc.h','compiler_attributes.h']
        for h in headers:
            if a.baseline and h in ['slab.h','overflow.h','gfp.h']:
                data=subprocess.check_output(['git','-C','/root/netbsd-src-ref','show',
                    '03d918f6d0e81fa05b8f1160eca0628ad39988a6:sys/external/bsd/common/include/linux/'+h])
            elif a.baseline and h in ['size_arithmetic.h','typed_alloc.h']:continue
            else:data=(stage/h).read_bytes()
            (t/'linux'/h).write_bytes(data)
        src=t/'test.c';src.write_text(C);exe=t/'test'
        flags=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(t)]
        subprocess.run(flags+[str(src),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
    print('LINUX_TYPED_ALLOC_OK: 20K wide size oracles, typed/default-GFP/one-evaluation/zero-fill, overflow and failure ownership')

if __name__=='__main__':main()
