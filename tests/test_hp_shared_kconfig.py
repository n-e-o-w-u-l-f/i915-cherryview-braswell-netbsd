#!/usr/bin/env python3
"""Verify actual configured kernel flags match selected Linux source semantics."""
import argparse
from pathlib import Path
import platform
import shlex
import socket
import subprocess
import tempfile

def main():
    p=argparse.ArgumentParser(description=__doc__);a=p.parse_args()
    if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking checks are authorized only on HP/NetBSD')
    root=Path('/root/hp-driver-port-20261005')
    flags=subprocess.check_output([str(root/'full-linux-tools/bin/nbmake-amd64'),'-C',str(root/'full-linux-obj'),'-V','CPPFLAGS.drmkms'],text=True)
    config=[f for f in shlex.split(flags) if f.startswith(('-DCONFIG_','-UCONFIG_'))]
    source='''#include <linux/kconfig.h>
#if defined(CONFIG_LOCKDEP) || defined(CONFIG_FB) || defined(CONFIG_BACKLIGHT_CLASS_DEVICE) || defined(CONFIG_BACKLIGHT_CLASS_DEVICE_MODULE)
#error Disabled Linux symbols must be absent in the native build
#endif
#if !IS_ENABLED(CONFIG_64BIT) || !IS_ENABLED(CONFIG_DRM_TTM) || !IS_ENABLED(CONFIG_DRM_DISPLAY_DP_HELPER) || !IS_ENABLED(CONFIG_DRM_KMS_HELPER)
#error Actual DRM/TTM source-selection flags must be shared with native headers
#endif
int main(void) { return IS_MODULE(CONFIG_DRM_I915) || !IS_BUILTIN(CONFIG_DRM_I915); }
'''
    with tempfile.TemporaryDirectory(prefix='i915-shared-kconfig-') as name:
        tmp=Path(name);src=tmp/'test.c';src.write_text(source);exe=tmp/'test'
        include=Path(__file__).resolve().parents[1]/'compat'
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-I',str(include),*config,str(src),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
    print('HP_SHARED_KCONFIG_OK: actual nbconfig flags, absent disabled symbols and shared DRM/TTM profile')

if __name__=='__main__':main()
