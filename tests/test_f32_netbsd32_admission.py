#!/usr/bin/env python3
"""Exact early NetBSD32 admission/unwind excerpts; FD/later-syscall stubs only.

No real Compat32 translation, native kernel-header, concurrency or hardware proof.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from check_f32_netbsd32_admission import AFTER, BEFORE, GUARD, RELATIVE, stage
from test_f29_native_zero_size_ioctl import function

FIXTURE = ROOT / 'tests/fixtures/f32_netbsd32_admission.c'
FIXTURE_SHA256 = 'a8ecce1451d248f1aec82a5408775f82747dc2e4495d1a848e6287bf9941a6d5'
CASES = ('modern_drm_all_commands', 'null_user_rejected', 'legacy_drm_preserved',
         'non_drm_hook_preserved', 'invalid_fd_rejected', 'missing_access_precedes_gate',
         'read_write_access_reaches_gate', 'fioclex_preserved', 'fionclex_preserved')
FLAGS = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('source control anchor drift: ' + before[:70])
    return text.replace(before, after, 1)


def excerpts(text):
    complete = function(text, 'netbsd32_ioctl')
    first = complete.index('\tmemp = NULL;\n')
    last = complete.index('\n\t/*\n\t * Interpret high order word', first)
    early = complete[first:last] + '\n'
    label = re.search(r'(?m)^[ \t]*out:\n', complete)
    if label is None or early.count(GUARD) != 1:
        raise ValueError('actual admission/unwind boundary differs')
    tail = complete[label.start():complete.rfind('}')] + '\n'
    if tail.count('fd_putfile(fd);') != 1:
        raise ValueError('actual descriptor release differs')
    return complete, early, tail


def controls(early, tail):
    predicate = "if (fp->f_ops != NULL && fp->f_ops->fo_ioctl_user != NULL &&\n\t    IOCGROUP(com) == 'd')"
    return [
        ('remove_gate', once(early, predicate, 'if (false)'), tail, CASES[0], 'result == ENOTTY'),
        ('reject_legacy_drm', once(early, predicate, "if (IOCGROUP(com) == 'd')"), tail,
         CASES[2], 'result == LEGACY_SENTINEL'),
        ('reject_non_drm_hook', once(early, predicate,
          'if (fp->f_ops != NULL && fp->f_ops->fo_ioctl_user != NULL)'), tail,
         CASES[3], 'result == LEGACY_SENTINEL'),
        ('wrong_errno', once(early, 'error = ENOTTY;', 'error = EINVAL;'), tail,
         CASES[0], 'result == ENOTTY'),
        ('return_without_fd_release', once(early,
          '\t\terror = ENOTTY;\n\t\tgoto out;\n', '\t\treturn ENOTTY;\n'), tail,
         CASES[0], 'get_calls == 1 && put_calls == 1'),
        ('omit_fd_putfile', early, once(tail, '\tfd_putfile(fd);',
          '\tif (false) fd_putfile(fd);'), CASES[0], 'get_calls == 1 && put_calls == 1'),
        ('ignore_descriptor_permissions', once(early,
          'if ((fp->f_flag & (FREAD | FWRITE)) == 0)', 'if (false)'), tail,
         CASES[5], "invoke(command('d', 16, 0xc0000000U), (void *)(uintptr_t)1) == EBADF"),
        ('invert_fioclex', once(early, 'com == FIOCLEX', 'com != FIOCLEX'), tail,
         CASES[7], 'cloexec_calls == 1 && cloexec_value'),
    ]


def disable_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = FIXTURE.read_bytes()
    if sha(fixture) != FIXTURE_SHA256:
        raise ValueError('reviewed environment fixture changed')
    original = (args.source / RELATIVE).read_bytes()
    if sha(original) != BEFORE:
        raise ValueError('pinned original differs')
    output, tree, native_receipt = stage(args.source, args.output)
    patched = (tree / RELATIVE).read_bytes()
    if sha(patched) != AFTER or patched.decode().replace(GUARD, '', 1).encode() != original:
        raise ValueError('native bytes outside the gate changed')
    complete, early, tail = excerpts(patched.decode())
    report = dict(state='RUNNING', started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  host=os.uname().nodename, pid=os.getpid(), native_source_receipt=native_receipt,
                  complete_patched_function_sha256=sha(complete.encode()),
                  actual_early_sha256=sha(early.encode()), actual_out_sha256=sha(tail.encode()),
                  fixture_sha256=sha(fixture), commands=[], variants=[],
                  limitation='Actual pinned early FD/FIOCLEX/admission/out source excerpts with explicit FD/later-body stubs; no real user-copy/conversion algorithm or Compat32 support.',
                  modern_direction_size_pairs=20, legacy_direction_size_pairs=20,
                  non_drm_direction_size_pairs=20,
                  native_kernel_headers='NOT_RUN', full_kernel='NOT_RUN', hardware='NOT_RUN')
    receipt = output / 'status.json'

    def save():
        temporary = output / 'status.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(receipt)

    def run(command, name):
        result = subprocess.run(command, capture_output=True, text=True, timeout=120,
                                preexec_fn=disable_core)
        (output / (name + '.stdout.log')).write_text(result.stdout)
        (output / (name + '.stderr.log')).write_text(result.stderr)
        report['commands'].append(dict(command=command, exit_code=result.returncode,
                                      stdout_sha256=sha(result.stdout.encode()),
                                      stderr_sha256=sha(result.stderr.encode())))
        save()
        return result

    save()
    try:
        variants = [('actual', early, tail, None, None), *controls(early, tail)]
        for name, selected_early, selected_tail, failing_case, assertion in variants:
            generated = once(fixture.decode(), '/* ACTUAL_EARLY */', selected_early)
            generated = once(generated, '/* ACTUAL_OUT */', selected_tail)
            source, binary = output / (name + '.c'), output / name
            source.write_text(generated)
            row = dict(name=name, generated_source_sha256=sha(generated.encode()))
            report['variants'].append(row)
            save()
            built = run(['/usr/bin/cc', *FLAGS, str(source), '-o', str(binary)], name + '.compile')
            row['compile_exit'] = built.returncode
            save()
            if built.returncode != 0:
                raise RuntimeError('source/control compile failed: ' + name)
            result = run([str(binary)], name + '.run')
            passed = re.findall(r'(?m)^PASS (\w+)$', result.stdout)
            started = re.findall(r'(?m)^RUN (\w+)$', result.stdout)
            row.update(run_exit=result.returncode, passed_cases=passed, started_cases=started,
                       binary_sha256=sha(binary.read_bytes()))
            if failing_case is None:
                accepted = (result.returncode == 0 and passed == list(CASES)
                            and started == list(CASES) and result.stderr == ''
                            and 'F32_SOURCE_ADMISSION_PASS 9\n' in result.stdout)
            else:
                index = CASES.index(failing_case)
                row.update(expected_case=failing_case, expected_assertion=assertion)
                accepted = (result.returncode == -signal.SIGABRT
                            and passed == list(CASES[:index])
                            and started == list(CASES[:index+1])
                            and 'CHECK_FAILED ' + assertion + '\n' in result.stderr)
            row['accepted'] = accepted
            save()
            if not accepted:
                raise RuntimeError('strict source/control acceptance differs: ' + name)
            print('F32', name, 'PASS', flush=True)
        if FIXTURE.read_bytes() != fixture or (args.source / RELATIVE).read_bytes() != original:
            raise ValueError('source input changed')
        if (tree / RELATIVE).read_bytes() != patched:
            raise ValueError('private patched source changed')
        report.update(state='PASS', baseline_cases=len(CASES), negative_controls=len(variants)-1,
                      native_bytes_outside_gate_unchanged=True)
    except BaseException as error:
        report.update(state='FAIL', error=str(error))
        raise
    finally:
        report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print(json.dumps(dict(state=report['state'], baseline_cases=len(CASES),
                          negative_controls=len(variants)-1, receipt=str(receipt))))


if __name__ == '__main__':
    main()
