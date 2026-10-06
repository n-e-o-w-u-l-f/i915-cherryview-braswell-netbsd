#!/usr/bin/env python3
"""Bind pinned container/type assertions with native byte-pointer arithmetic.

The strict Linux member/type and const-result contracts remain intact. Native
__UNCONST spells deliberate const removal without weakening kernel warnings.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess
from namespace_linux_compiler_math import bindings,frozen,translate

PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
PREFIX='sys/external/bsd/common/include/linux/'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    assert subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==PIN
    if a.out.exists():p.error('preserve existing output')
    mapping=bindings(a.linux_tree);patches=[]
    def diff(rel,old,new):
        patches.append(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
            fromfile='a/'+rel if old else '/dev/null',tofile='b/'+rel,n=1)))
    raw=frozen(a.linux_tree,'include/linux/build_bug.h')
    definitions=re.findall(r'^#define (?:static_assert|__static_assert)\([^\n]+',raw,re.M)
    if len(definitions)!=2:raise RuntimeError('changed pinned static assertion definitions')
    rel=PREFIX+'build_bug.h'
    old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+rel],text=True)
    anchor='#define\tstatic_assert(EXPR)\t\tCTASSERT(EXPR)\n';assert old.count(anchor)==1
    block='\n/* Pinned Linux C11 assertions; native CTASSERT spelling remains intact. */\n'+translate('\n'.join(definitions),mapping)+'\n'
    diff(rel,old,old.replace(anchor,anchor+block))
    raw=frozen(a.linux_tree,'include/linux/container_of.h')
    anchor='#include <linux/build_bug.h>\n';assert raw.count(anchor)==1
    # Linux compiler/types normally supply __same_type through a transitive
    # include. The native header requires an explicit owner here.
    raw=raw.replace(anchor,'#include <sys/cdefs.h>\n\n'+anchor+'#include <linux/compiler.h>\n')
    pointer='(type *)((void *)(ptr) - offsetof(type, member))'
    assert raw.count(pointer)==1
    raw=raw.replace(pointer,'(type *)((char *)__UNCONST(ptr) - offsetof(type, member))')
    new=translate(raw,mapping)
    diff(PREFIX+'container_of.h','',new)
    rel=PREFIX+'kernel.h'
    old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+rel],text=True)
    anchor='#include <linux/compiler.h>\n';assert old.count(anchor)==1
    diff(rel,old,old.replace(anchor,anchor+'#include <linux/container_of.h>\n'))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(''.join(patches))
    print('LINUX_CONTAINER_NATIVE_ADAPTER')

if __name__=='__main__':main()
