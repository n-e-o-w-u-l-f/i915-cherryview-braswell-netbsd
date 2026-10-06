#!/usr/bin/env python3
"""Bind complete pinned typecheck/word-part macros without replacing native names.

Only the Linux-owned identifier namespace and native endian predicate change.
Native adapters retain their existing typecheck and word-part macros.
"""
import argparse
import difflib
from pathlib import Path
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
    for name in ['typecheck.h','wordpart.h']:
        text=translate(frozen(a.linux_tree,'include/linux/'+name),mapping)
        if name=='wordpart.h':
            anchor='#define _LINUX_WORDPART_H\n';assert text.count(anchor)==1
            text=text.replace(anchor,anchor+'\n#include <sys/endian.h>\n#include <linux/types.h>\n')
            anchor='#ifdef __LITTLE_ENDIAN';assert text.count(anchor)==1
            text=text.replace(anchor,'#if _BYTE_ORDER == _LITTLE_ENDIAN')
        diff(PREFIX+name,'',text)
    rel=PREFIX+'kernel.h'
    old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+rel],text=True)
    anchor='#include <linux/slab.h>\n';assert old.count(anchor)==1
    # Patch 0026 is a prerequisite and already selects the owned math header.
    old=old.replace(anchor,anchor+'#include <linux/math.h>\n')
    anchor='#include <linux/math.h>\n';assert old.count(anchor)==1
    diff(rel,old,old.replace(anchor,anchor+'#include <linux/typecheck.h>\n#include <linux/wordpart.h>\n'))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(''.join(patches))
    print('LINUX_TYPECHECK_WORDPART_NATIVE_ADAPTER')

if __name__=='__main__':main()
