#!/usr/bin/env python3
"""Unchanged actual FILE/FD/POLL source bodies with explicit Native delegates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import socket
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (platform.system() != 'NetBSD' or platform.release().split('.')[0] != '11' or
            socket.gethostname().split('.')[0] != 'hp-tpnw121' or os.geteuid() == 0):
        raise ValueError('unprivileged HP NetBSD11 only')
    output = args.output
    if (not output.is_absolute() or output.exists() or output.is_symlink() or
            not output.parent.is_dir() or any(v.is_symlink() for v in output.parents)):
        raise ValueError('fresh absolute output required; preserve every failed attempt')
    # Extract only the exact, unchanged added Native helper. Mocking its
    # ownership ordering would make the borrowed-FD race test circular.
    patch_path = ROOT / 'patches/0038-netbsd-linux-fileops-dispatch.patch'
    patch_data = patch_path.read_bytes().replace(b'\r\n', b'\n')
    matches = list(re.finditer(rb'\n\+struct linux_file \*\n\+fd_get_linux_file\(unsigned fd\)\n\+\{[\s\S]*?\n\+\}\n', patch_data))
    if len(matches) != 1:
        raise ValueError('exact unique Native0038 helper required')
    helper = b'\n'.join(line[1:] for line in matches[0].group().splitlines() if line.startswith(b'+')) + b'\n'
    output.mkdir()
    source, include = output / 'source', output / 'include'
    source.mkdir()
    include.mkdir()
    state = dict(state='PREPARED', positive_expected=11, strict_fatal_expected=6,
                 scope='Unchanged production FILE/FD/POLL C and headers plus exact0038 fd helper. Explicit Native external API delegation; native kernel runtime acceptance OPEN.',
                 native_helper_patch_sha256=hashlib.sha256(patch_data).hexdigest(),
                 native_helper_sha256=hashlib.sha256(helper).hexdigest())
    receipt = output / 'status.json'

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save():
        receipt.write_bytes((json.dumps(state, indent=2) + '\n').encode())

    def run(command, name, timeout=60):
        def no_core():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        process = subprocess.Popen(command, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True, preexec_fn=no_core)
        try:
            data, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            data, _ = process.communicate()
            (output / name).write_bytes(data)
            raise
        (output / name).write_bytes(data)
        return process.returncode, data

    try:
        for name in ('test_model.h', 'test_file_lifecycle.c'):
            (source / name).write_bytes((HERE / name).read_bytes().replace(b'\r\n', b'\n'))
        for name in ('linux_file.c', 'linux_fd.c', 'linux_poll.c'):
            (source / name).write_bytes((ROOT / 'compat/native-file' / name).read_bytes().replace(b'\r\n', b'\n'))
        (source / 'fd_get_linux_file.inc').write_bytes(helper)
        real_headers = [ROOT / 'compat/native-file/include/linux' / name for name in
                        ('fs_netbsd.h', 'file_ref_netbsd.h', 'file_api_netbsd.h', 'file_netbsd.h', 'poll_netbsd.h')]
        real_headers += [ROOT / 'compat/native-uio/include/linux/kiocb_netbsd.h',
                         ROOT / 'compat/native-mm/include/linux/mm_abi_types_netbsd.h']
        for original in real_headers:
            target = include / 'linux' / original.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes().replace(b'\r\n', b'\n'))
        # Keep genuine host sys/queue.h, sys/fcntl.h, sys/poll.h, sys/errno.h,
        # sys/select.h and pthread/limits dependencies. Shadow only Native
        # kernel boundaries or already separately proved runtime providers.
        delegated = ['sys/' + n + '.h' for n in ('param', 'atomic', 'condvar', 'file', 'filedesc', 'kmem',
                     'lwp', 'mutex', 'proc', 'systm', 'kauth', 'workqueue', 'module', 'event')]
        delegated += ['linux/' + n + '.h' for n in ('types', 'gfp', 'atomic', 'mutex', 'rwsem', 'spinlock',
                      'rcupdate', 'err', 'wait', 'pagemap_netbsd', 'sched', 'task_netbsd', 'task_entry_preallocated')]
        for name in delegated:
            target = include / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'#include "test_model.h"\n')
        state['inputs_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
        command = ['cc', '-std=gnu11', '-O2', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-function', '-Wno-unused-parameter', '-DNDEBUG',
                   '-I' + str(source), '-I' + str(include), str(source / 'test_file_lifecycle.c'), '-o', str(output / 'model')]
        state['command'] = command
        save()
        code, _ = run(command, 'compile.log', 90)
        state['compile_exit'] = code
        if code:
            raise RuntimeError('positive actual FILE C compile failed')
        code, data = run([str(output / 'model')], 'positive.log')
        state['positive_exit'] = code
        state['positive_cases'] = [line.decode() for line in data.splitlines() if line.startswith(b'PASS ')]
        if code or len(state['positive_cases']) != 11 or b'NATIVE_FILE_MODEL_PASS cases=11 ' not in data:
            raise RuntimeError('positive FILE lifetime cases failed')
        state['fatal_controls'] = []
        for name, diagnostic in (
                ('ref-underflow', 'imbalanced file reference'), ('ref-resurrect', 'reference already released'),
                ('ref-zero-init', 'invalid initial count'), ('missing-reservation', 'no reservation in the current descriptor table'),
                ('wrong-fd-table', 'no reservation in the current descriptor table'), ('invalid-install', 'invalid consumed Linux file reference')):
            code, data = run([str(output / 'model'), name], name + '.log', 20)
            matched = code == -signal.SIGABRT and diagnostic.encode() in data
            state['fatal_controls'].append(dict(case=name, exit=code, required_diagnostic=diagnostic, matched=matched))
            save()
            if not matched:
                raise RuntimeError('strict fatal control failed: ' + name)
        if any(sha(output / name) != expected for name, expected in state['inputs_sha256'].items()):
            raise RuntimeError('source/model inputs changed during proof')
        state['state'] = 'PASS'
    except BaseException as error:
        state.update(state='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        state['artifacts_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p != receipt}
        save()
        print('NATIVE_FILE_MODEL_' + state['state'] + ' native_kernel_acceptance=OPEN')


if __name__ == '__main__':
    main()
