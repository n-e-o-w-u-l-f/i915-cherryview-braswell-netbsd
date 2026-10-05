#!/usr/bin/env python3
"""Bind Linux bitmap word size to native compiler/architecture inputs.

Linux's CONFIG_64BIT cannot define the physical word width of a NetBSD kernel.
Existing native and imported users must agree with the actual architecture.
Preserve native macro ownership in either include order and reject conflicts.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

LINUX_PIN='fd179f8a05be3ccae366b9b96e176b51fbe54aab'
NETBSD_PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
BITOPS='sys/external/bsd/common/include/linux/bitops.h'
GENERIC='sys/external/bsd/common/include/asm-generic/bitsperlong.h'

def bitops(old):
    line='#define\tBITS_PER_LONG\t\t(__SIZEOF_LONG__ * CHAR_BIT)\n'
    if old.count(line)!=1:raise ValueError('unexpected native word-size baseline')
    return old.replace(line,'#ifndef BITS_PER_LONG\n'+line+'#endif\n#if BITS_PER_LONG != (__SIZEOF_LONG__ * CHAR_BIT)\n#error Inconsistent native Linux word size\n#endif\n')

def generic(old):
    selection='#ifdef CONFIG_64BIT\n#define BITS_PER_LONG 64\n#else\n#define BITS_PER_LONG 32\n#endif /* CONFIG_64BIT */'
    if old.count(selection)!=1:raise ValueError('unexpected pinned generic word-size header')
    native='''/* NetBSD's native architecture/compiler determine the physical word size. */
#ifndef BITS_PER_LONG
#define BITS_PER_LONG __BITS_PER_LONG
#endif
#if BITS_PER_LONG != __BITS_PER_LONG
#error Inconsistent native Linux word size
#endif'''
    return old.replace(selection,native)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    for tree,pin in [(a.linux_tree,LINUX_PIN),(a.netbsd_tree,NETBSD_PIN)]:
        assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()==pin
    if a.out.exists():p.error('preserve existing output')
    old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show','HEAD:'+BITOPS],text=True)
    head=subprocess.check_output(['git','-C',str(a.linux_tree),'show','HEAD:include/asm-generic/bitsperlong.h'],text=True)
    patch=''.join(difflib.unified_diff(old.splitlines(keepends=True),bitops(old).splitlines(keepends=True),fromfile='a/'+BITOPS,tofile='b/'+BITOPS))
    patch+=''.join(difflib.unified_diff([],generic(head).splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+GENERIC))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(patch)

if __name__=='__main__':main()
