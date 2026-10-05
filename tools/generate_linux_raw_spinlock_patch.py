#!/usr/bin/env python3
"""Expose the native raw-lock adapter through the existing Linux spin header.

This supplies real non-sleeping mutex/IPL operations. Driver destruction must
also drain users and destroy native mutex state; that lifecycle gate remains
open until the modern DRM cleanup adapter is reconciled.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
SPIN='sys/external/bsd/drm2/include/linux/spinlock.h'
RAW='sys/external/bsd/drm2/include/linux/raw_spinlock.h'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    assert subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==PIN
    if a.out.exists():p.error('preserve existing output')
    old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show','HEAD:'+SPIN],text=True)
    anchor='#include <sys/mutex.h>\n'
    if old.count(anchor)!=1:raise ValueError('unexpected frozen native spin header')
    new=old.replace(anchor,anchor+'\n#include <linux/raw_spinlock.h>\n')
    raw=(Path(__file__).resolve().parents[1]/'compat/linux/raw_spinlock.h').read_text()
    diff=''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/'+SPIN,tofile='b/'+SPIN))
    diff+=''.join(difflib.unified_diff([],raw.splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+RAW))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(diff)

if __name__=='__main__':main()
