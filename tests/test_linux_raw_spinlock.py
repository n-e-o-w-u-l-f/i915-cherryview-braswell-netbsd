#!/usr/bin/env python3
"""Check production raw-lock delegation/IPL order with an instrumented OS model.

The model observes lock state and saved priority through success, contention,
nesting and side-effecting macro arguments. It does not execute kernel locks
or claim SMP/panic lifetime acceptance. Compiler execution is HP-only.
"""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import tempfile

C=r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <linux/raw_spinlock.h>
static int priority=3, seq[128], used, spin_active;
static kmutex_t *expected;
static int fail_try;
enum { INIT=1, HIGH, ENTER, EXIT, TRY, RESTORE, DESTROY };
int splhigh(void) { int old=priority; priority=IPL_HIGH;seq[used++]=HIGH;return old; }
void splx(int v) { assert(v>=0&&v<=IPL_HIGH);priority=v;seq[used++]=RESTORE; }
void mutex_init(kmutex_t *m, int type, int ipl) {
 assert(m==expected&&type==MUTEX_DEFAULT&&ipl==IPL_HIGH);m->init=1;m->held=0;seq[used++]=INIT;
}
void mutex_spin_enter(kmutex_t *m) {
 assert(m==expected&&m->init&&!m->held);m->old=priority;priority=IPL_HIGH;m->held=1;++spin_active;seq[used++]=ENTER;
}
void mutex_spin_exit(kmutex_t *m) {
 assert(m==expected&&m->held);m->held=0;priority=m->old;--spin_active;seq[used++]=EXIT;
}
int mutex_tryenter(kmutex_t *m) {
 assert(m==expected&&m->init);seq[used++]=TRY;
 if(fail_try)return 0;
 assert(!m->held);m->held=1;m->old=priority;priority=IPL_HIGH;++spin_active;return 1;
}
int mutex_owned(const kmutex_t *m) { return m->held; }
void mutex_destroy(kmutex_t *m) { assert(m==expected&&m->init&&!m->held);m->init=0;seq[used++]=DESTROY; }
static void trace(const int *events,int n) { assert(used==n);for(int i=0;i<n;++i)assert(seq[i]==events[i]);used=0; }
#define TRACE(...) do{const int e[]={__VA_ARGS__};trace(e,(int)(sizeof(e)/sizeof(e[0])));}while(0)
int main(void) {
 raw_spinlock_t lock={0}; expected=&lock.rsl_lock;
 raw_spin_lock_init(&lock);TRACE(INIT);
 raw_spin_lock(&lock);assert(priority==IPL_HIGH&&spin_active==1);
 raw_spin_unlock(&lock);assert(priority==3&&spin_active==0);TRACE(ENTER,EXIT);
 unsigned long flags[2]={99,99};raw_spinlock_t *locks[2]={&lock,&lock};int li=0,fi=0;
 raw_spin_lock_irqsave(locks[li++],flags[fi++]);assert(li==1&&fi==1&&flags[0]==3&&priority==IPL_HIGH);
 raw_spin_unlock_irqrestore(&lock,flags[0]);assert(priority==3&&spin_active==0);TRACE(HIGH,ENTER,EXIT,RESTORE);
 fail_try=1;li=fi=0;
 assert(!raw_spin_trylock_irqsave(locks[li++],flags[fi++]));
 assert(li==1&&fi==1&&flags[0]==3&&priority==3&&!spin_active);TRACE(HIGH,TRY,RESTORE);
 fail_try=0;assert(raw_spin_trylock_irqsave(&lock,flags[0]));
 assert(priority==IPL_HIGH&&spin_active==1);
 raw_spin_unlock_irqrestore(&lock,flags[0]);assert(priority==3&&spin_active==0);TRACE(HIGH,TRY,EXIT,RESTORE);
 /* Saved-high entry must remain high after its matching unlock. */
 priority=IPL_HIGH;raw_spin_lock_irqsave(&lock,flags[0]);
 raw_spin_unlock_irqrestore(&lock,flags[0]);assert(flags[0]==IPL_HIGH&&priority==IPL_HIGH);TRACE(HIGH,ENTER,EXIT,RESTORE);
 priority=3;assert(raw_spin_trylock(&lock));raw_spin_unlock(&lock);assert(priority==3);TRACE(TRY,EXIT);
 raw_spin_lock_destroy(&lock);assert(!lock.rsl_lock.init);TRACE(DESTROY);
 puts("LINUX_RAW_SPINLOCK_OK: non-sleeping delegation, saved IPL, contention restoration, macro single evaluation and native destroy");
 return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--header',type=Path)
    a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking checks are authorized only on HP/NetBSD')
    header=a.header or Path(__file__).resolve().parents[1]/'compat/linux/raw_spinlock.h'
    with tempfile.TemporaryDirectory(prefix='i915-raw-spin-') as name:
        temp=Path(name);(temp/'linux').mkdir();(temp/'sys').mkdir()
        (temp/'linux/raw_spinlock.h').write_bytes(header.read_bytes())
        (temp/'sys/intr.h').write_text('#define IPL_HIGH 7\nint splhigh(void);\nvoid splx(int);\n')
        (temp/'sys/mutex.h').write_text('typedef struct {int init,held,old;} kmutex_t;\n#define MUTEX_DEFAULT 2\nvoid mutex_init(kmutex_t*,int,int);\nvoid mutex_spin_enter(kmutex_t*);\nvoid mutex_spin_exit(kmutex_t*);\nint mutex_tryenter(kmutex_t*);\nint mutex_owned(const kmutex_t*);\nvoid mutex_destroy(kmutex_t*);\n')
        (temp/'sys/systm.h').write_text('#include <assert.h>\n#define KASSERT(X) assert(X)\n')
        source=temp/'test.c';source.write_text(C);exe=temp/'test'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(temp),str(source),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)

if __name__=='__main__':main()
