#!/usr/bin/env python3
"""Execute the full production completion header over an instrumented native CV model.

Tests lock/delegation, saturating claims, clock wrap, sliced large budgets and
signal/deadline races. Physical scheduler/FIFO/fatal-signal/IO/lifetime acceptance
remains a separate native integration gate.
"""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import tempfile

C=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <linux/completion.h>
struct event {unsigned int elapsed;int error;bool done;};
static struct event events[8];static unsigned int count,pos,clock_ticks,signals,broadcasts;static struct completion *active;
unsigned int getticks(void){return clock_ticks;}
int model_wait(kcondvar_t *cv,kmutex_t *m,int ticks,bool intr){
 (void)cv;(void)intr;assert(m->held && ticks>0 && ticks<=INT_MAX/2 && pos<count);
 struct event e=events[pos++];clock_ticks+=e.elapsed;if(e.done)active->c_done=1;return e.error;
}
int cv_timedwait(kcondvar_t *cv,kmutex_t *m,int t){return model_wait(cv,m,t,false);}
int cv_timedwait_sig(kcondvar_t *cv,kmutex_t *m,int t){return model_wait(cv,m,t,true);}
void cv_signal(kcondvar_t *cv){assert(cv->initialized);signals++;}
void cv_broadcast(kcondvar_t *cv){assert(cv->initialized);broadcasts++;}
int cv_wait_sig(kcondvar_t *cv,kmutex_t *m){return model_wait(cv,m,1,true);}
void cv_wait(kcondvar_t *cv,kmutex_t *m){assert(model_wait(cv,m,1,false)==0);}
static void setup(struct completion *c){init_completion(c);active=c;count=pos=0;clock_ticks=0;}
int main(void){
 struct completion c;setup(&c);assert(!completion_done(&c) && !try_wait_for_completion(&c));
 complete(&c);complete(&c);assert(c.c_done==2 && signals==2 && completion_done(&c));assert(try_wait_for_completion(&c) && c.c_done==1);assert(wait_for_completion_timeout(&c,0)==1 && c.c_done==0);assert(wait_for_completion_timeout(&c,0)==0);
 c.c_done=INT_MAX;complete(&c);assert((uint64_t)c.c_done==(uint64_t)INT_MAX+1);
 c.c_done=UINT_MAX-1;complete(&c);complete(&c);assert(c.c_done==UINT_MAX);assert(try_wait_for_completion(&c) && try_wait_for_completion(&c) && c.c_done==UINT_MAX);
 complete_all(&c);assert(broadcasts==1);reinit_completion(&c);assert(!completion_done(&c));
 c.c_done=1;assert(wait_for_completion_timeout(&c,(unsigned long)INT_MAX+123)==(unsigned long)INT_MAX+123 && pos==0);
 events[0]=(struct event){INT_MAX/2,EWOULDBLOCK,false};events[1]=(struct event){7,0,true};count=2;
 unsigned long budget=(unsigned long)INT_MAX/2+23;assert(wait_for_completion_timeout(&c,budget)==16 && pos==2 && c.c_done==0);
 clock_ticks=UINT_MAX-3;events[0]=(struct event){8,0,true};pos=0;count=1;assert(wait_for_completion_timeout(&c,17)==9 && clock_ticks==4);
 events[0]=(struct event){5,EWOULDBLOCK,true};pos=0;count=1;assert(wait_for_completion_timeout(&c,5)==1);
 events[0]=(struct event){3,EINTR,false};pos=0;count=1;assert(wait_for_completion_interruptible_timeout(&c,7)==-ERESTARTSYS && c.c_done==0);
 events[0]=(struct event){3,EINTR,true};pos=0;count=1;assert(wait_for_completion_interruptible_timeout(&c,7)==4 && c.c_done==0);
 events[0]=(struct event){0,EWOULDBLOCK,false};pos=0;count=1;assert(wait_for_completion_timeout(&c,4)==0);
 events[0]=(struct event){2,0,false};events[1]=(struct event){4,0,true};pos=0;count=2;assert(wait_for_completion_timeout(&c,10)==4 && pos==2);
 _Static_assert(__builtin_types_compatible_p(__typeof__(wait_for_completion_timeout(&c,1)),unsigned long),"timeout ABI");
 _Static_assert(__builtin_types_compatible_p(__typeof__(wait_for_completion_interruptible_timeout(&c,1)),long),"interruptible timeout ABI");
 assert(!c.c_lock.held);destroy_completion(&c);return 0;
}
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',action='store_true');a=p.parse_args()
 if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):p.error('compiler-invoking tests are HP/NetBSD only')
 stage=Path('/root/hp-driver-port-20261005/netbsd-full-linux');rel='sys/external/bsd/common/include/linux/completion.h'
 with tempfile.TemporaryDirectory(prefix='i915-completion-') as name:
  t=Path(name);header=t/'linux/completion.h';header.parent.mkdir(parents=True)
  data=subprocess.check_output(['git','-C','/root/netbsd-src-ref','show','HEAD:'+rel],text=True) if a.baseline else (stage/rel).read_text();header.write_text(data)
  for n in ['types','param','kernel','condvar','mutex']:
   q=t/'sys'/(n+'.h');q.parent.mkdir(parents=True,exist_ok=True);q.write_text('#include "model.h"\n')
  q=t/'machine/limits.h';q.parent.mkdir(parents=True);q.write_bytes(subprocess.check_output(['git','-C','/root/netbsd-src-ref','show','HEAD:sys/arch/amd64/include/limits.h']))
  native_errno=subprocess.check_output(['git','-C','/root/netbsd-src-ref','show','HEAD:sys/sys/errno.h'],text=True)
  restart=next(l for l in native_errno.splitlines() if l.startswith('#define') and 'ERESTART' in l)
  (t/'linux/errno.h').write_text('#include <errno.h>\n'+restart+'\n#ifndef ERESTARTSYS\n#define ERESTARTSYS 512\n#endif\n')
  (t/'sys/model.h').write_text('''#ifndef MODEL_H
#define MODEL_H
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <limits.h>
#define KASSERT(X) assert(X)
#define KASSERTMSG(X,...) assert(X)
#define MIN(A,B) ((A)<(B)?(A):(B))
#define MAX(A,B) ((A)>(B)?(A):(B))
#define MUTEX_DEFAULT 0
#define IPL_SCHED 1
typedef struct {bool initialized,held;} kmutex_t;
typedef struct {bool initialized;} kcondvar_t;
static inline void mutex_init(kmutex_t *m,int type,int ipl){assert(type==MUTEX_DEFAULT && ipl==IPL_SCHED);m->initialized=true;m->held=false;}
static inline void mutex_enter(kmutex_t *m){assert(m->initialized && !m->held);m->held=true;}
static inline void mutex_exit(kmutex_t *m){assert(m->held);m->held=false;}
static inline bool mutex_owned(kmutex_t *m){return m->held;}
static inline void mutex_destroy(kmutex_t *m){assert(m->initialized && !m->held);m->initialized=false;}
static inline void cv_init(kcondvar_t *c,const char *n){(void)n;c->initialized=true;}
static inline bool cv_has_waiters(kcondvar_t *c){assert(c->initialized);return false;}
static inline void cv_destroy(kcondvar_t *c){assert(c->initialized);c->initialized=false;}
unsigned int getticks(void);void cv_signal(kcondvar_t *);void cv_broadcast(kcondvar_t *);int cv_timedwait(kcondvar_t *,kmutex_t *,int);int cv_timedwait_sig(kcondvar_t *,kmutex_t *,int);int cv_wait_sig(kcondvar_t *,kmutex_t *);void cv_wait(kcondvar_t *,kmutex_t *);
#endif
''')
  src=t/'test.c';src.write_text(C);exe=t/'test';subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(t),str(src),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
 print('LINUX_COMPLETION_OK: saturating counter, timeout widths/slices, clock wrap, signal/deadline races and native lock/CV delegation')

if __name__=='__main__':main()
