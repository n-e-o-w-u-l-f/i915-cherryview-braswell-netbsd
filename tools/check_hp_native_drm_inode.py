#!/usr/bin/env python3
"""Compile the native inode owner with real HP kernel headers; test separately.

This is an inode-component check, not the full modern DRM adapter replay.
The userspace allocator/atomic fixture never substitutes kernel ABI headers.
No kernel or device is installed, loaded or changed.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import signal
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
COMPONENT = Path('compat/native-drm-inode')
FILES = [COMPONENT / 'native_drm_inode.c', COMPONENT / 'native_drm_inode.h',
         Path('tests/fixtures/native_drm_inode_model.h'),
         Path('tests/fixtures/native_drm_inode_test.c'),
         Path('tools/check_hp_native_drm_inode.py')]
CASES = ['invalid_arguments_and_mode', 'allocation_failure_clears_output',
         'identity_initial_reference_and_exact_final_free', 'retain_then_last_drop',
         'zero_reference_not_resurrected', 'saturated_reference_not_incremented',
         'zero_and_null_put_panic', 'concurrent_two_threads_parent_owned',
         'concurrent_four_threads_parent_owned']
MUTANTS = [
    ('zero_resurrection', 'count == 0 || count == UINT_MAX', 'count == UINT_MAX',
     4, '!native_drm_inode_tryget(&inode)'),
    ('overflow', 'count == 0 || count == UINT_MAX', 'count == 0',
     5, '!native_drm_inode_tryget(&inode)'),
    ('missing_final_free', 'kmem_free(inode, sizeof(*inode));', '(void)inode;',
     2, 'inode_model_frees == 1'),
    ('premature_free', 'if (count != 1)\n\t\treturn;', '(void)count;',
     3, 'inode_model_frees == 0'),
    ('wrong_free_size', 'kmem_free(inode, sizeof(*inode));', 'kmem_free(inode, sizeof(inode));',
     2, 'size == inode_model_allocation_size'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv, *, cwd=None, timeout=60):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    return dict(command=[str(x) for x in argv], cwd=str(cwd or Path.cwd()),
                exit_code=result.returncode, stdout=result.stdout,
                stderr=result.stderr)


def checked(argv, *, cwd=None):
    row = run(argv, cwd=cwd)
    if row['exit_code']:
        raise RuntimeError(json.dumps(row))
    return row['stdout'].strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netbsd-source', type=Path, required=True)
    parser.add_argument('--kernel-obj', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (platform.system() != 'NetBSD' or platform.release().split('.')[0] != '11'
            or platform.machine() != 'amd64'
            or socket.gethostname().split('.')[0].lower() != 'hp-tpnw121'
            or os.geteuid() == 0):
        raise RuntimeError('requires non-root execution on HP NetBSD 11 amd64')
    source = args.netbsd_source.resolve(strict=True)
    obj = args.kernel_obj.resolve(strict=True)
    output = args.output.parent.resolve(strict=True) / args.output.name
    if (args.output.name in ('', '.', '..') or output.exists()
            or args.output.is_symlink()):
        raise RuntimeError('output must be a new directory under an existing parent')
    if (source == ROOT or output.is_relative_to(source) or output.is_relative_to(obj)
            or output.is_relative_to(ROOT)):
        raise RuntimeError('output must not overwrite source/configured kernel inputs')
    if checked(['git', '-C', source, 'rev-parse', 'HEAD']) != PIN:
        raise RuntimeError('foreign NetBSD source pin')
    if checked(['git', '-C', source, 'status', '--porcelain']):
        raise RuntimeError('pinned NetBSD source must remain clean')
    if checked(['git', '-C', ROOT, 'diff', '--name-only']):
        raise RuntimeError('test source changes must be staged and identifiable')
    for path in FILES:
        indexed = subprocess.run(['git', '-C', str(ROOT), 'show', ':' + str(path)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
        if hashlib.sha256(indexed).hexdigest() != sha(ROOT / path):
            raise RuntimeError('test source does not equal indexed blob: ' + str(path))
    make = '/usr/tools/bin/nbmake-amd64'
    values = {name: checked([make, '-C', obj, '-v', name])
              for name in ('CC', 'CFLAGS', 'CPPFLAGS', 'S')}
    compiler = shlex.split(values['CC'])
    if compiler != ['/usr/tools/bin/x86_64--netbsd-gcc']:
        raise RuntimeError('unexpected configured native compiler')
    configured_sys = Path(values['S']).resolve(strict=True)
    cpp = shlex.split(values['CPPFLAGS'])
    # Preserve actual generated options and kernel flags. Only relocate the
    # configured source prefix to the clean, independently pinned source.
    old = str(configured_sys.parent)
    cpp = [a.replace(old + '/', str(source) + '/') for a in cpp]
    flags = shlex.split(values['CFLAGS']) + cpp
    if not {'-D_KERNEL', '-nostdinc', '-Werror'}.issubset(flags):
        raise RuntimeError('configured native kernel compiler flags missing')
    if any('-DNATIVE_DRM_INODE_TEST' in a for a in flags):
        raise RuntimeError('model macro must never enter kernel compilation')
    receipt = dict(schema_version=1, status='RUNNING',
                   observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   scope='native synthetic character-inode component only',
                   system=platform.platform(), host=socket.gethostname(), uid=os.geteuid(),
                   netbsd_pin=PIN, netbsd_source=str(source), kernel_obj=str(obj),
                   configured_source_sys=str(configured_sys), native_make_values=values,
                   makefile_sha256=sha(obj / 'Makefile'),
                   source_head=checked(['git', '-C', ROOT, 'rev-parse', 'HEAD']),
                   source_tree=checked(['git', '-C', ROOT, 'write-tree']),
                   source_sha256={str(p): sha(ROOT / p) for p in FILES},
                   source_root=str(ROOT),
                   full_adapter='NOT_RUN_MISSING_FILE_MM_POLL_DRM_PROVIDERS',
                   full_kernel='NOT_RUN', physical_acceptance='NOT_RUN',
                   installed=False, booted=False, commands=[])
    prior_kernel = obj / 'netbsd'
    receipt['unchanged_prior_kernel_sha256'] = sha(prior_kernel)
    output.mkdir()
    receipt_path = output / 'receipt.json'

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')

    def required(argv, cwd=None):
        row = run(argv, cwd=cwd)
        receipt['commands'].append(row)
        save()
        if row['exit_code']:
            raise RuntimeError('command failed: ' + ' '.join(row['command']))
        return row

    save()
    try:
        receipt['booted_kernel'] = checked(['/sbin/sysctl', '-n', 'machdep.booted_kernel'])
        receipt['compiler_version'] = checked(compiler + ['--version'])
        native = output / 'native_drm_inode.o'
        dep = output / 'native_drm_inode.d'
        required(compiler + flags + ['-I' + str(ROOT / COMPONENT), '-MD', '-MF', str(dep),
                                    '-c', str(ROOT / COMPONENT / 'native_drm_inode.c'),
                                    '-o', str(native)], cwd=obj)
        # Header closure from the real compiler. Never use test fixture headers.
        deps = shlex.split(dep.read_text(encoding='utf8').replace('\\\n', ' ').split(':', 1)[1])
        header_paths = sorted({(Path(x) if Path(x).is_absolute() else obj / x).resolve(strict=True)
                               for x in deps if x.endswith('.h')})
        if any('native_drm_inode_model.h' == p.name for p in header_paths):
            raise RuntimeError('model header contaminated native kernel ABI check')
        receipt['native_headers_sha256'] = {str(p): sha(p) for p in header_paths}
        receipt['header_provenance'] = {}
        for path in header_paths:
            if path.is_relative_to(source):
                owner = 'clean pinned NetBSD source'
            elif path.is_relative_to(ROOT / COMPONENT):
                owner = 'reviewed component public header'
            elif path.is_relative_to(obj):
                owner = 'hashed configured kernel generated header'
            elif path.is_relative_to(configured_sys.parent):
                counterpart = source / path.relative_to(configured_sys.parent)
                if not counterpart.is_file() or sha(path) != sha(counterpart):
                    raise RuntimeError('configured source header differs from pinned source: ' + str(path))
                owner = 'configured machine symlink; byte equal to pinned source ' + str(counterpart)
            else:
                raise RuntimeError('unqualified native header owner: ' + str(path))
            receipt['header_provenance'][str(path)] = owner
        for name in ('types.h', 'atomic.h', 'systm.h', 'kmem.h', 'stat.h', 'errno.h'):
            path = source / 'sys/sys' / name
            if path.resolve() not in header_paths:
                raise RuntimeError('expected actual native header not consumed: ' + name)
        receipt['native_object_sha256'] = sha(native)
        receipt['native_object_size'] = native.stat().st_size
        undefined = required(['/usr/tools/bin/x86_64--netbsd-nm', '-u', str(native)])['stdout']
        receipt['undefined_native_symbols'] = sorted(line.split()[-1] for line in undefined.splitlines())
        required(['/usr/tools/bin/x86_64--netbsd-nm', '-g', '--defined-only', str(native)])
        providers = checked(['/usr/tools/bin/x86_64--netbsd-nm', '-g', '--defined-only', str(prior_kernel)])
        defined = {line.split()[-1] for line in providers.splitlines() if line.split()}
        missing = sorted(set(receipt['undefined_native_symbols']) - defined)
        if missing:
            raise RuntimeError('native dependency has no provider in prior pinned kernel: ' + ', '.join(missing))
        receipt['native_symbol_providers'] = 'all component undefined symbols exist in unchanged prior native kernel; not a new link'
        model_flags = ['/usr/bin/cc', '-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
                       '-pthread', '-fsanitize=undefined', '-fno-sanitize-recover=all',
                       '-I' + str(ROOT / 'tests/fixtures')]
        fixture = ROOT / 'tests/fixtures/native_drm_inode_test.c'
        executable = output / 'native_drm_inode_test'
        required(model_flags + [str(fixture), '-o', str(executable)])
        positive = required([str(executable)], cwd=output)
        expected = ['CASE_PASS ' + case for case in CASES] + ['NATIVE_DRM_INODE_CASES_PASS count=9']
        if positive['stdout'].splitlines() != expected or positive['stderr']:
            raise RuntimeError('positive model case oracle did not match')
        receipt['model_result'] = positive['stdout']
        receipt['semantic_negative_controls'] = []
        original = (ROOT / COMPONENT / 'native_drm_inode.c').read_text(encoding='utf8')
        for name, before, after, prefix, assertion in MUTANTS:
            if original.count(before) != 1:
                raise RuntimeError('mutation anchor is not unique: ' + name)
            mutation = original.replace(before, after)
            mutant_root = output / 'mutants' / name
            for rel in FILES[:4]:
                destination = mutant_root / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                if rel == COMPONENT / 'native_drm_inode.c':
                    destination.write_text(mutation, encoding='utf8')
                else:
                    shutil.copyfile(ROOT / rel, destination)
            mutant_fixture = mutant_root / 'tests/fixtures/native_drm_inode_test.c'
            mutant_binary = mutant_root / 'test'
            required(model_flags + [str(mutant_fixture), '-o', str(mutant_binary)])
            row = run([str(mutant_binary)], cwd=mutant_root)
            receipt['commands'].append(row)
            if (row['exit_code'] != -signal.SIGABRT
                    or row['stdout'].splitlines() != expected[:prefix]
                    or 'INODE_MODEL_PANIC MODEL_CHECK ' + assertion + ' at ' not in row['stderr']):
                raise RuntimeError('semantic mutation oracle mismatch: ' + name)
            receipt['semantic_negative_controls'].append(dict(
                name=name, mutated_source_sha256=sha(mutant_root / COMPONENT / 'native_drm_inode.c'),
                exit_code=row['exit_code'], expected_case_prefix=prefix,
                expected_assertion=assertion, status='REJECTED'))
            save()
        if any(sha(ROOT / p) != receipt['source_sha256'][str(p)] for p in FILES):
            raise RuntimeError('tested source changed during component check')
        if sha(obj / 'Makefile') != receipt['makefile_sha256']:
            raise RuntimeError('configured kernel Makefile changed during component check')
        if sha(prior_kernel) != receipt['unchanged_prior_kernel_sha256']:
            raise RuntimeError('prior kernel changed during component check')
        receipt['status'] = 'PASS'
        receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    except BaseException as error:
        receipt['status'] = 'FAIL'
        receipt['error'] = str(error)
        receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
        raise
    print(json.dumps(dict(status=receipt['status'], receipt=str(receipt_path),
                         native_object_sha256=receipt['native_object_sha256'],
                         model_result=receipt['model_result'])))


if __name__ == '__main__':
    main()
