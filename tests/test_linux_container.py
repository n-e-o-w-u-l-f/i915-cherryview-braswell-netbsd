#!/usr/bin/env python3
"""Compile actual private container/assertion headers on HP, with negative controls.

The temporary OS includes are explicit scalar/compiler userspace models.
A separate actual native kernel header object is required for ABI integration.
"""
import argparse
from pathlib import Path
import platform
import re
import socket
import subprocess
import tempfile

C=r'''
#include <assert.h>
#include <stddef.h>
#undef static_assert /* userspace assert.h differs from the kernel include set */
#include <linux/container_of.h>
struct item { char lead; long member; int tail; };
netbsd_linux_static_assert(sizeof(long)>=4);
netbsd_linux_static_assert(offsetof(struct item, member)>0, "nonzero member offset");
static struct item items[2];
static unsigned evaluations;
static long *member(void){evaluations++;return &items[1].member;}
int main(void){
 long *p=&items[1].member; const long *cp=p; void *vp=p; const void *cvp=p;
 assert(netbsd_linux_container_of(p,struct item,member)==&items[1]);
 assert(netbsd_linux_container_of(vp,struct item,member)==&items[1]);
 assert(netbsd_linux_container_of_const(p,struct item,member)==&items[1]);
 assert(netbsd_linux_container_of_const(cp,struct item,member)==&items[1]);
 assert(netbsd_linux_container_of_const(cvp,struct item,member)==&items[1]);
 netbsd_linux_static_assert(__same_type(netbsd_linux_container_of_const(p,struct item,member),struct item *));
 netbsd_linux_static_assert(__same_type(netbsd_linux_container_of_const(cp,struct item,member),const struct item *));
 netbsd_linux_static_assert(__same_type(netbsd_linux_container_of_const(cvp,struct item,member),const struct item *));
 evaluations=0;assert(netbsd_linux_container_of_const(member(),struct item,member)==&items[1] && evaluations==1);
 evaluations=0;assert(netbsd_linux_container_of(member(),struct item,member)==&items[1] && evaluations==1);
 for(unsigned int i=0;i<2;i++)assert(netbsd_linux_container_of_const(&items[i].tail,struct item,tail)==&items[i]);
 return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',action='store_true');a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking tests are HP/NetBSD only')
    stage=Path('/root/hp-driver-port-20261005/netbsd-full-linux/sys/external/bsd/common/include/linux')
    with tempfile.TemporaryDirectory(prefix='i915-container-') as name:
        t=Path(name);(t/'linux').mkdir();(t/'lib/libkern').mkdir(parents=True)
        (t/'lib/libkern/libkern.h').write_text('#define CTASSERT(e) _Static_assert(e,#e)\n')
        (t/'linux/stddef.h').write_text('#include <stddef.h>\n')
        (t/'linux/compiler.h').write_text('#define __same_type(a,b) __builtin_types_compatible_p(__typeof__(a),__typeof__(b))\n')
        for h in ['container_of.h','build_bug.h']:
            if a.baseline:
                data=subprocess.check_output(['git','-C','/root/linux-rtl8723be-ref-fresh','show',
                    'fd179f8a05be3ccae366b9b96e176b51fbe54aab:include/linux/'+h])
            else:data=(stage/h).read_bytes()
            (t/'linux'/h).write_bytes(data)
        src=t/'test.c';src.write_text(C);exe=t/'test'
        flags=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wcast-qual','-Wpointer-arith','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(t)]
        subprocess.run(flags+[str(src),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
        cases=[('void bad(void){int *p=0;(void)netbsd_linux_container_of_const(p,struct item,member);}',
                'pointer type mismatch in container_of()'),
               ('netbsd_linux_static_assert(0,"explicit assertion failure");','explicit assertion failure'),
               ('netbsd_linux_static_assert(0);','static assertion failed'),
               ('void bad(void){int value=0;netbsd_linux_static_assert(value);}','not constant')]
        for body,diagnostic in cases:
            src.write_text(C+'\n'+body+'\n')
            r=subprocess.run(flags+['-c',str(src),'-o',str(t/'bad.o')],capture_output=True,text=True)
            if r.returncode==0 or diagnostic not in r.stderr:raise AssertionError('missing negative control: '+diagnostic)
    print('LINUX_CONTAINER_OK: exact pinned assertions, const/void/member types, one evaluation and four negative controls')

if __name__=='__main__':main()
