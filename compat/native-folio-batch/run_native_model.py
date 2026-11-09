#!/usr/bin/env python3
"""Actual bounded folio batch C plus explicit page-owner delegation on HP11."""
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
        raise ValueError('new absolute output without redirected ancestors required')
    output.mkdir()
    source, include = output / 'source', output / 'include'
    source.mkdir()
    include.mkdir()
    state = dict(state='PREPARED', scope='Actual folio batch C with explicit native-page-owner delegation. Real Native UAO/queue/runtime acceptance OPEN.',
                 positive_expected=8, fatal_expected=6)
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
        for name in ('linux_folio_batch.c', 'test_model.h', 'test_folio_batch.c'):
            (source / name).write_bytes((HERE / name).read_bytes().replace(b'\r\n', b'\n'))
        target = include / 'linux/folio_batch_netbsd.h'
        target.parent.mkdir()
        target.write_bytes((HERE / 'include/linux/folio_batch_netbsd.h').read_bytes().replace(b'\r\n', b'\n'))
        state['inputs_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
        command = ['cc', '-std=gnu11', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-DNDEBUG',
                   '-I' + str(source), '-I' + str(include), str(source / 'test_folio_batch.c'), '-o', str(output / 'model')]
        state['command'] = command
        save()
        code, _ = run(command, 'compile.log', 90)
        state['compile_exit'] = code
        if code:
            raise RuntimeError('positive C compile failed')
        code, data = run([str(output / 'model')], 'positive.log')
        state['positive_exit'] = code
        state['positive_cases'] = [line.decode() for line in data.splitlines() if line.startswith(b'PASS ')]
        if code or len(state['positive_cases']) != 8 or b'NATIVE_FOLIO_BATCH_MODEL_PASS cases=8 ' not in data:
            raise RuntimeError('positive ownership cases failed')
        state['fatal_controls'] = []
        for name, diagnostic in (
                ('full', 'missing owner or full batch'), ('null', 'missing owner or full batch'),
                ('bad-count', 'invalid count/cursor'), ('bad-cursor', 'invalid count/cursor'),
                ('missing-wire', 'missing live native wire'), ('dead-owner', 'missing live native wire')):
            code, data = run([str(output / 'model'), name], name + '.log', 20)
            matched = code == -signal.SIGABRT and diagnostic.encode() in data
            state['fatal_controls'].append(dict(case=name, exit=code, required_diagnostic=diagnostic, matched=matched))
            save()
            if not matched:
                raise RuntimeError('strict fatal control failed: ' + name)
        if any(sha(output / name) != expected for name, expected in state['inputs_sha256'].items()):
            raise RuntimeError('source/model input drift')
        state['state'] = 'PASS'
    except BaseException as error:
        state.update(state='FAIL', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        state['artifacts_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p != receipt}
        save()
        print('NATIVE_FOLIO_BATCH_MODEL_' + state['state'] + ' native_kernel_acceptance=OPEN')


if __name__ == '__main__':
    main()
