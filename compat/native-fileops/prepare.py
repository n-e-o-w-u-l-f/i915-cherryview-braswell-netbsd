#!/usr/bin/env python3
"""Prepare exact native dispatch and additive per-mapping request contracts.

Does not build or install. Retains 0038 unchanged and derives the next patch
against its exact result, with the real NetBSD11 file operation signatures.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
BEFORE = {
 'sys/sys/file.h':'a6019f187474dddf7eac80eff44ea652fc9d3bb43459d076bbf106c5bac69a4c',
 'sys/sys/filedesc.h':'3ef72d7490544b5cd806abe869e80a03ba0414f9b621b0351b26587ede81a72c',
 'sys/kern/sys_generic.c':'532ff66e2560a93be706032fd5f69e1a1b69d57f165621ea66d3f3e0aea69514',
 'sys/kern/kern_descrip.c':'48006299c61b697c7342f2341cd867066f5ea5851efc174f93ce3aa284df4de1',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(data, before, after):
    if data.count(before) != 1:
        raise ValueError('changed native source anchor: '+before[:80])
    return data.replace(before, after)


def prepare(reference, output):
    if output.exists() or output.is_symlink():
        raise ValueError('new preparation output required')
    before = {rel:(reference/rel).read_bytes() for rel in BEFORE}
    if {rel:sha(data) for rel,data in before.items()} != BEFORE:
        raise ValueError('actual pinned native source digest mismatch')
    patch = (ROOT/'patches/0038-netbsd-linux-fileops-dispatch.patch').read_bytes().replace(b'\r\n',b'\n')
    with tempfile.TemporaryDirectory(prefix='native-fileops-source-') as name:
        temporary = Path(name)
        for rel,data in before.items():
            target=temporary/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        subprocess.run(['git','-c','core.autocrlf=false','-C',str(temporary),'apply','--check','-'],input=patch,check=True)
        subprocess.run(['git','-c','core.autocrlf=false','-C',str(temporary),'apply','-'],input=patch,check=True)
        dispatched={rel:(temporary/rel).read_bytes() for rel in BEFORE}
    text=dispatched['sys/sys/file.h'].decode()
    text=once(text,'struct uvm_object;\n','struct uvm_object;\nstruct uvm_mmap_request;\n')
    text=once(text,'\tstruct linux_file *(*fo_linux_file)(struct file *);\n',
        '\tstruct linux_file *(*fo_linux_file)(struct file *);\n'
        '\t/* Optional per-mapping preparation. Same native fo_mmap inputs,\n'
        '\t * plus one transaction request. On failure the callback unwinds\n'
        '\t * and returns NULL object/request outputs. On success the caller\n'
        '\t * consumes the object reference and finishes the request once\n'
        '\t * after every mapping/hint retry or pre-mapping failure.\n'
        '\t * Existing fo_mmap behavior is the NULL-hook fallback. */\n'
        '\tint\t(*fo_mmap_prepare)(struct file *, off_t *, size_t, int,\n'
        '\t\t    int *, int *, struct uvm_object **, int *,\n'
        '\t\t    struct uvm_mmap_request **);\n')
    new=text.encode()
    request=''.join(difflib.unified_diff(dispatched['sys/sys/file.h'].decode().splitlines(True),
                    text.splitlines(True),'a/sys/sys/file.h','b/sys/sys/file.h')).encode()
    legacy=dict(netbsd_pin=PIN,patch_sha256=sha(patch),files={rel:dict(before_sha256=sha(before[rel]),
                after_sha256=sha(dispatched[rel])) for rel in before},
                acceptance='Actual source contract; native ABI and full kernel remain separate.')
    extension=dict(netbsd_pin=PIN,prior_patch_sha256=sha(patch),patch_sha256=sha(request),
                files={'sys/sys/file.h':dict(before_sha256=sha(dispatched['sys/sys/file.h']),after_sha256=sha(new))},
                acceptance='Source contract only. Requires matching UVM per-mapping-request consumer, actual native compilation and full kernel rebuild.')
    output.mkdir(parents=True)
    for name,data in [('dispatch.patch',patch),('mmap-request.patch',request),
                      ('dispatch.json',(json.dumps(legacy,indent=2)+'\n').encode()),
                      ('mmap-request.json',(json.dumps(extension,indent=2)+'\n').encode())]:
        (output/name).write_bytes(data)
    return legacy,extension


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    legacy,extension=prepare(args.reference,args.output)
    print(json.dumps(dict(dispatch=legacy['patch_sha256'],mmap_request=extension['patch_sha256'])))
