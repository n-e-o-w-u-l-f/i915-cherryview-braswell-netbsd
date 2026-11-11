#!/usr/bin/env python3
"""Recover only the reviewed native Worker C/header from two pinned patch sections.

The historical generator and the other twelve patch owners are never executed.
Default mode checks and reports. --write creates the fixed fresh source-owned
output and writes its provenance last. A failed publication retains any new
partial directory for inspection; no atomic directory publication is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

REPOSITORY = Path(__file__).resolve().parents[1]
INPUT_COMMIT = 'e7d7100c44322d3209d8f43d1d3a3842b52b340b'
NETBSD_PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
OUTPUT_ROOT = 'compat/native-runtime/worker-f49'
PATCH = 'patches/0032-netbsd-linux-task-wait-worker.patch'
NATIVE_C = 'sys/external/bsd/drm2/linux/linux_kthread.c'
NATIVE_H = 'sys/external/bsd/drm2/include/linux/kthread.h'
BASE_C = 'compat/native-runtime/worker/base/linux_kthread.c'
BASE_H = 'compat/native-runtime/worker/base/kthread.h'
FRAGMENT_C = 'compat/native-runtime/worker/worker.inc'
FRAGMENT_H = 'compat/native-runtime/worker/worker_header.inc'
HISTORICAL_RECIPE = 'compat/native-runtime/worker/generate.py'
INTEGRATION_WITNESS = 'compat/native-runtime/worker/INTEGRATION.txt'
INPUTS = {
    BASE_C: dict(size=7207, sha256='566260787e456fe3ea40fb50f2cc93500faf0ccb4927a0a5e977777ad89d61bf', blob='a7735f8eb62a1ae697756deed51c718396e9b579', role='pinned_native_source'),
    BASE_H: dict(size=2546, sha256='4384d635d5049d38bd322009007b04808afeb30e4c99c0e484ba95bfbd10933b', blob='74af400efc77e55c821f11e7bafd7a499e141962', role='pinned_native_header'),
    PATCH: dict(size=130848, sha256='9b53ce73daba8b6937c54209e2ff28087775409c9be2c386a97301f3781737fd', blob='20e0b8bdcaaa29b5050e1ac353086604308f0cad', role='selected_final_patch_authority'),
    FRAGMENT_C: dict(size=10512, sha256='2ad653da9cb181aa9966e4e0e98b12c3fa0c197574f9d4f0021b9e744359001d', blob='54576a3a96d24f51788c40ae38fbb1f9b2f5d4e4', role='embedded_worker_implementation_witness'),
    FRAGMENT_H: dict(size=2098, sha256='9f3887613605b06fad70f45bd69f92cd7015de7775a859082bbedb991a2dc1a2', blob='70aa0ef127e2b4c8f242f5868d6efda2fdd13c6f', role='embedded_worker_declaration_witness'),
    HISTORICAL_RECIPE: dict(size=8005, sha256='722d9acb293caa2a1447a61656f954e82f9a54be63f4628362ad7d1e9180274b', blob='2ac669aba5f269d5e9b5c49fdfb43a2aaf3b3fde', role='historical_recipe_read_only_not_executed'),
    INTEGRATION_WITNESS: dict(size=6579, sha256='641fea8eb59177617cd1e54dd60bab45a59dec1c97205a6815bc74b859d7a12b', blob='2ecf30dbfba159795fee0a2951cf1dc2c3f9d30f', role='historical_and_final_patch_identity_record'),
}
SECTIONS = {
    NATIVE_C: dict(size=17013, sha256='25f4bae7984a11a355b06aefd2ba7ac37f424ca0b4390d89d95942f715c2091a', hunks=25),
    NATIVE_H: dict(size=2431, sha256='cd3bf675e1335dfe671d832178ce6a9828d198d7b4abc80387378f86ed489477', hunks=2),
}
OUTPUTS = {
    'linux_kthread.c': dict(size=19566, sha256='31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274', blob='c8f72ebd33119c9a4e47cc58b3397074c0523887'),
    'include/linux/kthread.h': dict(size=4700, sha256='97c094ab5fbc3688334875500c23d5053186d35e6342d2668ce63659335b8814', blob='87bfe919c26654f034351f97acffc88d138cd861'),
}
OPERATION_AUDIT_SHA256 = '3b7fd8d098fc40b9d4401f18121d461fb7821e0477587aba0843413bb73454ed'
OPEN_GATES = ['separate exact provider input contract', 'actual native preprocessing and compilation',
              'Task/Wait/Worker ownership and link closure', 'worker stop/park/drain/lifetime behavior',
              'full kernel and physical hardware acceptance']


def require(value, message):
    if not value:
        raise ValueError('native Worker recovery: ' + message)


def identity(raw):
    return dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())


def regular_bytes(path):
    path = Path(path)
    require(not path.is_symlink() and path.resolve(strict=True) == path, 'aliased input: ' + str(path))
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), 'regular input required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read()
        after = os.fstat(fd)
        same = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(same(before) == same(after), 'input changed during read')
        return raw
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def bind_inputs(repository):
    repository = Path(repository).resolve(strict=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
                       GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    payloads, bindings = {}, {}
    for name, expected in INPUTS.items():
        path = repository / name
        raw = regular_bytes(path)
        observed = identity(raw)
        require(all(observed[key] == expected[key] for key in observed), 'working bytes differ: ' + name)
        tree = subprocess.check_output(['git', '--no-replace-objects', '-C', str(repository), 'ls-tree',
            '--full-tree', INPUT_COMMIT, '--', name], env=environment, timeout=30).decode().rstrip('\n')
        require(tree == '100644 blob ' + expected['blob'] + '\t' + name, 'committed mode/path/blob differs: ' + name)
        payloads[name] = raw
        bindings[name] = dict(expected)
    return payloads, bindings


def extract_sections(raw):
    require(identity(raw)['sha256'] == INPUTS[PATCH]['sha256'] and len(raw) == INPUTS[PATCH]['size'],
            'whole patch identity differs')
    lines = raw.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith(b'--- a/')]
    require(len(starts) == 14, 'exact fourteen patch owner sections required')
    owners, result = [], {}
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(lines)
        require(lines[start].endswith(b'\n') and start + 1 < end, 'patch owner header incomplete')
        owner = lines[start][6:-1].decode()
        require(owner not in owners and not owner.startswith('/') and '..' not in PurePosixPath(owner).parts and
                PurePosixPath(owner).as_posix() == owner and '\\' not in owner and
                re.fullmatch(r'[A-Za-z0-9_./+-]+', owner) is not None,
                'duplicate or noncanonical patch owner')
        require(lines[start + 1] == b'+++ b/' + owner.encode() + b'\n', 'cross-owner patch headers differ')
        owners.append(owner)
        if owner in SECTIONS:
            section = b''.join(lines[start:end])
            expected = SECTIONS[owner]
            require(len(section) == expected['size'] and identity(section)['sha256'] == expected['sha256'],
                    'selected patch section identity differs: ' + owner)
            result[owner] = section
    require(set(result) == set(SECTIONS), 'both exact Worker owner sections required')
    return result


def apply_selected(raw, section):
    lines, source = section.splitlines(keepends=True), raw.splitlines(keepends=True)
    require(len(lines) >= 3 and lines[0].startswith(b'--- a/') and lines[1].startswith(b'+++ b/'),
            'selected section headers required')
    owner = lines[0][6:-1].decode()
    require(owner in SECTIONS and lines[1] == b'+++ b/' + owner.encode() + b'\n', 'selected owner differs')
    output, audit, position, index = [], [], 0, 2
    while index < len(lines):
        header = lines[index]
        match = re.fullmatch(rb'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', header)
        require(match is not None, 'unsupported selected hunk header')
        old_start, old_count = int(match[1]), int(match[2] or b'1')
        new_start, new_count = int(match[3]), int(match[4] or b'1')
        require(old_start >= 1 and new_start >= 1 and position <= old_start - 1 <= len(source),
                'overlapping or out-of-range selected hunk')
        previous, replacement, hunk = [], [], [header]
        index += 1
        while index < len(lines) and not lines[index].startswith(b'@@ '):
            line = lines[index]
            require(line[:1] in (b' ', b'-', b'+') and line.endswith(b'\n'),
                    'unsupported selected hunk payload or missing newline')
            if line[:1] in (b' ', b'-'): previous.append(line[1:])
            if line[:1] in (b' ', b'+'): replacement.append(line[1:])
            hunk.append(line); index += 1
        require(len(previous) == old_count and len(replacement) == new_count, 'selected hunk line counts differ')
        output.extend(source[position:old_start - 1])
        require(len(output) == new_start - 1, 'selected new hunk position differs')
        require(source[old_start - 1:old_start - 1 + old_count] == previous, 'selected old context differs')
        output.extend(replacement); position = old_start - 1 + old_count
        audit.append(dict(owner=owner, old_start=old_start, old_count=old_count, new_start=new_start,
            new_count=new_count, hunk_sha256=identity(b''.join(hunk))['sha256'],
            old_sha256=identity(b''.join(previous))['sha256'], new_sha256=identity(b''.join(replacement))['sha256']))
    output.extend(source[position:])
    require(len(audit) == SECTIONS[owner]['hunks'], 'exact selected hunk count differs')
    return b''.join(output), audit


def make_provenance(bindings, audit):
    bindings = {name: dict(row) for name, row in bindings.items()}
    return dict(schema=1, state='RECOVERED_SOURCE_ONLY_NOT_INSTALLED', netbsd_pin=NETBSD_PIN,
        repository_input_commit=INPUT_COMMIT, repository_inputs=bindings,
        source_mode='PINNED_NETBSD_BLOBS_PLUS_EXACT_TWO_REVIEWED_PATCH_SECTIONS',
        selected_sections={name: dict(row) for name, row in SECTIONS.items()},
        patch_owner_sections=14, applied_owner_sections=2, unexecuted_owner_sections=12,
        files={name: dict(row) for name, row in OUTPUTS.items()}, operations=audit,
        recovery_tool_sha256=identity(regular_bytes(Path(__file__).resolve()))['sha256'],
        historical_recipe=dict(path=HISTORICAL_RECIPE, executed=False,
            limitation='Its fini replacement discards the task-system return; the final selected patch retains the checked return.'),
        historical_integration=dict(path=INTEGRATION_WITNESS,
            interpretation='Historical candidate claims remain historical; the final selected patch output matches the later final identity record. No historical generator, compile or link is reproduced.'),
        definition_ownership=dict(private_kthread_structure=dict(file='linux_kthread.c', line=55),
            private_static_spawn=dict(file='linux_kthread.c', line=183),
            linux_kthread_wake_locked=dict(file='linux_kthread.c', line=415,
                                          declaration='include/linux/kthread.h:132'),
            task_system_fini_checked=dict(file='linux_kthread.c', call_line=86, assertion_line=87)),
        open_gates=list(OPEN_GATES), whole_patch_applied=False, historical_recipe_executed=False,
        native_preprocessing='NOT_RUN', native_compilation='NOT_RUN', linked=False,
        installed=False, booted=False, runtime='NOT_RUN')


def recover(repository=None):
    repository = REPOSITORY if repository is None else repository
    payloads, bindings = bind_inputs(repository)
    sections = extract_sections(payloads[PATCH])
    outputs, audit = {}, []
    for source, owner, output in ((BASE_C, NATIVE_C, 'linux_kthread.c'),
                                  (BASE_H, NATIVE_H, 'include/linux/kthread.h')):
        result, operations = apply_selected(payloads[source], sections[owner])
        require(identity(result) == OUTPUTS[output], 'recovered output identity differs: ' + output)
        outputs[output] = result; audit.extend(operations)
    require(outputs['linux_kthread.c'].endswith(payloads[FRAGMENT_C]), 'complete original Worker implementation witness differs')
    require(outputs['include/linux/kthread.h'].count(payloads[FRAGMENT_H]) == 1,
            'complete Worker declaration witness differs')
    require(all(row['sha256'].encode() in payloads[INTEGRATION_WITNESS] for row in OUTPUTS.values()),
            'final integration output identity record differs')
    checked_fini = b'void\nlinux_kthread_fini(void)\n{\n\tint error;\n\n\terror = linux_task_system_fini();\n\tKASSERT(error == 0);\n}\n'
    require(outputs['linux_kthread.c'].count(checked_fini) == 1, 'final checked Task fini result must be retained')
    proof = make_provenance(bindings, audit)
    outputs['provenance.json'] = (json.dumps(proof, indent=2, sort_keys=True) + '\n').encode()
    return dict(files=outputs, provenance=proof, inputs=bindings, audit=audit)


def validate_publication(files):
    require(isinstance(files, dict) and set(files) == set(OUTPUTS) | {'provenance.json'}, 'exact three output files required')
    for name, expected in OUTPUTS.items():
        require(isinstance(files[name], bytes) and identity(files[name]) == expected, 'publication output identity differs')
    require(isinstance(files['provenance.json'], bytes), 'provenance bytes required')
    proof = json.loads(files['provenance.json'], object_pairs_hook=unique_object)
    audit = proof.get('operations') if isinstance(proof, dict) else None
    require(isinstance(audit, list) and len(audit) == 27 and
            hashlib.sha256(json.dumps(audit, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            == OPERATION_AUDIT_SHA256, 'publication operation audit differs')
    expected = make_provenance(INPUTS, audit)
    # Canonical JSON comparison also distinguishes bool from int and catches
    # every unknown field, unlike ordinary Python dictionary equality.
    require(json.dumps(proof, sort_keys=True, separators=(',', ':')) ==
            json.dumps(expected, sort_keys=True, separators=(',', ':')),
            'publication provenance scope/identity differs')
    return proof


def publish_fresh(output, files):
    validate_publication(files)
    output = Path(output)
    require(output.parent.resolve(strict=True) == output.parent and not os.path.lexists(output),
            'preserve existing or aliased output')
    output.mkdir(mode=0o700, exist_ok=False)
    # The provenance is last, so an incomplete retained directory never carries
    # a successfully published proof. Existing paths are never overwritten.
    for name in ('linux_kthread.c', 'include/linux/kthread.h', 'provenance.json'):
        path = output / name
        if name == 'include/linux/kthread.h':
            (output / 'include').mkdir(); (output / 'include/linux').mkdir()
        with path.open('xb') as stream:
            stream.write(files[name]); stream.flush(); os.fsync(stream.fileno())
        require(regular_bytes(path) == files[name], 'publication byte readback differs')
    return dict(state='RECOVERED_SOURCE_ONLY_NOT_INSTALLED', output=str(output),
                files={name: identity(raw) for name, raw in files.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='create only the fixed fresh source-owned output')
    args = parser.parse_args()
    recovered = recover()
    validate_publication(recovered['files'])
    if args.write:
        result = publish_fresh(REPOSITORY / OUTPUT_ROOT, recovered['files'])
        require(recover()['files'] == recovered['files'], 'source evidence changed during publication')
    else:
        result = dict(state='VERIFIED_DERIVATION_ONLY_NO_WRITE', files={name: identity(raw)
                      for name, raw in recovered['files'].items()}, operations=len(recovered['audit']))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
