#!/usr/bin/env python3
"""Namespace Linux RB_ROOT initializers without changing native sys/tree.h.

Only C identifiers in exact pinned manifest inputs are translated. Comments,
strings and character literals remain byte-for-byte unchanged. The imported
source baseline is verified before a native-tree patch can be applied.
"""
import argparse
import difflib
import json
from pathlib import Path
import re
import subprocess

PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
TOKEN = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\bRB_ROOT\b')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    head=subprocess.check_output(['git','-C',str(a.linux_tree),'rev-parse','HEAD'],text=True).strip()
    if head!=PIN: p.error('wrong frozen Linux reference')
    if a.out.exists(): p.error('preserve existing output')
    patches=[]; files=0; identifiers=0
    for row in json.loads(a.manifest.read_text())['files']:
        path=row['path']
        if not path.endswith(('.c','.h')): continue
        old=subprocess.check_output(['git','-C',str(a.linux_tree),'show','HEAD:'+path],text=True)
        count=0
        def replace(m):
            nonlocal count
            if m[0]=='RB_ROOT': count+=1; return 'LINUX_RB_ROOT'
            return m[0]
        new=TOKEN.sub(replace,old)
        if new==old: continue
        relative=path.removeprefix('drivers/gpu/') if path.startswith('drivers/gpu/') else path
        target='sys/external/bsd/drm2/dist/'+relative
        patches.append(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
            fromfile='a/'+target,tofile='b/'+target)))
        files+=1; identifiers+=count
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(''.join(patches))
    print('LINUX_RB_ROOT_CALLSITES',files,'files',identifiers,'identifiers')

if __name__=='__main__': main()
