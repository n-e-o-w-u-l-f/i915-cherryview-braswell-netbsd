#!/usr/bin/env python3
"""Port the complete pinned math64 header and generic arithmetic implementations.

Native scalar/opaque-optimizer prerequisites are explicit. The generic Linux
function bodies remain intact except for the existing private macro bindings;
the unused minmax include is removed from the division implementation.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess
from namespace_linux_compiler_math import bindings,frozen,translate
NETBSD_PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
BASE='sys/external/bsd/'

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--linux-tree',type=Path,required=True);p.add_argument('--netbsd-tree',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args()
 assert subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==NETBSD_PIN
 if a.out.exists():p.error('preserve existing output')
 mapping=bindings(a.linux_tree);patches=[]
 def native(path):return subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',NETBSD_PIN+':'+path],text=True)
 def diff(path,old,new,n=3):patches.append(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/'+path if old else '/dev/null',tofile='b/'+path,n=n)))
 path=BASE+'drm2/include/linux/math64.h';old=native(path);new=translate(frozen(a.linux_tree,'include/linux/math64.h'),mapping)
 new=new.replace('#include <linux/types.h>','#include <linux/compiler.h>\n#include <linux/types.h>',1);diff(path,old,new)
 path=BASE+'common/include/vdso/math64.h';diff(path,'',translate(frozen(a.linux_tree,'include/vdso/math64.h'),mapping))
 path=BASE+'common/include/linux/types.h';old=native(path);anchor='#include <sys/stdint.h>\n'
 assert old.count(anchor)==1
 # Preserve the exact pinned UAPI alignment as well as the kernel aliases.
 raw=frozen(a.linux_tree,'include/uapi/linux/types.h')
 defs=re.findall(r'^typedef[^\n]* __[su]128[^\n]*;',raw,re.M)
 assert len(defs)==2
 block='\n#ifdef __SIZEOF_INT128__\n'+'\n'.join(defs)+'\ntypedef __s128 s128;\ntypedef __u128 u128;\n#endif\n'
 # Insert after the POSIX UAPI adapter added by patch 0020, using a stable end anchor.
 anchor='typedef uint8_t u8;\n';assert old.count(anchor)==1;diff(path,old,old.replace(anchor,block+'\n'+anchor),n=1)
 path=BASE+'common/include/linux/compiler.h';old=native(path)
 raw=frozen(a.linux_tree,'include/linux/compiler.h');pattern=r'#ifndef OPTIMIZER_HIDE_VAR\n[\s\S]*?\n#endif'
 block=re.search(pattern,raw)
 if not block:raise RuntimeError('missing pinned opaque optimizer primitive')
 anchor='#define\tbarrier()\t__insn_barrier()\n';assert old.count(anchor)==1;diff(path,old,old.replace(anchor,block[0]+'\n\n'+anchor),n=1)
 path=BASE+'common/include/linux/bitops.h';old=native(path);anchor='#include <linux/bits.h>\n';assert old.count(anchor)==1
 helper='''
/* Linux most-significant bit index; zero has no defined result. */
static inline unsigned int
__fls(unsigned long word)
{
    KASSERT(word != 0);
    return fls64(word) - 1;
}
'''
 diff(path,old,old.replace(anchor,anchor+helper),n=1)
 additions=[]
 for local,source in [('linux_div64_native.c','lib/math/div64.c'),('linux_int_sqrt_native.c','lib/math/int_sqrt.c'),('linux_int_pow_native.c','lib/math/int_pow.c')]:
  data=translate(frozen(a.linux_tree,source),mapping)
  if local=='linux_div64_native.c':
   include='#include <linux/minmax.h>\n';assert data.count(include)==1;data=data.replace(include,'/* Native integration: unused Linux minmax header is not an input. */\n')
  if local=='linux_int_sqrt_native.c':
   include='#include <linux/limits.h>\n';assert data.count(include)==1;data=data.replace(include,'#include <machine/limits.h>\n')
  diff(BASE+'drm2/linux/'+local,'',data);additions.append('file\texternal/bsd/drm2/linux/'+local+'\tdrmkms_linux\n')
 path=BASE+'drm2/linux/files.drmkms_linux';old=native(path)
 first=re.search(r'^file[^\n]*\n',old,re.M);assert first
 at=first.start();new=old[:at]+'# Pinned Linux integer arithmetic; complete caller/OS validation remains open.\n'+''.join(additions)+'\n'+old[at:];diff(path,old,new,n=1)
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(''.join(patches));print('LINUX_MATH64_NATIVE_ADAPTER',len(additions),'implementation units')

if __name__=='__main__':main()
