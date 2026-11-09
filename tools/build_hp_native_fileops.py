#!/usr/bin/env python3
"""Compile actual patched native file/syscall owners on HP; never install.

Two native core objects are an ABI check, not full modern DRM or kernel closure.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess

from native_hp_build import (configured_compiler, create_private_output,
                             private_output, require_hp_owner, toolchain_paths)

PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('sys/sys/file.h', 'sys/sys/filedesc.h',
          'sys/kern/sys_generic.c', 'sys/kern/kern_descrip.c')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(argv, **kwargs):
    return subprocess.check_output([str(x) for x in argv], text=True, **kwargs).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netbsd-source', type=Path, required=True)
    p.add_argument('--kernel-obj', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--toolchain', type=Path, required=True)
    a = p.parse_args()
    try:
        require_hp_owner()
        tools = toolchain_paths(a.toolchain)
    except (ValueError, OSError) as error:
        p.error(str(error))
    source, obj = a.netbsd_source.resolve(strict=True), a.kernel_obj.resolve(strict=True)
    try:
        output = private_output(a.output, (source, obj, ROOT, tools['root']))
    except (ValueError, OSError) as error:
        p.error(str(error))
    if checked(['git', '-C', source, 'rev-parse', 'HEAD']) != PIN:
        p.error('wrong NetBSD source pin')
    if checked(['git', '-C', source, 'status', '--porcelain']):
        p.error('pinned source dirty')
    values = {k: checked([tools['make'], '-C', obj, '-v', k])
              for k in ('CC', 'CFLAGS', 'CPPFLAGS', 'S')}
    try:
        cc = configured_compiler(values['CC'], tools)
    except (ValueError, OSError) as error:
        p.error(str(error))
    configured = Path(values['S']).resolve(strict=True).parent
    flags = shlex.split(values['CFLAGS']) + [v.replace(str(configured) + '/', str(source) + '/')
                                            for v in shlex.split(values['CPPFLAGS'])]
    if not {'-Werror', '-D_KERNEL', '-nostdinc'}.issubset(flags):
        p.error('required kernel flags missing')
    patch = ROOT / 'patches/0038-netbsd-linux-fileops-dispatch.patch'
    state = dict(state='RUNNING', started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 pid=os.getpid(), host=socket.gethostname(), source_pin=PIN,
                 patch_sha256=sha(patch), makefile_sha256=sha(obj / 'Makefile'),
                 prior_kernel_sha256=sha(obj / 'netbsd'), native_flags=values,
                 toolchain=str(tools['root']),
                 native_tool_sha256={str(tools[k]):sha(tools[k]) for k in ('make','compiler')},
                 inputs={}, commands=[], full_adapter='NOT_RUN', full_kernel='NOT_RUN',
                 installed=False, booted=False)
    create_private_output(output)
    receipt = output / 'status.json'

    def save():
        receipt.write_text(json.dumps(state, indent=2) + '\n', encoding='utf8')

    def run(argv, cwd):
        row = dict(command=[str(x) for x in argv], cwd=str(cwd))
        r = subprocess.run(row['command'], cwd=cwd, capture_output=True, text=True)
        row.update(exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        state['commands'].append(row)
        save()
        if r.returncode:
            raise RuntimeError('native step failed: ' + ' '.join(row['command']))
        return row

    save()
    try:
        overlay = output / 'source'
        for rel in INPUTS:
            target = overlay / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / rel).read_bytes())
            state['inputs'][rel] = sha(target)
        run(['git', 'apply', '--check', str(patch)], overlay)
        run(['git', 'apply', str(patch)], overlay)
        state['patched_sources_sha256'] = {rel: sha(overlay / rel) for rel in INPUTS}
        state['objects'] = {}
        for name in ('sys_generic', 'kern_descrip'):
            artifact, dep = output / (name + '.o'), output / (name + '.d')
            run(cc + ['-I' + str(overlay / 'sys')] + flags + ['-MD', '-MF', str(dep),
                    '-c', str(overlay / 'sys/kern' / (name + '.c')), '-o', str(artifact)], obj)
            dependencies = shlex.split(dep.read_text(encoding='utf8').replace('\\\n', ' ').split(':', 1)[1])
            headers = {(Path(v) if Path(v).is_absolute() else obj / v).resolve(strict=True)
                       for v in dependencies if v.endswith('.h')}
            for rel in ('sys/sys/file.h', 'sys/sys/filedesc.h'):
                if (overlay / rel).resolve() not in headers:
                    raise RuntimeError('patched header not consumed: ' + rel)
            state['objects'][name] = dict(sha256=sha(artifact), bytes=artifact.stat().st_size,
                headers_sha256={str(v): sha(v) for v in sorted(headers)})
        if sha(obj / 'netbsd') != state['prior_kernel_sha256']:
            raise RuntimeError('prior kernel changed')
        if (sha(patch) != state['patch_sha256'] or sha(obj / 'Makefile') != state['makefile_sha256']
                or any(sha(path)!=expected for path,expected in state['native_tool_sha256'].items())):
            raise RuntimeError('patch/config drift')
        state['state'] = 'PASS'
    except BaseException as error:
        state.update(state='FAIL', error=str(error))
        raise
    finally:
        state['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print(json.dumps(dict(state=state['state'], receipt=str(receipt), objects=list(state['objects']))))


if __name__ == '__main__':
    main()
