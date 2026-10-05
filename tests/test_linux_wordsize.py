#!/usr/bin/env python3
"""Check exact native/imported bitmap constants and include order on HP.

Both 32/64-bit preprocessing contexts are checked, and actual amd64 C checks
sizeof(long). The 32-bit case is a CPP input test, not a 32-bit kernel build.
"""
import argparse
from pathlib import Path
import platform
import re
import socket
import subprocess
import tempfile

PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
BITOPS='sys/external/bsd/common/include/linux/bitops.h'
GENERIC='sys/external/bsd/common/include/asm-generic/bitsperlong.h'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--baseline',action='store_true')
    p.add_argument('--apply-candidate',action='store_true')
    a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking checks are authorized only on HP/NetBSD')
    owner=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='i915-wordsize-') as name:
        temp=Path(name);stage=a.netbsd_tree
        if a.apply_candidate:
            stage=temp/'candidate';native=stage/BITOPS;native.parent.mkdir(parents=True)
            native.write_bytes(subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+BITOPS]))
            patch=owner/'patches/0023-netbsd-linux-native-word-size.patch'
            subprocess.run(['git','-C',str(stage),'apply','--check',str(patch)],check=True)
            subprocess.run(['git','-C',str(stage),'apply',str(patch)],check=True)
        if a.baseline:
            bit=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+BITOPS],text=True)
        else:
            bit=(stage/BITOPS).read_text()
        # Test only the production preprocessor word-size block; unrelated
        # kernel bit-operation functions are covered by native compilation.
        match=re.search(r'(#ifndef BITS_PER_LONG\n#define\s+BITS_PER_LONG[^\n]*\n#endif\n#if[^\n]*\n#error[^\n]*\n#endif\n)',bit)
        if a.baseline:
            block=next(x for x in bit.splitlines() if re.match(r'#define\s+BITS_PER_LONG\s',x))+'\n'
            header=Path('/root/hp-driver-port-20261005/netbsd-full-linux/sys/external/bsd/drm2/dist/include/asm-generic/bitsperlong.h').read_text()
        else:
            if not match:raise RuntimeError('missing production word-size conflict guard')
            block=match[1];header=(stage/GENERIC).read_text()
        uapi=temp/'uapi/asm-generic/bitsperlong.h';uapi.parent.mkdir(parents=True)
        uapi.write_bytes(subprocess.check_output(['git','-C','/root/linux-rtl8723be-ref-fresh','show','HEAD:include/uapi/asm-generic/bitsperlong.h']))
        (temp/'native.h').write_text(block);(temp/'generic.h').write_text(header)
        for bits in [32,64]:
            for order in [('native.h','generic.h'),('generic.h','native.h')]:
                source=temp/'probe.c'
                source.write_text('#define CHAR_BIT __CHAR_BIT__\n'+''.join('#include "'+h+'"\n' for h in order)+
                    '#if BITS_PER_LONG != '+str(bits)+'\n#error Incorrect physical bitmap word size\n#endif\n'+
                    '#ifndef __ASSEMBLER__\n_Static_assert(BITS_PER_LONG == sizeof(long)*8,"native C word width");\n#endif\n')
                command=['cc','-Werror','-U__SIZEOF_LONG__','-D__SIZEOF_LONG__='+str(bits//8),
                    '-D__BITS_PER_LONG='+str(bits),'-I',str(temp)]
                if bits==32:command+=['-D__ASSEMBLER__','-E','-P']
                else:command+=['-std=gnu11','-fsyntax-only']
                subprocess.run(command+[str(source)],check=True,stdout=subprocess.DEVNULL)
        # Explicitly conflicting producer values must fail in both headers.
        for name in ['native.h','generic.h']:
            source=temp/'conflict.c';source.write_text('#define CHAR_BIT __CHAR_BIT__\n#define BITS_PER_LONG 32\n#include "'+name+'"\n')
            r=subprocess.run(['cc','-Werror','-D__BITS_PER_LONG=64','-I',str(temp),'-E',str(source)],capture_output=True,text=True)
            if r.returncode==0 or 'Inconsistent native Linux word size' not in r.stderr:
                raise AssertionError('conflicting word-size producer not rejected')
    print('LINUX_WORD_SIZE_OK: 32/64 CPP contexts, native amd64 C, both include orders, two conflict controls')

if __name__=='__main__':main()
