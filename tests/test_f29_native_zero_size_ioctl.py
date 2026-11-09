#!/usr/bin/env python3
"""Pinned F29 native marshalling plus actual DRM dispatcher source test.

All allocator, descriptor, file and user-access surroundings are explicit models.
This is not native kernel-header, full-link, concurrent or hardware acceptance.
"""
import argparse
import datetime
import hashlib
import importlib.util
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
from check_f29_native_zero_size_patch import AFTER, BEFORE, PATCH, PATCH_SHA256, stage

OWNER = ROOT / 'compat/native-drm'
spec = importlib.util.spec_from_file_location('f29_ioctl_derivation', OWNER / 'prepare_ioctl_patch.py')
derivation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(derivation)
FIXTURE = ROOT / 'tests/fixtures/f29_native_ioctl_bridge.c'
FIXTURE_SHA256 = '49558ca1fb831e67a86cb60a2c56c4b00f714087f9098f2bc7d2f9c81c1e1d9e'
FUNCTIONS = ('drm_ioctl_permit', 'drm_ioctl_kernel', 'drm_ioctl_dispatch',
             'drm_ioctl', 'drm_ioctl_kernel_data')
CASES = ('forged_get_cap_zero_size', 'zero_size_large_canonical',
         'linux_read_write_16', 'linux_write_only_16', 'linux_read_only_16',
         'legacy_zero_size_preserves_user_address',
         'non_drm_hook_zero_size_preserves_user_address',
         'copyin_fault_before_callback', 'highbit_rejected_before_uaccess',
         'oversized_native_argument_rejected', 'null_user_zero_size_get_cap')
FLAGS = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('source control anchor changed: ' + before[:70])
    return text.replace(before, after, 1)


def function(text, name):
    start = re.search(r'(?m)^(?:static\s+)?(?:int|long)\s+' +
                      re.escape(name) + r'\([^;{]*\)\n\{', text)
    if start is None:
        raise ValueError('actual source function missing: ' + name)
    opening = text.index('{', start.start())
    tokens = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|'
                        r"'(?:\\.|[^'\\])*'|[{}]")
    depth = 0
    for token in tokens.finditer(text, opening):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return text[start.start():token.end()] + '\n'
    raise ValueError('unbalanced actual function: ' + name)


def native_fragments(text):
    complete = function(text, 'sys_ioctl')
    start = complete.index('\t/* Translate Linux DRM ioctl direction bits before any user memory IO. */\n')
    end = complete.index('\n\t/*\n\t * Interpret high order word', start)
    early = complete[start:end] + '\n'
    size = '\tsize = IOCPARM_LEN(com);\n\talloc_size = size;\n'
    if complete.count(size) != 1:
        raise ValueError('native size assignment changed')
    start = complete.index('\tif (size > IOCPARM_MAX) {\n')
    end = complete.index('\n\tswitch (com) {', start)
    marshal = complete[start:end] + '\n'
    if marshal.count('if (linux_drm_ioctl && size == 0)') != 1:
        raise ValueError('F29 domain guard missing')
    return complete, dict(early=early, size=size, marshal=marshal)


def controls(native, drm):
    guard = 'if (linux_drm_ioctl && size == 0)'
    return [
        ('remove_zero_guard', once(native, guard, 'if (false)'), drm, CASES[0], 'data == NULL'),
        ('broaden_zero_guard_to_legacy', once(native, guard, 'if (size == 0)'), drm,
         CASES[5], 'native_seen_data == user_bytes'),
        ('guard_only_raw_zero_command', once(native, guard,
            'if (linux_drm_ioctl && (com >> IOCPARM_SHIFT) == 0)'), drm, CASES[0], 'data == NULL'),
        ('remove_direction_translation', once(native, 'if (linux_drm_ioctl) {', 'if (false) {'),
         drm, CASES[3], 'memcmp(data, callback_prefix, callback_prefix_size) == 0'),
        ('remove_highbit_guard', once(native,
            'if (linux_drm_ioctl && (com & IOC_VOID) != 0)', 'if (false)'),
         drm, CASES[8], 'error == ENOTTY'),
        ('clear_data_for_all_drm_sizes', once(native, guard, 'if (linux_drm_ioctl)'),
         drm, CASES[2], 'error == 0'),
        ('remove_canonical_zero_extension', native, once(drm,
            'memset(kdata + in_size, 0, ksize - in_size);',
            'memset(kdata + in_size, 0xa5, ksize - in_size);'), CASES[0], 'p[i] == 0'),
        ('dispatch_into_native_pointer', native, once(drm,
            'retcode = drm_ioctl_kernel(filp, func, kdata, ioctl->flags);',
            'retcode = drm_ioctl_kernel(filp, func, native_out_size ? native_data : kdata, ioctl->flags);'),
         CASES[0], 'data != NULL'),
    ]


