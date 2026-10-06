#!/usr/bin/env python3
"""Reproduce the pinned native UUID/GUID implementation and real build graph."""
import argparse, difflib, hashlib, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
PATCH_SHA='1adb7c56f823f08dfa42073175d1d74fdf9f50c10590997f3dd50b727f836c66'
def replace_once(text,old,new):
    if text.count(old)!=1:raise RuntimeError('changed native UUID source anchor')
    return text.replace(old,new)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('preserve existing generated patch')
    if subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()!=PIN:
        p.error('wrong frozen NetBSD revision')
    graph_paths=['sys/external/bsd/drm2/linux/files.drmkms_linux',
                 'sys/modules/drmkms_linux/Makefile']
    graph={}
    with tempfile.TemporaryDirectory(prefix='uuid-source-') as name:
        temp=Path(name);shutil.copytree(ROOT/'compat/native-uuid',temp/'assets')
        subprocess.run([sys.executable,str(temp/'assets/generate.py')],check=True)
        patch=(temp/'assets/native-uuid.patch').read_bytes()
        if hashlib.sha256(patch).hexdigest()!=PATCH_SHA:raise RuntimeError('changed pinned UUID body projection')
        for path in graph_paths:
            dest=temp/path;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+path]))
        subprocess.run(['git','-C',str(temp),'apply',
                        *['--include='+p for p in graph_paths],
                        str(ROOT/'patches/0032-netbsd-linux-task-wait-worker.patch')],check=True)
        graph={path:(temp/path).read_text() for path in graph_paths}
    changes=[patch.decode()]
    for path,anchor,addition in [
        ('sys/external/bsd/drm2/linux/files.drmkms_linux',
         'file\texternal/bsd/drm2/linux/linux_module.c\t\tdrmkms_linux\n',
         'file\texternal/bsd/drm2/linux/linux_uuid.c\t\tdrmkms_linux\n'),
        ('sys/modules/drmkms_linux/Makefile','SRCS+=\tlinux_module.c\n','SRCS+=\tlinux_uuid.c\n')]:
        old=graph[path]
        new=replace_once(old,anchor,anchor+addition)
        changes.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),'a/'+path,'b/'+path,n=1))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(''.join(changes))
    print('NATIVE_UUID_GUID_PATCH_GENERATED real_cprng=1 native_acpi_scalar_api=preserved')
if __name__=='__main__':main()
