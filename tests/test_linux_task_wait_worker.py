#!/usr/bin/env python3
"""HP-only execution of staged native C through explicit primitive models.

The pthread adapters exercise production functions, not native NetBSD kernel
execution. A separate native object/link proof is necessary for integration.
"""
from pathlib import Path
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORK = Path('/root/hp-driver-port-20261005')
STAGE = WORK / 'netbsd-full-linux/sys/external/bsd/drm2'
ASSETS = ROOT / 'compat/native-runtime'
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: native runtime compilation/tests are HP/NetBSD only')

with tempfile.TemporaryDirectory(prefix='hp-native-runtime-', dir=WORK) as name:
    temp = Path(name)
    patch = temp / 'runtime.patch'
    subprocess.run([sys.executable, str(ROOT / 'tools/generate_linux_task_wait_worker_patch.py'),
                    '--netbsd-tree', '/root/netbsd-src-ref',
                    '--linux-tree', '/root/linux-rtl8723be-ref-fresh',
                    '--out', str(patch)], check=True)
    assert patch.read_bytes() == (ROOT / 'patches/0032-netbsd-linux-task-wait-worker.patch').read_bytes()
    shutil.copytree(ASSETS / 'task', temp / 'task')
    shutil.copytree(ASSETS / 'worker', temp / 'worker')
    for group, names in [('task', ['linux_task.c', 'linux_wait.c', 'linux_wait_var.c']),
                         ('worker', ['linux_kthread.c'])]:
        for source in names:
            shutil.copyfile(STAGE / 'linux' / source, temp / group / source)
    for group, names in [('task', ['sched.h', 'task_netbsd.h', 'wait.h', 'wait_bit.h']),
                         ('worker', ['kthread.h'])]:
        include = temp / group / 'include/linux'
        include.mkdir(parents=True, exist_ok=True)
        for source in names:
            shutil.copyfile(STAGE / 'include/linux' / source, include / source)
    # Check actual staged input bytes, not a second implementation in fixtures.
    import importlib.util
    spec = importlib.util.spec_from_file_location('runtime_generator', ROOT / 'tools/generate_linux_task_wait_worker_patch.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    import hashlib
    for source, expected in generator.EXPECTED.items():
        assert hashlib.sha256((temp / source).read_bytes()).hexdigest() == expected, source
    env = dict(os.environ, NETBSD_RUNTIME_TEST_TASK=str(temp / 'task'))
    subprocess.run([sys.executable, str(temp / 'task/run_tests.py')], env=env, check=True)
    subprocess.run([sys.executable, str(temp / 'worker/tests/prepare.py')], check=True)
    exe = temp / 'worker/tests/check'
    subprocess.run(['/usr/bin/cc', '-D_NETBSD_SOURCE', '-std=gnu11', '-O2', '-g',
                    '-Wall', '-Wextra', '-Werror', '-pthread',
                    str(temp / 'worker/tests/test_worker.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=90)
print('NATIVE_TASK_WAIT_WORKER_MODEL_PASS one_task_runtime=1 keyed_vars=256 callback_lifetime=pass worker_tests=13')
