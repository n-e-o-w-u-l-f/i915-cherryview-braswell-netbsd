#!/usr/bin/env python3
"""Build the integrated runtime using HP's actual native kernel flags.

This object/relocatable-link check does not execute NetBSD scheduler code or
replace the required full kernel link and physical driver acceptance.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import shlex
import socket
import subprocess

WORK = Path('/root/hp-driver-port-20261005')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    parser.error('compilation/link probes are authorized only on HP/NetBSD')
out = args.output.resolve()
if out.parent != WORK or out.exists():
    parser.error('fresh isolated output directory required; preserve previous proofs')
out.mkdir()
tree = WORK / 'netbsd-full-linux'
stage = tree / 'sys/external/bsd/drm2'
line = next(line for line in (WORK / 'native-math64-drm_buddy.log').read_text().splitlines()
            if line.startswith(str(WORK / 'full-linux-tools/bin/x86_64--netbsd-gcc ')) and ' -c ' in line)
flags = shlex.split(line)
flags = flags[:flags.index('-c')]
state = {'state': 'RUNNING', 'host': socket.gethostname(),
         'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'checks': [], 'source_sha256': {}, 'header_sha256': {},
         'acceptance': 'OPEN: full kernel link, native scheduler/softint/lifecycle runtime and physical driver acceptance'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save():
    (out / 'status.json').write_text(json.dumps(state, indent=2) + '\n')


def run(name, command):
    result = subprocess.run(command, cwd=WORK / 'full-linux-obj',
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=180)
    log = out / (name + '.log')
    log.write_text(result.stdout)
    record = {'name': name, 'exit': result.returncode, 'command': command,
              'log_sha256': sha(log)}
    state['checks'].append(record)
    save()
    print(name, result.returncode, flush=True)
    if result.returncode:
        print(result.stdout, flush=True)
    return result.returncode


for name in ['sched.h', 'task_netbsd.h', 'wait.h', 'wait_bit.h', 'kthread.h']:
    state['header_sha256'][name] = sha(stage / 'include/linux' / name)
state['header_sha256']['completion.h'] = sha(tree / 'sys/external/bsd/common/include/linux/completion.h')
failures = []
objects = []
for name in ['linux_task', 'linux_wait', 'linux_wait_var', 'linux_kthread', 'linux_module']:
    source = stage / 'linux' / (name + '.c')
    obj = out / (name + '.o')
    state['source_sha256'][name + '.c'] = sha(source)
    rc = run(name, flags + ['-c', str(source), '-o', str(obj)])
    if rc:
        failures.append(name)
    else:
        state.setdefault('objects', {})[name] = {'bytes': obj.stat().st_size, 'sha256': sha(obj)}
        if name != 'linux_module':
            objects.append(obj)
if not any(name in failures for name in ['linux_task', 'linux_wait', 'linux_wait_var', 'linux_kthread']):
    linked = out / 'task-wait-worker.o'
    rc = run('shared-runtime-link', [str(WORK / 'full-linux-tools/bin/x86_64--netbsd-ld'),
                                    '-r', '-o', str(linked), *map(str, objects)])
    if rc:
        failures.append('shared-runtime-link')
    else:
        nm = subprocess.check_output(['/usr/bin/nm', '-g', str(linked)], text=True)
        (out / 'shared-runtime-nm.log').write_text(nm)
        unresolved = [line for line in nm.splitlines() if ' U linux_' in line]
        state['unresolved_shared_linux_symbols'] = unresolved
        if unresolved:
            failures.append('shared-runtime-symbols')
        state['linked_object'] = {'bytes': linked.stat().st_size, 'sha256': sha(linked)}
state['state'] = 'FAILED' if failures else 'PASSED'
state['failures'] = failures
state['updated'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
save()
raise SystemExit(bool(failures))
