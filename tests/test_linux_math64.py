#!/usr/bin/env python3
"""Run pinned arithmetic implementation bodies against wide independent oracles.

Scalar and bit-index fixtures model the OS inputs in HP userspace. Actual
native kernel header/implementation objects are verified separately; this is
not a 32-bit kernel or whole-driver closure claim.
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
#include <stdint.h>
#include <limits.h>
#include <linux/math64.h>
static u64 random_state=0xfeedbabe12345678ULL;
static u64 next(void){ random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state; }
static u64 mul_oracle(u64 a,u64 b,u64 c,u64 d){unsigned __int128 q=((unsigned __int128)a*b+c)/d;return q>UINT64_MAX?UINT64_MAX:(u64)q;}
static unsigned long sqrt_oracle(unsigned long x){u64 lo=0,hi=1ULL<<32;while(lo+1<hi){u64 m=(lo+hi)/2;if(m<=x/m)lo=m;else hi=m;}return lo;}
static u64 pow_oracle(u64 b,unsigned int e){u64 r=1;while(e--)r*=b;return r;}
static void vectors(u64 a,u64 b,u32 d) {
 u64 rem;u32 rem32;assert(b && d);
 assert(div64_u64(a,b)==a/b);
 assert(div64_u64_rem(a,b,&rem)==a/b && rem==a%b);
 assert(div_u64(a,d)==a/d);
 assert(div_u64_rem(a,d,&rem32)==a/d && rem32==a%d);
 assert(mul_u64_u32_div(a,d,d)==a);
 assert(mul_u64_add_u64_div_u64(a,b,a,b)==mul_oracle(a,b,a,b));
 assert(mul_u64_u64_div_u64(a,b,b)==a);
 assert(mul_u64_u64_div_u64_roundup(a,b,b)==mul_oracle(a,b,b-1,b));
 for(unsigned int s=0;s<128;s++) {
  assert(mul_u64_u64_shr(a,b,s)==(u64)(((unsigned __int128)a*b)>>s));
  assert(mul_u64_u32_shr(a,d,s)==(u64)(((unsigned __int128)a*d)>>s));
  assert(mul_u64_u32_add_u64_shr(a,d,b,s)==(u64)((((unsigned __int128)a*d)+b)>>s));
 }
 assert(int_sqrt((unsigned long)a)==sqrt_oracle((unsigned long)a));
 assert(int_sqrt64(a)==sqrt_oracle((unsigned long)a));
}
int main(void){
 _Static_assert(__builtin_types_compatible_p(__typeof__(div_u64_rem(0,1,(u32 *)0)),u64),"unsigned quotient type");
 _Static_assert(__builtin_types_compatible_p(__typeof__(div64_u64(0,1)),u64),"unsigned dividend/result ABI");
 _Static_assert(__builtin_types_compatible_p(__typeof__(div_s64_rem(0,1,(s32 *)0)),s64),"signed quotient type");
 _Static_assert(sizeof(u128)==16 && _Alignof(u128)==16,"128bit scalar ABI");
 u64 edges[]={0,1,2,3,0xffffffffULL,1ULL<<32,(1ULL<<32)+1,1ULL<<48,1ULL<<63,UINT64_MAX-1,UINT64_MAX};
 u32 ds[]={1,2,3,17,0x7fffffffU,0x80000000U,0xffffffffU};
 for(unsigned int i=0;i<sizeof(edges)/sizeof(edges[0]);i++)for(unsigned int j=1;j<sizeof(edges)/sizeof(edges[0]);j++)for(unsigned int k=0;k<sizeof(ds)/sizeof(ds[0]);k++)vectors(edges[i],edges[j],ds[k]);
 for(unsigned int i=0;i<20000;i++){u64 a=next(),b=next()|1;u32 d=(u32)next()|1;vectors(a,b,d);}
 for(unsigned long i=0;i<65536;i++)assert(int_sqrt(i)==sqrt_oracle(i));
 for(unsigned int i=0;i<2048;i++){u64 a=next();for(unsigned int e=0;e<65;e++)assert(int_pow(a,e)==pow_oracle(a,e));}
 for(int a=-2048;a<=2048;a++)for(int d=-19;d<=19;d++)if(d){
  s32 r32;s64 r64;assert(div_s64(a,d)==a/d);assert(div_s64_rem(a,d,&r32)==a/d && r32==a%d);assert(div64_s64(a,d)==a/d);assert(div64_s64_rem(a,d,&r64)==a/d && r64==a%d);
 }
 s64 r;assert(div64_s64_rem(INT64_MIN+1,3,&r)==(INT64_MIN+1)/3 && r==(INT64_MIN+1)%3);
 assert(mul_u64_add_u64_div_u64(UINT64_MAX,UINT64_MAX,UINT64_MAX,1)==UINT64_MAX);
 u64 rem;assert(iter_div_u64_rem(99,7,&rem)==14 && rem==1);
 for(s64 a=-12345;a<=12345;a+=23)for(unsigned int s=0;s<64;s++){u64 mag=a<0?-a:a;u64 q=(u64)(((unsigned __int128)mag*7919)>>s);assert(mul_s64_u64_shr(a,7919,s)==(a<0?(u64)-(s64)q:q));}
 return 0;
}
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',action='store_true');a=p.parse_args()
 if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):p.error('compiler-invoking tests are HP/NetBSD only')
 root=Path('/root/hp-driver-port-20261005');tree=root/'netbsd-full-linux';inc=tree/'sys/external/bsd';sources=[inc/'drm2/linux'/n for n in ['linux_div64_native.c','linux_int_sqrt_native.c','linux_int_pow_native.c']]
 with tempfile.TemporaryDirectory(prefix='i915-math64-') as name:
  tmp=Path(name);types=tmp/'linux/types.h';types.parent.mkdir(parents=True)
  types.write_text('''#ifndef TEST_MATH_TYPES
#define TEST_MATH_TYPES
#include <stdint.h>
#include <stdbool.h>
typedef unsigned char u8;typedef signed char s8;typedef unsigned short u16;typedef short s16;typedef unsigned int u32;typedef int s32;typedef unsigned long long u64;typedef long long s64;
typedef u8 __u8;typedef s8 __s8;typedef u16 __u16;typedef s16 __s16;typedef u32 __u32;typedef s32 __s32;typedef u64 __u64;typedef s64 __s64;typedef long __kernel_long_t;typedef unsigned long __kernel_ulong_t;
typedef __signed__ __int128 __s128 __attribute__((aligned(16)));typedef unsigned __int128 __u128 __attribute__((aligned(16)));typedef __s128 s128;typedef __u128 u128;
#endif
''')
  if a.baseline:
   # The actual original adapter returns a 32-bit quotient for this API.
   old=subprocess.check_output(['git','-C','/root/netbsd-src-ref','show','HEAD:sys/external/bsd/drm2/include/linux/math64.h'],text=True)
   (tmp/'linux/math64.h').write_text(old)
   src=tmp/'baseline.c';src.write_text('#include <stdint.h>\n#include <linux/math64.h>\nint main(void){uint32_t r; uint64_t n=UINT64_C(1)<<48;return div_u64_rem(n,3,&r)!=n/3 || r!=1;}\n')
   exe=tmp/'baseline';subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-I',str(tmp),'-I',str(inc/'common/include'),str(src),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True);return
  comp=(inc/'common/include/linux/compiler.h').read_text();opaque=re.search(r'#ifndef OPTIMIZER_HIDE_VAR\n[\s\S]*?\n#endif',comp)
  assert opaque
  (tmp/'linux/compiler.h').write_text('#include <sys/cdefs.h>\n#include <linux/compiler_attributes.h>\n#define likely(X) __predict_true(X)\n#define unlikely(X) __predict_false(X)\n'+opaque[0]+'\n')
  (tmp/'linux/export.h').write_text('#define EXPORT_SYMBOL(X)\n#define EXPORT_SYMBOL_GPL(X)\n')
  bits=(inc/'common/include/linux/bitops.h').read_text()
  helper=re.search(r'static inline unsigned int\n__fls\(unsigned long word\)\n\{[\s\S]*?\n\}',bits);assert helper
  (tmp/'linux/bitops.h').write_text('#ifndef TEST_MATH_BITOPS\n#define TEST_MATH_BITOPS\n#include <linux/types.h>\n#include <sys/bitops.h>\n#include <assert.h>\n#define KASSERT(X) assert(X)\n'+helper[0]+'\nstatic inline int fls(unsigned int x){return x?32-__builtin_clz(x):0;}\n#endif\n')
  (tmp/'linux/log2.h').write_text('#include <linux/bitops.h>\n')
  (tmp/'linux/limits.h').write_text('#include <limits.h>\n')
  src=tmp/'test.c';src.write_text(C);exe=tmp/'test'
  base=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-DBITS_PER_LONG=64','-DCONFIG_ARCH_SUPPORTS_INT128=1']
  for path in [tmp,inc/'common/include',inc/'drm2/include',inc/'drm2/dist/include']:base+=['-I',str(path)]
  command=base+['-fsanitize=undefined','-fno-sanitize-recover=all',str(src),*[str(s) for s in sources],'-o',str(exe)]
  subprocess.run(command,check=True);subprocess.run([str(exe)],check=True)
  zero=tmp/'zero.c';zero.write_text('#include <linux/math64.h>\nint main(void){volatile u64 z=0;return mul_u64_add_u64_div_u64(9,7,3,z);}\n')
  fault=tmp/'zero';subprocess.run(base+[str(zero),*[str(s) for s in sources],'-o',str(fault)],check=True)
  result=subprocess.run([str(fault)],capture_output=True,text=True)
  if result.returncode!=-8:raise AssertionError('Expected native SIGFPE for zero divisor, got '+str(result.returncode))
 print('LINUX_MATH64_OK: wide arithmetic/ABI, >20K multiply-divide and 128 shifts, sqrt/power, saturation and real zero-divisor fault')

if __name__=='__main__':main()
