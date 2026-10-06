#!/usr/bin/env python3
"""Exercise production private typechecks and word parts on HP.

The endian/type inputs below are explicit userspace models. A separate real
native-kernel header probe is required; neither model proves another OS ABI.
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
#include <sys/param.h>
#include <linux/types.h>
#include <linux/typecheck.h>
#include <linux/wordpart.h>
static u64 seed=0x9e3779b97f4a7c15ULL;
static u64 next(void){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;}
static void bits(u64 x){
 assert(netbsd_linux_upper_32_bits(x)==(u32)(x/0x100000000ULL));
 assert(netbsd_linux_lower_32_bits(x)==(u32)(x%0x100000000ULL));
 assert(netbsd_linux_upper_16_bits((u32)x)==(u16)((u32)x/65536));
 assert(netbsd_linux_lower_16_bits((u32)x)==(u16)((u32)x%65536));
}
int main(void){
 u64 x=17;u32 small=0x87654321;int value=1;
 assert(netbsd_linux_typecheck(u64,x)==1);
 assert(netbsd_linux_typecheck_pointer(&value)==1);
 typedef u64 (*fn_t)(void);netbsd_linux_typecheck_fn(fn_t,next);
 assert(netbsd_linux_upper_32_bits(small)==0);
 for(u64 i=0;i<65536;i++)bits((i<<32)|i);
 for(int i=0;i<10000;i++)bits(next());
 unsigned int index=0;u64 values[]={0x123456789abcdef0ULL};
 assert(netbsd_linux_upper_32_bits(values[index++])==0x12345678 && index==1);
 index=0;assert(netbsd_linux_lower_32_bits(values[index++])==0x9abcdef0 && index==1);
 for(unsigned long b=0;b<256;b++){
  unsigned long expected=0;for(unsigned int j=0;j<sizeof(expected);j++)expected=expected*256+b;
  assert(netbsd_linux_REPEAT_BYTE(b)==expected);
  assert(netbsd_linux_REPEAT_BYTE_U32(b)==(u32)expected);
 }
 for(unsigned int n=0;n<sizeof(unsigned long);n++){
  unsigned long expected=0;
  for(unsigned int j=0;j<n;j++){
   unsigned int position=_BYTE_ORDER==_LITTLE_ENDIAN?j:sizeof(unsigned long)-1-j;
   expected|=0xffUL<<(8*position);
  }
  assert(netbsd_linux_aligned_byte_mask(n)==expected);
 }
 return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',action='store_true');a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking tests are HP/NetBSD only')
    mapping=bindings(Path('/root/linux-rtl8723be-ref-fresh'))
    source='#include <linux/typecheck.h>\n# include_next <linux/typecheck.h>\n#include "linux/typecheck.h"\ntypecheck(u64,x); /* typecheck */\n'
    result=translate(source,mapping)
    assert result==source.replace('\ntypecheck(u64,x);','\nnetbsd_linux_typecheck(u64,x);')
    source='#include \\\n  <linux/typecheck.h>\n'
    assert translate(source,mapping)==source
    stage=Path('/root/hp-driver-port-20261005/netbsd-full-linux/sys/external/bsd')
    with tempfile.TemporaryDirectory(prefix='i915-wordpart-') as name:
        t=Path(name);(t/'linux').mkdir();(t/'sys').mkdir()
        (t/'linux/types.h').write_text('typedef unsigned short u16;typedef unsigned int u32;typedef unsigned long long u64;\n')
        for h in ['typecheck.h','wordpart.h']:
            if a.baseline:
                data=subprocess.check_output(['git','-C','/root/linux-rtl8723be-ref-fresh','show',
                    'fd179f8a05be3ccae366b9b96e176b51fbe54aab:include/linux/'+h])
            else:data=(stage/'common/include/linux'/h).read_bytes()
            (t/'linux'/h).write_bytes(data)
        flags=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-DBITS_PER_LONG=64','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(t)]
        for order in [1234,4321]:
            (t/'sys/endian.h').write_text('#define _LITTLE_ENDIAN 1234\n#define _BIG_ENDIAN 4321\n#undef _BYTE_ORDER\n#define _BYTE_ORDER '+str(order)+'\n')
            src=t/'test.c';src.write_text(C);exe=t/'test'
            subprocess.run(flags+[str(src),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
            for body,diagnostic in [('void bad(void){int x=0;(void)netbsd_linux_typecheck(u64,x);}','comparison of distinct pointer types'),
                                    ('void bad(void){int x=0;(void)netbsd_linux_typecheck_pointer(x);}','invalid type argument')]:
                src.write_text(C+'\n'+body+'\n')
                result=subprocess.run(flags+['-c',str(src),'-o',str(t/'bad.o')],capture_output=True,text=True)
                if result.returncode==0 or diagnostic not in result.stderr:raise AssertionError('missing typecheck negative control: '+diagnostic)
    print('LINUX_TYPECHECK_WORDPART_OK: type/pointer negative controls, full-width parts, single evaluation and both endian models')

if __name__=='__main__':main()
