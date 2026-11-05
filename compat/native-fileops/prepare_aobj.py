#!/usr/bin/env python3
"""Derive real same-object UAO growth/future freelist owners at the native pin."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
BEFORE={'sys/uvm/uvm_aobj.c':'a9d8131479e979841214c57a77a89dfba2351730871bd6648c6502f469f7d39d',
        'sys/uvm/uvm_aobj.h':'5db0f17b73b1495a1dd097737995cc9efa5f1eddfbfb720baeee0f571ab66ace'}
def sha(data):return hashlib.sha256(data).hexdigest()
def prepare(reference,output):
    if output.exists() or output.is_symlink():raise ValueError('new output required')
    before={rel:(reference/rel).read_bytes() for rel in BEFORE}
    if {rel:sha(data) for rel,data in before.items()}!=BEFORE:raise ValueError('native source pin mismatch')
    helper=(ROOT/'compat/native-file/native_aobj_grow.inc').read_bytes().replace(b'\r\n',b'\n')
    text=before['sys/uvm/uvm_aobj.c'].decode()
    anchor='/*\n * uao_set_pgfl: allocate pages only from the specified freelist.'
    if text.count(anchor)!=1:raise ValueError('native UAO owner anchor drift')
    native=text.replace(anchor,helper.decode()+'\n'+anchor)
    header=before['sys/uvm/uvm_aobj.h'].decode()
    anchor='void\tuao_init(void);\n'
    if header.count(anchor)!=1:raise ValueError('native UAO declaration anchor drift')
    header=header.replace(anchor,anchor+'/* Private kernel file/MM owner extensions; same UAO identity. */\n'
        'int\tuao_grow(struct uvm_object *, voff_t);\n'
        'int\tuao_set_pgfl_future(struct uvm_object *, int);\n')
    after={'sys/uvm/uvm_aobj.c':native.encode(),'sys/uvm/uvm_aobj.h':header.encode()}
    patch=''.join(''.join(difflib.unified_diff(before[rel].decode().splitlines(True),
        after[rel].decode().splitlines(True),'a/'+rel,'b/'+rel)) for rel in before).encode()
    contract=dict(netbsd_pin=PIN,patch_sha256=sha(patch),helper_sha256=sha(helper),
        files={rel:dict(before_sha256=sha(before[rel]),after_sha256=sha(after[rel])) for rel in before},
        acceptance='Actual UAO source owner only; native compilation/lifetime tests and complete kernel link remain separate.')
    output.mkdir(parents=True)
    (output/'aobj-owner.patch').write_bytes(patch)
    (output/'aobj-owner.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(patch_sha256=sha(patch),helper_sha256=sha(helper))))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.reference,args.output)
