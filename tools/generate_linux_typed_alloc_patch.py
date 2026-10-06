#!/usr/bin/env python3
"""Port pinned object allocators and saturated sizes above native allocation.

The kmem backend and its GFP policy remain explicit native dependencies.
Overflow rejection returns NULL before any backend allocation or old free.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess
from namespace_linux_compiler_math import bindings,frozen,translate

PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
PREFIX='sys/external/bsd/common/include/linux/'

def macro(raw,name):
    lines=raw.splitlines(keepends=True)
    found=[i for i,s in enumerate(lines) if re.match(r'^#define\s+'+re.escape(name)+r'\(',s)]
    if len(found)!=1:raise RuntimeError('changed pinned macro '+name)
    i=found[0];out=lines[i];i+=1
    while out.rstrip().endswith('\\'):
        out+=lines[i];i+=1
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    assert subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==PIN
    if a.out.exists():p.error('preserve existing output')
    mapping=bindings(a.linux_tree);patches=[]
    def native(rel):return subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+rel],text=True)
    def diff(rel,old,new):
        patches.append(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
            fromfile='a/'+rel if old else '/dev/null',tofile='b/'+rel,n=1)))
    raw=frozen(a.linux_tree,'include/linux/overflow.h');functions=[]
    for name in ['size_mul','size_add','size_sub']:
        found=re.findall(r'^static __always_inline size_t __must_check '+name+r'\([^\n]+\)\n\{[\s\S]*?^\}',raw,re.M)
        if len(found)!=1:raise RuntimeError('changed pinned size function '+name)
        functions.append(found[0]+'\n')
    text='''/* SPDX-License-Identifier: GPL-2.0 OR MIT */
/* Complete size arithmetic bodies from the frozen Linux overflow.h. */
#ifndef _NETBSD_LINUX_SIZE_ARITHMETIC_H_
#define _NETBSD_LINUX_SIZE_ARITHMETIC_H_
#include <linux/compiler.h>

'''+translate('\n'.join(functions),mapping)+'\n#endif\n'
    # Preserve the exact upstream license rather than guessing its terms.
    license_line=raw.splitlines()[0];assert 'SPDX-License-Identifier:' in license_line
    text=text.replace(text.splitlines()[0],license_line,1)
    diff(PREFIX+'size_arithmetic.h','',text)
    rel=PREFIX+'overflow.h';old=native(rel)
    anchor='#define\tcheck_add_overflow(a, b, res)\t__builtin_add_overflow(a, b, res)\n';assert old.count(anchor)==1
    new=old.replace(anchor,anchor+'#define\tcheck_sub_overflow(a, b, res)\t__builtin_sub_overflow(a, b, res)\n\n#include <linux/size_arithmetic.h>\n')
    diff(rel,old,new)
    slab=frozen(a.linux_tree,'include/linux/slab.h');gfp=frozen(a.linux_tree,'include/linux/gfp.h')
    text=slab.splitlines()[0]+'''
/* Pinned Linux optional-GFP and typed object allocation macro bodies. */
#ifndef _NETBSD_LINUX_TYPED_ALLOC_H_
#define _NETBSD_LINUX_TYPED_ALLOC_H_
#include <linux/gfp.h>
#include <linux/overflow.h>

'''+macro(gfp,'__default_gfp')+macro(gfp,'default_gfp')+'\n'+''.join(macro(slab,n)+'\n' for n in ['__alloc_objs','kmalloc_obj','kmalloc_objs','kzalloc_obj','kzalloc_objs'])+'#endif\n'
    diff(PREFIX+'typed_alloc.h','',translate(text,mapping))
    rel=PREFIX+'slab.h';old=native(rel)
    anchor='#include <linux/rcupdate.h>\n';assert old.count(anchor)==1
    new=old.replace(anchor,anchor+'#include <linux/typed_alloc.h>\n')
    decl='int kmflags = linux_gfp_to_kmem(gfp);';assert new.count(decl)==2;new=new.replace(decl,'int kmflags;')
    anchor='\tKASSERTMSG(size < SIZE_MAX - sizeof(*lm), "size=%zu", size);\n';assert new.count(anchor)==1
    new=new.replace(anchor,'\tif (size >= SIZE_MAX - sizeof(*lm))\n\t\treturn NULL;\n\tkmflags = linux_gfp_to_kmem(gfp);\n')
    anchor='\tstruct linux_malloc *olm, *nlm;\n\tint kmflags;\n';assert new.count(anchor)==1
    new=new.replace(anchor,anchor+'\n\tif (size >= SIZE_MAX - sizeof(*nlm))\n\t\treturn NULL;\n\tkmflags = linux_gfp_to_kmem(gfp);\n')
    diff(rel,old,new)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(''.join(patches))
    print('LINUX_TYPED_ALLOC_NATIVE_ADAPTER: four object wrappers, three full size functions, native overflow rejection')

if __name__=='__main__':main()
