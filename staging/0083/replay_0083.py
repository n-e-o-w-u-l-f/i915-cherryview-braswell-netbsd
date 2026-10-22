#!/usr/bin/env python3
"""Compile staged kernel-candidate source with isolated mock kernel headers.
No HP access, no NetBSD native build; fail closed on missing toolchain.
"""
from pathlib import Path
import os, subprocess, tempfile, json, re, hashlib, shutil
ROOT = Path(__file__).resolve().parent
SOURCES = [ROOT/'0083_linux_backlight_class.c', ROOT/'test_0083.c']
EXPECTED = {
    '0083_linux_backlight_abi.h':'ba6b5cbab440c10868e33d9494f6cea57b71346a4831ab9993d88c763c5be3af',
    '0083_linux_backlight_class.c':'cd3352478dae6a9fbef8ac65a13b5984379b94a6e21f8b96ee5daa3aa6088a3a',
    'test_0083.c':'35ee8d5d6704db07b1a862c260725d45ae53e364bf812e1de5dfbd0035d0e6ba',
}

def run(command, env=None):
    x = subprocess.run([str(z) for z in command], capture_output=True, text=True, timeout=30, check=False, env=env)
    if x.returncode:
        raise RuntimeError(f'command={command} exit={x.returncode}\nstdout={x.stdout}\nstderr={x.stderr}')
    return x

def main():
    for name, expected in EXPECTED.items():
        real = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if real != expected:
            raise RuntimeError(f'source mismatch {name}: {real} != {expected}')
    result=[]
    with tempfile.TemporaryDirectory(prefix='hp-i915-0083-') as temp:
        for cc in ('gcc','clang'):
            if not shutil.which(cc):
                raise RuntimeError(cc+' compiler unavailable')
            output = Path(temp)/cc
            cmd = [cc, '-v', '-std=gnu11', '-O2', '-Wall','-Wextra','-Wpedantic','-Werror',
                   '-Wconversion','-Wshadow','-pthread', '-I', ROOT/'mockinclude', '-I', ROOT,
                   *SOURCES,'-o',output]
            compile_log=run(cmd).stderr
            for i in range(5):
                x=run([output])
                marker=x.stdout.strip()
                if not re.fullmatch(r'HP_I915_0083_STAGED_ABI_PASS checks=26 alloc=3 free=3 callbacks=5',marker):
                    raise RuntimeError('unexpected marker '+repr(marker))
                result.append({'compiler':cc,'iteration':i+1,'marker':marker})
            (ROOT/('0083-'+cc+'-verbose.log')).write_text(compile_log)
        out=Path(temp)/'sanitizer'
        cmd = ['gcc','-v','-std=gnu11','-g','-O1','-Wall','-Wextra','-Wpedantic','-Werror',
               '-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',
               '-I',ROOT/'mockinclude','-I',ROOT,*SOURCES,'-o',out]
        log=run(cmd).stderr
        e={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'}
        x=run([out],env=e)
        if not re.fullmatch(r'HP_I915_0083_STAGED_ABI_PASS checks=26 alloc=3 free=3 callbacks=5',x.stdout.strip()):
            raise RuntimeError('sanitizer marker mismatch')
        (ROOT/'0083-sanitizer-verbose.log').write_text(log)
        result.append({'compiler':'gcc-asan-ubsan','iteration':1,'marker':x.stdout.strip()})
    print(json.dumps({'status':'PASS','runs':len(result),'checks_per_run':26,
                      'total_synthetic_checks':len(result)*26,
                      'netbsd_kernel_object':'NOT_BUILT','hp':'NOT_ACCESSED','runs_detail':result},indent=2))

if __name__=='__main__':
    main()
