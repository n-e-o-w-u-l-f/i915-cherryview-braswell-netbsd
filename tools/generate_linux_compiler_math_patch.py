#!/usr/bin/env python3
"""Add privately named pinned attributes/math to native Linux adapter headers."""
import argparse
import difflib
from pathlib import Path
import subprocess
from namespace_linux_compiler_math import bindings,frozen,translate
NETBSD_PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
PREFIX='sys/external/bsd/common/include/linux/'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True);p.add_argument('--netbsd-tree',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('preserve existing output')
    assert subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==NETBSD_PIN
    mapping=bindings(a.linux_tree);patches=[]
    for name,anchor,addition in [('compiler.h','#include <linux/stddef.h>\n','compiler_attributes.h'),('kernel.h','#include <linux/slab.h>\n','math.h')]:
        rel=PREFIX+name;old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',NETBSD_PIN+':'+rel],text=True)
        if old.count(anchor)!=1:raise RuntimeError('unexpected native include anchor')
        new=old.replace(anchor,anchor+'#include <linux/'+addition+'>\n')
        patches.append(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/'+rel,tofile='b/'+rel,n=1)))
    for name in ['compiler_attributes.h','math.h']:
        rel=PREFIX+name;data=translate(frozen(a.linux_tree,'include/linux/'+name),mapping)
        patches.append(''.join(difflib.unified_diff([],data.splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+rel)))
    rel='sys/external/bsd/common/include/asm/div64.h'
    old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',NETBSD_PIN+':'+rel],text=True)
    macro='#define\tdo_div(n_q, d)\t_do_div(&(n_q), (d))'
    replacement=r"""/* Both native uint64_t and Linux u64 retain the complete quotient. */
#define do_div(n_q, d) ({ \
    __typeof__(&(n_q)) __linux_n_q = &(n_q); \
    uint32_t __linux_divisor = (d); \
    _Static_assert(sizeof(*__linux_n_q) == sizeof(uint64_t), \
        "do_div requires a 64-bit dividend"); \
    uint32_t __linux_remainder = *__linux_n_q % __linux_divisor; \
    *__linux_n_q /= __linux_divisor; \
    __linux_remainder; \
})"""
    if old.count(macro)!=1 or old.count('const uint32_t q =')!=1:raise RuntimeError('unexpected native division helper')
    new=old.replace(macro,replacement).replace('const uint32_t q =','const uint64_t q =')
    patches.append(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/'+rel,tofile='b/'+rel)))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(''.join(patches))
    print('LINUX_COMPILER_MATH_ADAPTER',len(mapping),'private macro bindings')

if __name__=='__main__':main()
