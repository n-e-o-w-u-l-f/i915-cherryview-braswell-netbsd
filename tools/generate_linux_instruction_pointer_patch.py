#!/usr/bin/env python3
"""Bind pinned instruction-location helpers to native x86-64 compiler output.

Retain the upstream generic fallback and its HAS_BROKEN_THIS_IP marker for
other architectures; only HP x86-64 receives the frozen RIP-based helper.
No Linux assembly linkage/IBT/Kbuild alignment headers are imported here.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess

LINUX_PIN='fd179f8a05be3ccae366b9b96e176b51fbe54aab'
NETBSD_PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
COMPILER='sys/external/bsd/common/include/linux/compiler.h'
POINTER='sys/external/bsd/common/include/linux/instruction_pointer.h'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    for tree,pin in [(a.linux_tree,LINUX_PIN),(a.netbsd_tree,NETBSD_PIN)]:
        assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()==pin
    if a.out.exists():p.error('preserve existing output')
    def get(tree,path):return subprocess.check_output(['git','-C',str(tree),'show','HEAD:'+path],text=True)
    old=get(a.netbsd_tree,COMPILER);anchor='#include <asm/barrier.h>\n'
    if old.count(anchor)!=1:raise ValueError('unexpected native compiler header')
    new=old.replace(anchor,anchor+'\n#include <linux/instruction_pointer.h>\n')
    pointer=get(a.linux_tree,'include/linux/instruction_pointer.h')
    arch=get(a.linux_tree,'arch/x86/include/asm/linkage.h')
    macro=re.search(r'^#define _THIS_IP_ .*$',arch,re.M)
    if not macro:raise ValueError('missing frozen x86-64 instruction pointer')
    linkage='#include <asm/linkage.h>'
    if pointer.count(linkage)!=1:raise ValueError('unexpected instruction pointer prerequisites')
    pointer=pointer.replace(linkage,'/* Native target ABI selects the pinned x86-64 RIP helper. */\n#if defined(__x86_64__) && !defined(__ILP32__)\n'+macro[0]+'\n#endif')
    diff=''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/'+COMPILER,tofile='b/'+COMPILER))
    diff+=''.join(difflib.unified_diff([],pointer.splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+POINTER))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(diff)

if __name__=='__main__':main()
