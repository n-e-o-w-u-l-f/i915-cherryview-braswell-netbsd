#!/usr/bin/env python3
"""Exercise privately bound pinned Linux attributes/math and native do_div on HP.

The arithmetic type fixture is a userspace model of fixed Linux scalar types;
actual kernel header/object compilation remains a separate acceptance check.
"""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from namespace_linux_compiler_math import bindings,translate

C=r'''
#include <assert.h>
#include <stdint.h>
#include <sys/cdefs.h>
#include <sys/param.h>
#include "native_attributes.h"
#include <linux/compiler_attributes.h>
#include <linux/math.h>
static netbsd_linux_always_inline int add_one(int x) { return x+1; }
static inline __always_inline int native_add_one(int x) { return x+1; }
static int native_data __section(".native_compat_data") = 1;
static int linux_data netbsd_linux_section(".linux_port_data") = 2;
static int netbsd_linux_always_unused unused_data;
static int netbsd_linux_maybe_unused maybe_unused_data;
static netbsd_linux_noinline int opaque(int x) { return x; }
int checked_value(void) netbsd_linux_must_check;
int checked_value(void) { return 17; }
void format_test(const char *, ...) netbsd_linux_printf(1,2);
void format_test(const char *s, ...) { (void)s; }
static int nearest(int a,int d) {
 int q=a/d,r=a%d,ar=r<0?-r:r,ad=d<0?-d:d;
 if(ar*2>=ad)q+=((a<0)!=(d<0))?-1:1;
 return q;
}
int main(void) {
 volatile int x=4;
 assert(add_one(x)==5 && native_add_one(x)==5 && opaque(x)==4);
 assert(native_data==1 && linux_data==2 && checked_value()==17);
 format_test("%d",3);
 uint64_t n=UINT64_C(0xfedcba9876543210),original=n;
 unsigned int r=do_div(n,7);assert(n==original/7 && r==original%7);
 unsigned long long ll=UINT64_C(0xfedcba9876543210), ll_original=ll;
 r=do_div(ll,UINT32_MAX);assert(ll==ll_original/UINT32_MAX && r==ll_original%UINT32_MAX);
 uint64_t slots[2]={UINT64_C(1)<<48,0};int i=0,j=3;
 r=do_div(slots[i++],j++);assert(i==1 && j==4 && slots[0]==(UINT64_C(1)<<48)/3 && r==1);
 uint64_t helper=UINT64_C(1)<<48;assert(_do_div(&helper,3)==1 && helper==(UINT64_C(1)<<48)/3);
 for(int a=-999;a<=999;a++)for(int d=-41;d<=41;d++)if(d)
  assert(netbsd_linux_DIV_ROUND_CLOSEST(a,d)==nearest(a,d));
 for(uint64_t a=0;a<4096;a++) {
  for(uint32_t d=1;d<43;d++) {
   assert(netbsd_linux_DIV_ROUND_UP(a,d)==(a+d-1)/d);
   assert(netbsd_linux_DIV_ROUND_DOWN_ULL(a,d)==a/d);
   assert(netbsd_linux_DIV_ROUND_UP_ULL(a,d)==(a+d-1)/d);
   assert(netbsd_linux_DIV_ROUND_CLOSEST_ULL(a,d)==(a+d/2)/d);
   assert(netbsd_linux_roundup(a,d)==((a+d-1)/d)*d);
   assert(netbsd_linux_rounddown(a,d)==(a/d)*d);
  }
  for(unsigned int b=0;b<9;b++) {
   uint64_t d=UINT64_C(1)<<b;
   assert(netbsd_linux_round_up(a,d)==((a+d-1)/d)*d);
   assert(netbsd_linux_round_down(a,d)==(a/d)*d);
   assert(netbsd_linux_DIV_ROUND_UP_POW2(a,d)==(a/d+!!(a&(d-1))));
  }
 }
 ll=UINT64_C(1)<<50;
 assert(netbsd_linux_DIV_ROUND_DOWN_ULL(ll,3)==ll/3);
 assert(netbsd_linux_DIV_ROUND_UP_ULL(ll,3)==(ll+2)/3);
 assert(netbsd_linux_DIV_ROUND_CLOSEST_ULL(ll,3)==(ll+1)/3);
 assert(netbsd_linux_DIV_ROUND_UP_POW2(UINT64_MAX,8)==UINT64_MAX/8+1);
 uint64_t a=5,b=7; i=0;j=0;
 assert(netbsd_linux_roundup((i++,a),(j++,b))==7 && i==1 && j==1);
 i=0;j=0;assert(netbsd_linux_round_down((i++,a),(j++,b+1))==0 && i==1 && j==1);
 assert(netbsd_linux_mult_frac((unsigned long long)19,3,5)==11);
 assert(netbsd_linux_abs((int)-7)==7 && netbsd_linux_abs_diff((uint64_t)9,(uint64_t)2)==7);
 assert(reciprocal_scale(UINT32_MAX,UINT32_MAX)==UINT32_MAX-1);
 _Static_assert(__builtin_types_compatible_p(__typeof__(netbsd_linux_abs((char)0)),char),"abs char type");
 return 0;
}
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline-div',action='store_true');a=p.parse_args()
 if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
  p.error('compiler-invoking checks are authorized only on HP/NetBSD')
 linux=Path('/root/linux-rtl8723be-ref-fresh');tree=Path('/root/hp-driver-port-20261005/netbsd-full-linux')
 mapping=bindings(linux)
 sample='__always_inline /* __always_inline */ "roundup" \'x\' // noinline\\\nroundup\nroundup(x,y)'
 result=translate(sample,mapping)
 assert result.startswith('netbsd_linux_always_inline /* __always_inline */ "roundup"')
 assert '// noinline\\\nroundup\nnetbsd_linux_roundup(x,y)' in result
 assert translate('RB_ROOT __alloc_size__(1) __always_inline__',mapping)=='RB_ROOT __alloc_size__(1) __always_inline__'
 with tempfile.TemporaryDirectory(prefix='i915-compiler-math-') as name:
  tmp=Path(name)
  if a.baseline_div:
   src=tmp/'baseline.c';src.write_text('#include <stdint.h>\n#include <asm/div64.h>\nint main(void){ uint64_t n=UINT64_C(1)<<48; uint32_t r=do_div(n,3); return n!=(UINT64_C(1)<<48)/3 || r!=1; }\n')
   include=Path('/root/hp-driver-port-20261005/netbsd-reference/sys/external/bsd/common/include')
   exe=tmp/'baseline';subprocess.run(['cc','-std=gnu11','-Wall','-Werror','-I',str(include),str(src),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True);return
  native=(tree/'sys/external/bsd/common/include/linux/compiler.h').read_text()
  block=native[native.index('#define\t__printf'):native.index('#define\t__deprecated')]
  (tmp/'native_attributes.h').write_text(block)
  types=tmp/'linux/types.h';types.parent.mkdir(parents=True)
  types.write_text('''#ifndef TEST_LINUX_TYPES
