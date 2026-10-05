#!/usr/bin/env python3
"""Compile actual instruction-location helpers and validate HP RIP provenance."""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import tempfile

C=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <linux/instruction_pointer.h>
#ifdef HAS_BROKEN_THIS_IP
#error HP must use its architecture instruction-pointer helper
#endif
static __attribute__((noinline)) unsigned long here(void) { return _THIS_IP_; }
static __attribute__((noinline)) unsigned long caller(void) { return _RET_IP_; }
int main(void) {
 unsigned long pc=here(), begin=(unsigned long)(uintptr_t)here;
 assert(pc>=begin && pc<begin+256);
 assert(caller()!=0 && _CODE_LOCATION_!=0);
 puts("LINUX_INSTRUCTION_POINTER_OK: frozen x86-64 RIP lies in its actual function, return/code location helpers");
 return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking checks are authorized only on HP/NetBSD')
    header=a.netbsd_tree/'sys/external/bsd/common/include/linux/instruction_pointer.h'
    with tempfile.TemporaryDirectory(prefix='i915-instruction-pointer-') as name:
        temp=Path(name);(temp/'linux').mkdir()
        (temp/'linux/instruction_pointer.h').write_bytes(header.read_bytes())
        src=temp/'test.c';src.write_text(C);exe=temp/'test'
        subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer','-I',str(temp),str(src),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)

if __name__=='__main__':main()
