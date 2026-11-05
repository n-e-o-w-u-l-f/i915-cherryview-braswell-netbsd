#!/usr/bin/env python3
"""Run source-bound lifecycle C on HP11, explicitly delegated userland APIs."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import resource
import signal
import socket
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (platform.system() != 'NetBSD' or not platform.release().startswith('11.') or
            socket.gethostname() not in ('hp-tpnw121', 'hp-tpnw121.fritz.box') or os.geteuid() == 0):
        raise ValueError('native userland model execution requires unprivileged HP NetBSD11')
    output = args.output
    if not output.is_absolute() or any(p.is_symlink() for p in output.parents):
        raise ValueError('output must be absolute with no redirected ancestors')
    if output.exists() or output.is_symlink():
        raise ValueError('output must be new; failed evidence is retained')
    spec = importlib.util.spec_from_file_location('task_notifier_generator', HERE / 'generate.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    _, after, patch, metadata = generator.sources()
    output.mkdir(parents=True)
    include = output / 'include'
    source = output / 'source'
    include.mkdir()
    source.mkdir()
    status = {'state': 'PREPARED', 'scope': 'Actual generated task C, pthread-specificdata/CV/workqueue delegation. Native kernel ABI, actual IRQ/VM/sleepq/code-owner acceptance OPEN.',
              'positive_cases_expected': 8, 'strict_fatal_controls_expected': 6,
              'generated_source': metadata, 'compiler_results': [], 'fatal_controls': []}
    status_path = output / 'status.json'

    def save():
        status_path.write_bytes((json.dumps(status, indent=2) + '\n').encode())

    def run(command, log, timeout):
        # Strict expected aborts do not leave userland core files elsewhere.
        def no_core():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   cwd=output, start_new_session=True, preexec_fn=no_core)
        try:
            data, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            data, _ = process.communicate()
            (output / log).write_bytes(data)
            raise
        result = subprocess.CompletedProcess(command, process.returncode, data)
        (output / log).write_bytes(result.stdout)
        return result

    try:
        for path, name in ((generator.TASK, 'linux_task.c'), (generator.HEADER, 'linux/task_netbsd.h')):
            target = source / name if name.endswith('.c') else include / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(after[path])
        (include / 'linux/sched.h').write_bytes((ROOT / 'compat/native-runtime/task/sched.h').read_bytes().replace(b'\r\n', b'\n'))
        for name in ('test_model.h', 'test_task_notifier.c'):
            (source / name).write_bytes((HERE / name).read_bytes().replace(b'\r\n', b'\n'))
        for name in ('task_entry_preallocated.inc', 'task_quiesce_retained.inc'):
            (source / name).write_bytes((ROOT / 'compat/native-file' / name).read_bytes().replace(b'\r\n', b'\n'))
        headers = ['sys/' + n + '.h' for n in ('param', 'atomic', 'condvar', 'intr', 'kmem',
                   'lwp', 'proc', 'signalvar', 'sleepq', 'specificdata', 'systm', 'workqueue', 'kernel')]
        headers += ['linux/' + n + '.h' for n in ('raw_spinlock', 'spinlock', 'errno', 'kthread')]
        # Native pthread/sched.h and libc limits.h require their genuine
        # sys/sched.h and machine/limits.h, not delegated kernel wrappers.
        headers += ['asm/barrier.h', 'asm/param.h', 'asm/processor.h']
        for name in headers:
            target = include / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'#include "test_model.h"\n')
        (output / 'task-notifier.patch').write_bytes(patch.encode())
        status['input_sha256'] = {str(p.relative_to(output)): digest(p.read_bytes())
                                 for p in sorted(output.rglob('*')) if p.is_file()}
        command = ['cc', '-std=gnu11', '-O2', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-function', '-Wno-unused-parameter', '-I' + str(include),
                   '-I' + str(source), str(source / 'test_task_notifier.c'), '-o', str(output / 'model')]
        status['command'] = command
        save()
        compiled = run(command, 'compile.log', 90)
        status['compiler_results'].append({'exit': compiled.returncode, 'log': 'compile.log'})
        if compiled.returncode:
            raise RuntimeError('positive source-bound C compilation failed')
        positive = run([str(output / 'model')], 'positive.log', 60)
        status['positive_exit'] = positive.returncode
        expected = b'TASK_NOTIFIER_MODEL_PASS cases=8 '
        named = [line for line in positive.stdout.splitlines() if line.startswith(b'PASS ')]
        if positive.returncode != 0 or expected not in positive.stdout or len(named) != 8:
            raise RuntimeError('positive lifecycle cases failed')
        for name, diagnostic in (
                ('null-parent', b'missing parent owner'), ('shared-parent', b'invalid parent spare'),
                ('dead-parent', b'invalid parent spare'), ('attached-parent', b'invalid parent spare'),
                ('overflow', b'invalid/overflowed runtime owner'), ('underflow', b'reference underflow')):
            result = run([str(output / 'model'), name], name + '.log', 20)
            matched = result.returncode == -signal.SIGABRT and diagnostic in result.stdout
            status['fatal_controls'].append({'case': name, 'exit': result.returncode,
                                            'required_diagnostic': diagnostic.decode(), 'matched': matched})
            save()
            if not matched:
                raise RuntimeError('strict fatal control failed: ' + name)
        current = {name: digest((output / name).read_bytes()) for name in status['input_sha256']}
        if current != status['input_sha256']:
            raise RuntimeError('source/model inputs changed during execution')
        status['state'] = 'PASS'
    except BaseException as error:
        status['state'] = 'FAIL'
        status['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        status['artifact_sha256'] = {str(p.relative_to(output)): digest(p.read_bytes())
                                     for p in sorted(output.rglob('*')) if p.is_file() and p != status_path}
        save()
        print('TASK_NOTIFIER_MODEL_' + status['state'] + ' native_kernel_acceptance=OPEN')


if __name__ == '__main__':
    main()