def disable_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--linux-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    linux_path = args.linux_source.resolve(strict=True)
    linux = linux_path.read_bytes()
    derived = derivation.derive(linux)
    contract = json.loads((OWNER / 'drm_ioctl_kernel_data.json').read_text())
    fixture = FIXTURE.read_bytes()
    if sha(fixture) != FIXTURE_SHA256 or sha(derived) != contract['after_sha256']:
        raise ValueError('reviewed fixture or complete derived dispatcher changed')
    drm = '\n'.join(function(derived.decode(), name) for name in FUNCTIONS)
    output, tree, native_receipt = stage(args.native_source, args.output)
    complete, fragments = native_fragments((tree / 'sys/kern/sys_generic.c').read_text())
    native = fragments['early'] + fragments['size'] + fragments['marshal']
    report = dict(state='RUNNING', started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        host=os.uname().nodename, pid=os.getpid(), native_source_receipt=native_receipt,
        linux_source=str(linux_path), linux_source_sha256=sha(linux),
        derived_complete_source_sha256=sha(derived), actual_drm_functions_sha256=sha(drm.encode()),
        complete_patched_sys_ioctl_sha256=sha(complete.encode()),
        native_excerpt_sha256={key:sha(value.encode()) for key,value in fragments.items()},
        patch_sha256=PATCH_SHA256, fixture_sha256=sha(fixture), commands=[], variants=[],
        source_sha256={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in
            (PATCH, FIXTURE, Path(__file__), ROOT/'tools/check_f29_native_zero_size_patch.py')},
        native_kernel_headers='NOT_RUN', full_kernel='NOT_RUN', hardware='NOT_RUN',
        limitation='Exact unchanged native source excerpts and five real DRM functions with modeled FD/file/DRM/allocator/uaccess surroundings only')
    receipt = output / 'status.json'
    def save():
        temporary = output/'status.tmp'
        temporary.write_text(json.dumps(report,indent=2)+'\n')
        temporary.replace(receipt)
    def run(argv, name):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=120,
                                preexec_fn=disable_core)
        (output/(name+'.stdout.log')).write_text(result.stdout)
        (output/(name+'.stderr.log')).write_text(result.stderr)
        report['commands'].append(dict(command=argv,exit_code=result.returncode,
            stdout_sha256=sha(result.stdout.encode()),stderr_sha256=sha(result.stderr.encode())))
        save()
        return result
    save()
    try:
        variants = [('actual', native, drm, None, None), *controls(native, drm)]
        for name, native_body, drm_body, failing_case, assertion in variants:
            offset = native_body.index(fragments['size'])
            bodies = dict(early=native_body[:offset], size=fragments['size'],
                          marshal=native_body[offset+len(fragments['size']):])
            generated = fixture.decode()
            for key,value in bodies.items():
                marker = '/* ACTUAL_NATIVE_' + key.upper() + ' */'
                generated = once(generated, marker, value)
            generated = once(generated, '/* ACTUAL_DRM_FUNCTIONS */', drm_body)
            cfile, binary = output/(name+'.c'), output/name
            cfile.write_text(generated)
            row = dict(name=name, generated_source_sha256=sha(generated.encode()))
            report['variants'].append(row)
            save()
            if name == 'actual':
                syntax = run(['/usr/bin/cc', *FLAGS, '-fsyntax-only', str(cfile)], 'actual.syntax')
                row['syntax_exit'] = syntax.returncode
                if syntax.returncode != 0:
                    raise RuntimeError('new combined C syntax failed; inspect actual.syntax.stderr.log')
            built = run(['/usr/bin/cc', *FLAGS, str(cfile), '-o', str(binary)], name+'.compile')
            row['compile_exit'] = built.returncode
            save()
            if built.returncode != 0:
                raise RuntimeError('combined source/control failed to compile: '+name)
            result = run([str(binary)], name+'.run')
            passed = re.findall(r'(?m)^PASS (\w+)$', result.stdout)
            started = re.findall(r'(?m)^RUN (\w+)$', result.stdout)
            row.update(run_exit=result.returncode, passed_cases=passed, started_cases=started,
                       binary_sha256=sha(binary.read_bytes()))
            if failing_case is None:
                accepted = (result.returncode == 0 and passed == list(CASES)
                            and started == list(CASES) and result.stderr == ''
                            and 'F29_NATIVE_IOCTL_SOURCE_PASS 11\n' in result.stdout)
            else:
                index = CASES.index(failing_case)
                row.update(expected_case=failing_case,expected_assertion=assertion)
                accepted = (result.returncode == -signal.SIGABRT
                    and passed == list(CASES[:index]) and started == list(CASES[:index+1])
                    and 'CHECK_FAILED '+assertion+'\n' in result.stderr)
            row['accepted'] = accepted
            save()
            if not accepted:
                raise RuntimeError('strict source/control acceptance differs: '+name)
            print('F29 '+name+' PASS',flush=True)
        if linux_path.read_bytes() != linux or sha(PATCH.read_bytes()) != PATCH_SHA256:
            raise ValueError('frozen source changed during test')
        if {rel:sha((args.native_source/rel).read_bytes()) for rel in BEFORE} != BEFORE:
            raise ValueError('original native source changed during test')
        if {rel:sha((tree/rel).read_bytes()) for rel in AFTER} != AFTER:
            raise ValueError('private applied source changed during test')
        report.update(state='PASS',baseline_cases=len(CASES),negative_controls=len(variants)-1)
    except BaseException as error:
        report.update(state='FAIL',error=str(error))
        raise
    finally:
        report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print(json.dumps(dict(state=report['state'],baseline_cases=len(CASES),
                          negative_controls=len(variants)-1,receipt=str(receipt))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
