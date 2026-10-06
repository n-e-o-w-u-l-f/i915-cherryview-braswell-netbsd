#!/usr/bin/env python3
"""Generate one native task runtime and the selected frozen callback/worker APIs.

Source generation is independent of compilation. Native entry attachment,
fatal-only sleeps, unload admission/draining and full VM/PID/IO remain gates.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from namespace_linux_compiler_math import bindings, frozen, translate
ASSETS = ROOT / 'compat/native-runtime'
NETBSD_PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
LINUX_PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
PREFIX = 'sys/external/bsd/drm2/'
EXPECTED = {
    'task/linux_task.c': 'd434fcaa9dea2e01d52b44605c3b2eedf9045550b1ff9c572c19e85eb0600ee4',
    'task/linux_wait.c': '4a933c0bb0cbf5c2483c22d8fb7a36b7166d0b52b2e30bf9223d69d9a8cd0c69',
    'task/linux_wait_var.c': 'c9493b685923c0f89fb5c6e752db753c8ee2801fd4e97643644686d71ce23920',
    'task/include/linux/task_netbsd.h': '293683066abd75d96f6cb486c7ed7d20e11ba0955380b2aa6f64f77d9976af68',
    'task/include/linux/sched.h': '4ce0c06140c7048bf079aabcaaa8a28800f0668fa76d6d618037974caa8f0ff4',
    'task/include/linux/wait.h': '61ef59279676174b3394e88451ff828a83bff7c50d679b4a946d3daee45dfa86',
    'task/include/linux/wait_bit.h': '03c6c7fad5f76cbb64b2813eac9db4f98f0ba28376da2cdff404b5c16631490e',
    'worker/linux_kthread.c': '31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274',
    'worker/include/linux/kthread.h': '97c094ab5fbc3688334875500c23d5053186d35e6342d2668ce63659335b8814',
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('unexpected native source anchor: ' + old[:100])
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netbsd-tree', type=Path, required=True)
    parser.add_argument('--linux-tree', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('preserve existing generated patch')
    for tree, pin in [(args.netbsd_tree, NETBSD_PIN), (args.linux_tree, LINUX_PIN)]:
        if subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'],
                                   text=True).strip() != pin:
            parser.error('different frozen source revision')

    def native(path):
        return subprocess.check_output(['git', '-C', str(args.netbsd_tree),
                                        'show', NETBSD_PIN + ':' + path], text=True)

    changes = []

    def diff(path, old, new):
        changes.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                            'a/' + path, 'b/' + path, n=1))

    with tempfile.TemporaryDirectory(prefix='native-runtime-source-') as name:
        temp = Path(name)
        shutil.copytree(ASSETS / 'task', temp / 'task')
        shutil.copytree(ASSETS / 'worker', temp / 'worker')
        headers = temp / 'task/include/linux'
        headers.mkdir(parents=True, exist_ok=True)
        for name, target in [('task_netbsd.h', 'task_netbsd.h'), ('sched.h', 'sched.h')]:
            shutil.copyfile(temp / 'task' / name, headers / target)
        (temp / 'worker/include/linux').mkdir(parents=True)
        env = dict(os.environ, NETBSD_RUNTIME_LINUX_TREE=str(args.linux_tree.resolve()),
                   NETBSD_RUNTIME_WAIT_OUTPUT=str(temp / 'task'))
        for script in ['generate_wait.py', 'generate_wait_var.py']:
            subprocess.run([sys.executable, str(temp / 'task' / script)],
                           env=env, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(temp / 'worker/generate.py')], check=True)
        worker = temp / 'worker/linux_kthread.c'
        data = replace_once(worker.read_text(),
            'void\nlinux_kthread_fini(void)\n{\n\n\tlinux_task_system_fini();\n}',
            'void\nlinux_kthread_fini(void)\n{\n\tint error;\n\n'
            '\terror = linux_task_system_fini();\n\tKASSERT(error == 0);\n}')
        worker.write_text(data)
        # Explicit final-newline normalization preserves every function body.
        for relative in EXPECTED:
            path = temp / relative
            path.write_bytes(path.read_bytes().rstrip(b'\n') + b'\n')
        for relative, expected in EXPECTED.items():
            if hashlib.sha256((temp / relative).read_bytes()).hexdigest() != expected:
                raise RuntimeError('candidate differs from recorded HP source: ' + relative)
        for group, names in [('task', ['linux_task.c', 'linux_wait.c', 'linux_wait_var.c']),
                             ('worker', ['linux_kthread.c'])]:
            for name in names:
                path = PREFIX + 'linux/' + name
                old = native(path) if name == 'linux_kthread.c' else ''
                diff(path, old, (temp / group / name).read_text())
        for group, names in [('task', ['task_netbsd.h', 'sched.h', 'wait.h', 'wait_bit.h']),
                             ('worker', ['kthread.h'])]:
            for name in names:
                path = PREFIX + 'include/linux/' + name
                old = '' if name == 'task_netbsd.h' else native(path)
                diff(path, old, (temp / group / 'include/linux' / name).read_text())

    path = 'sys/external/bsd/common/include/linux/completion.h'
    # Prior completion patch0028 owns the real CV implementation. This hunk
    # changes only its include contract and applies before or after0028.
    old = native(path)
    diff(path, old, replace_once(old, '#include <linux/errno.h>\n',
                                '#include <linux/errno.h>\n#include <linux/wait.h>\n'))
    path = 'sys/external/bsd/common/include/linux/math.h'
    old = translate(frozen(args.linux_tree, 'include/linux/math.h'), bindings(args.linux_tree))
    # The arithmetic depends on const.h. Linux's UAPI kernel umbrella also
    # imports a second sysinfo layout into native mm.h consumers. Retain the
    # exact const macros directly; sysinfo/UVM ownership remains a separate port.
    diff(path, old, replace_once(old, '#include <uapi/linux/kernel.h>\n',
                                '#include <linux/const.h>\n'))
    path = PREFIX + 'linux/files.drmkms_linux'
    old = native(path)
    anchor = 'file\texternal/bsd/drm2/linux/linux_kthread.c\t\tdrmkms_linux\n'
    diff(path, old, replace_once(old, anchor, anchor +
         ''.join('file\texternal/bsd/drm2/linux/' + name + '\tdrmkms_linux\n'
                 for name in ['linux_task.c', 'linux_wait.c', 'linux_wait_var.c'])))
    path = 'sys/modules/drmkms_linux/Makefile'
    old = native(path)
    addition = ''.join('SRCS+=\t' + name + '\n' for name in
                       ['linux_kthread.c', 'linux_task.c', 'linux_wait.c', 'linux_wait_var.c'])
    diff(path, old, replace_once(old, 'SRCS+=\tlinux_module.c\n',
                                'SRCS+=\tlinux_module.c\n' + addition))
    path = PREFIX + 'linux/linux_module.c'
    old = native(path)
    new = replace_once(old, '\tlinux_irq_work_init();\n',
                       '\terror = linux_wait_var_init();\n\tif (error) {\n'
                       '\t\tprintf("linux: unable to initialize variable waits: %d\\n", error);\n'
                       '\t\tgoto fail9;\n\t}\n\n\tlinux_irq_work_init();\n')
    new = replace_once(new, 'fail9: __unused\n', 'fail9:\n')
    new = replace_once(new, '\tlinux_irq_work_fini();\n\tlinux_kthread_fini();\n',
                       '\tlinux_irq_work_fini();\n\tlinux_wait_var_fini();\n'
                       '\tlinux_kthread_fini();\n')
    new = replace_once(new,
                       '\tcase MODULE_CMD_FINI:\n\t\tlinux_fini();\n\t\treturn 0;',
                       '\tcase MODULE_CMD_FINI: {\n'
                       '\t\tint error = linux_task_system_quiesce();\n'
                       '\t\tif (error != 0)\n\t\t\treturn error;\n'
                       '\t\tlinux_fini();\n\t\treturn 0;\n\t}')
    diff(path, old, new)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(''.join(changes))
    print('NATIVE_TASK_WAIT_WORKER_PATCH_GENERATED sources=4 shared_task_runtime=1')


if __name__ == '__main__':
    main()
