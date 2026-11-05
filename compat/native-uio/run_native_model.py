#!/usr/bin/env python3
"""Source-bound UBUF/KVEC model, executable only on unprivileged HP NetBSD11."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import socket
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if (platform.system() != 'NetBSD' or platform.release().split('.')[0] != '11' or
            socket.gethostname().split('.')[0] != 'hp-tpnw121' or os.geteuid() == 0):
        raise ValueError('unprivileged HP NetBSD11 only')
    output = args.output
    if (not output.is_absolute() or output.exists() or output.is_symlink() or
            not output.parent.is_dir() or any(v.is_symlink() for v in output.parents)):
        raise ValueError('new absolute private output required; preserve failures')
    output.mkdir()
    source, include = output / 'source', output / 'include'
    source.mkdir()
    include.mkdir()
    status = dict(state='PREPARED', positive_expected=12, fatal_expected=6,
                  scope='Actual source adapter C with delegated errno/memory ownership APIs. Native kernel ABI/runtime/FILE I/O integration OPEN.')
    status_path = output / 'status.json'

    def save():
        status_path.write_bytes((json.dumps(status, indent=2) + '\n').encode())

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
        for name in ('linux_uio.c', 'test_model.h', 'test_uio.c'):
            (source / name).write_bytes((HERE / name).read_bytes().replace(b'\r\n', b'\n'))
        for original in sorted((HERE / 'include').rglob('*.h')):
            target = include / original.relative_to(HERE / 'include')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes().replace(b'\r\n', b'\n'))
        (include / 'linux/types.h').write_bytes(b'#include "test_model.h"\n')
        status['inputs_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
        command = ['cc', '-std=gnu11', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-DNDEBUG',
                   '-I' + str(source), '-I' + str(include), str(source / 'test_uio.c'), '-o', str(output / 'model')]
        status['command'] = command
        save()
        code, _ = run(command, 'compile.log', 90)
        status['compile_exit'] = code
        if code:
            raise RuntimeError('positive source-bound C compile failed')
        code, data = run([str(output / 'model')], 'positive.log')
        status['positive_exit'] = code
        names = [line.decode() for line in data.splitlines() if line.startswith(b'PASS ')]
        status['positive_cases'] = names
        if code or len(names) != 12 or b'NATIVE_UIO_MODEL_PASS cases=12 ' not in data:
            raise RuntimeError('positive I/O cases failed')
        status['fatal_controls'] = []
        for name, diagnostic in (
                ('bad-direction', 'invalid direction/iterator'), ('revert-before-start', 'before borrowed range'),
                ('expand-past-owner', 'outside borrowed range'), ('short-vectors', 'count exceeds borrowed vectors'),
                ('user-vector-array', 'invalid kernel vector owner'), ('missing-file', 'missing native file/request')):
            code, data = run([str(output / 'model'), name], name + '.log', 20)
            matched = code == -signal.SIGABRT and diagnostic.encode() in data
            status['fatal_controls'].append(dict(case=name, exit=code, required_diagnostic=diagnostic, matched=matched))
            save()
            if not matched:
                raise RuntimeError('strict fatal control failed: ' + name)
        if any(sha(output / name) != expected for name, expected in status['inputs_sha256'].items()):
            raise RuntimeError('source/model inputs changed during validation')
        status['state'] = 'PASS'
    except BaseException as error:
        status.update(state='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        status['artifacts_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p != status_path}
        save()
        print('NATIVE_UIO_MODEL_' + status['state'] + ' native_kernel_acceptance=OPEN')


if __name__ == '__main__':
    main()