#define TEST_LINUX_TYPES
#include <stdint.h>
typedef unsigned char u8;typedef signed char s8;typedef unsigned short u16;typedef short s16;typedef unsigned int u32;typedef int s32;typedef unsigned long long u64;typedef long long s64;
typedef u8 __u8;typedef s8 __s8;typedef u16 __u16;typedef s16 __s16;typedef u32 __u32;typedef s32 __s32;typedef u64 __u64;typedef s64 __s64;typedef long __kernel_long_t;typedef unsigned long __kernel_ulong_t;
#endif
''')
  src=tmp/'test.c';src.write_text(C);exe=tmp/'test'
  includes=[tmp,tree/'sys/external/bsd/common/include',tree/'sys/external/bsd/drm2/include',tree/'sys/external/bsd/drm2/dist/include']
  flags=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-DBITS_PER_LONG=64']
  for include in includes:flags+=['-I',str(include)]
  subprocess.run(flags+[str(src),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
  for body,warning in [('void bad_format(void){ format_test("%d","wrong"); }','format'),('void bad_result(void){ checked_value(); }','unused-result')]:
   bad=tmp/'negative.c';bad.write_text(C+'\n'+body+'\n')
   r=subprocess.run(flags+['-c',str(bad),'-o',str(tmp/'negative.o')],capture_output=True,text=True)
   if r.returncode==0 or warning not in r.stderr:raise AssertionError('attribute negative control not detected: '+warning)
 print('LINUX_COMPILER_MATH_OK: native/private attributes, format/result negative controls, >64K arithmetic vectors, full-width div and single evaluation')

if __name__=='__main__':main()
