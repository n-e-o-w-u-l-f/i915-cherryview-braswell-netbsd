#!/usr/bin/env python3
"""Add frozen Linux variable wait macros to the explicit native keyed API."""
import hashlib
import os
import json
import re
import subprocess
from pathlib import Path
PIN='fd179f8a05be3ccae366b9b96e176b51fbe54aab'
ROOT=Path(os.environ['NETBSD_RUNTIME_WAIT_OUTPUT'])
original=subprocess.check_output(['git','-C',os.environ['NETBSD_RUNTIME_LINUX_TREE'],
    'show',PIN+':include/linux/wait_bit.h'],text=True)
start=original.index('#define ___wait_var_event(')
end=original.index('/**\n * clear_and_wake_up_bit',start)
macros=original[start:end].replace('___wait_cond_timeout(condition)',
    '___wait_cond_timeout(condition, __ret)')
lines=macros.splitlines(keepends=True);adapted=[];i=0
while i<len(lines):
    match=re.match(r'#define\s+(\w+)',lines[i])
    if match is None: adapted.append(lines[i]);i+=1;continue
    chunk=[lines[i]];i+=1
    while chunk[-1].rstrip().endswith('\\') and i<len(lines):
        chunk.append(lines[i]);i+=1
    text=''.join(chunk)
    if match.group(1)!='___wait_var_event' and re.search(r'\b(?:long|int)\s+__ret\b',text):
        text=re.sub(r'\b__ret\b','__linux_'+match.group(1)+'_ret',text)
    adapted.append(text)
header=(ROOT/'wait_bit.h').read_text().rstrip()+'\n'
assert header.endswith('#endif\n')
header=header[:-len('#endif\n')]+''.join(adapted)+'\n#endif\n'
(ROOT/'include/linux/wait_bit.h').write_text(header)
manifest=json.loads((ROOT/'provenance.json').read_text())
for path in ('include/linux/wait_bit.h','kernel/sched/wait_bit.c','include/linux/hash.h'):
    raw=subprocess.check_output(['git','-C',os.environ['NETBSD_RUNTIME_LINUX_TREE'],'show',PIN+':'+path])
    manifest['frozen_inputs'][path]=hashlib.sha256(raw).hexdigest()
for path in ('include/linux/wait_bit.h','linux_wait_var.c'):
    manifest['files'][path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
(ROOT/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('generated native hashed variable callback API/macros')
