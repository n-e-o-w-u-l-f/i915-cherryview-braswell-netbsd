#!/usr/bin/env python3
"""Check the active F30 chain on four real native originals; never compile."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

from build_hp_native_core_patch import patch_chain
from build_hp_native_fileops import DEFAULT_CHAIN, ROOT
from check_f29_native_zero_size_patch import BEFORE, PATCH as F29_PATCH, stage as f29_stage
from native_hp_build import create_private_output, private_output, require_hp_owner

FINAL = {
    'sys/sys/file.h': 'efa6a2d1d13681f45e032dced3bf3cc21a5282d035a510fd339b59160a6c2521',
    'sys/sys/filedesc.h': '72cda1ee9dd9fd4efb26d8cd3f8861e6e1179c828b80ae3d2481d9f88e7f3549',
    'sys/kern/sys_generic.c': '36d9743f193d7a7e40e0bbf0c2a84ee4183cadc21363d8261a54e60af443e977',
    'sys/kern/kern_descrip.c': '614e5ca25265322a2462ca2da81d67ee5e416f737a05d2b12c2ab4410569ab37',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(source, output):
    require_hp_owner()
    source = Path(source).resolve(strict=True)
    patches, contracts = [list(items) for items in zip(*DEFAULT_CHAIN)]
    chain, initial, final, units = patch_chain(patches, contracts)
    if initial != BEFORE or final != FINAL or set(units) != {
            'sys/kern/sys_generic.c', 'sys/kern/kern_descrip.c'}:
        raise ValueError('active F30 ownership or final identity differs')
    if {rel: digest(source / rel) for rel in BEFORE} != BEFORE:
        raise ValueError('actual complete native originals differ')
    contract = json.loads(contracts[-1].read_text())
    reference = contract['standalone_f29']
    if (ROOT / reference['path'] != F29_PATCH
            or digest(F29_PATCH) != reference['patch_sha256']
            or reference['sys_generic_sha256'] != FINAL['sys/kern/sys_generic.c']):
        raise ValueError('standalone F29 reference differs')
    inputs = {str(path): digest(path) for path in (*patches, *contracts, F29_PATCH)}
    output = private_output(output, (source, ROOT))
    create_private_output(output)
    tree = output / 'source'
    tree.mkdir(mode=0o700)
    for rel in BEFORE:
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((source / rel).read_bytes())
    env = os.environ.copy()
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(key, None)
    env['GIT_CEILING_DIRECTORIES'] = str(output)
    report = dict(state='RUNNING', started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        project='HP-I915', step='F30', source=str(source), tree=str(tree),
        chain=chain, initial=initial, final=final, native_c_owners=units,
        commands=[], negative_controls=[], input_sha256=inputs,
        parent_git_discovery='ceiling and cleared Git directory/index variables',
        native_object_compilation='NOT_RUN', full_kernel='NOT_RUN', hardware='NOT_RUN')
    receipt = output / 'status.json'

    def save():
        temporary = output / 'status.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(receipt)

    def reject(name, operation, fragment):
        try:
            operation()
        except ValueError as error:
            if fragment not in str(error):
                raise RuntimeError(name + ': unexpected refusal: ' + str(error)) from error
            report['negative_controls'].append(dict(name=name, result='PASS', error=str(error)))
            save()
        else:
            raise RuntimeError('negative control accepted: ' + name)

    def apply(patch, *, dry=False, success=True, name=None):
        command = ['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error']
        if dry:
            command.append('--check')
        command.append(str(patch))
        result = subprocess.run(command, cwd=tree, env=env, capture_output=True,
                                text=True, timeout=30)
        report['commands'].append(dict(command=command, exit_code=result.returncode,
                                      stdout=result.stdout, stderr=result.stderr,
                                      expected_success=success))
        save()
        if (result.returncode == 0) != success:
            raise RuntimeError('actual source-chain git acceptance differs: ' + str(command))
        if name:
            report['negative_controls'].append(dict(name=name, result='PASS',
                                                    exit_code=result.returncode))
            save()

    save()
    try:
        reject('wrong_order', lambda: patch_chain(patches[::-1], contracts[::-1]), 'predecessor')
        reject('double_chain', lambda: patch_chain(patches + patches, contracts + contracts), 'duplicate')
        drift_patch = output / 'drift.patch'
        drift_patch.write_bytes(patches[-1].read_bytes() + b'\n# source identity drift\n')
        reject('patch_drift', lambda: patch_chain(patches[:-1] + [drift_patch], contracts), 'identity')
        drift = json.loads(contracts[-1].read_text())
        drift['files']['sys/kern/sys_generic.c']['before_sha256'] = '0' * 64
        drift_contract = output / 'drift.json'
        drift_contract.write_text(json.dumps(drift))
        reject('source_contract_drift', lambda: patch_chain(patches, contracts[:-1] + [drift_contract]),
               'noncomposing')
        preserved = None
        for index, step in enumerate(chain):
            for rel, row in step['files'].items():
                if digest(tree / rel) != row['before_sha256']:
                    raise ValueError('before-image drift: ' + rel)
            if index == 2:
                raw = patches[-1].read_bytes()
                anchor = b' \tproc_t\t\t*p;\n'
                if raw.count(anchor) != 1:
                    raise ValueError('corrupt-context anchor changed')
                corrupt = output / 'corrupt-context.patch'
                corrupt.write_bytes(raw.replace(anchor, b' \tproc_t\t\t*f30_corrupt_context;\n'))
                apply(corrupt, dry=True, success=False, name='corrupt_actual_context')
            apply(Path(step['patch']), dry=True)
            apply(Path(step['patch']))
            for rel, row in step['files'].items():
                if digest(tree / rel) != row['after_sha256']:
                    raise ValueError('after-image drift: ' + rel)
            if index == 1:
                preserved = {rel: (tree / rel).read_bytes() for rel in BEFORE
                             if rel != 'sys/kern/sys_generic.c'}
        apply(patches[-1], dry=True, success=False, name='double_apply_actual_delta')
        actual = {rel: digest(tree / rel) for rel in BEFORE}
        if actual != FINAL or any((tree / rel).read_bytes() != data for rel, data in preserved.items()):
            raise ValueError('recovered header/descriptor owners changed')
        _, standalone_tree, standalone = f29_stage(source, output / 'standalone-f29')
        if ((tree / 'sys/kern/sys_generic.c').read_bytes()
                != (standalone_tree / 'sys/kern/sys_generic.c').read_bytes()):
            raise ValueError('active F30 syscall differs from standalone F29')
        if {rel: digest(source / rel) for rel in BEFORE} != BEFORE:
            raise ValueError('protected native originals changed')
        if {path: digest(path) for path in inputs} != inputs:
            raise ValueError('patch/contract input changed')
        report.update(state='PASS', final_sha256=actual, recovered_other_three_unchanged=True,
                      standalone_f29_syscall_byte_equal=True, standalone_receipt=standalone,
                      originals_unchanged=True, negative_count=len(report['negative_controls']))
    except BaseException as error:
        report.update(state='FAIL', error=str(error))
        raise
    finally:
        report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    return report, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report, receipt = check(args.source, args.output)
    print(json.dumps(dict(state=report['state'], negative_controls=report['negative_count'],
                          native_c_owners=report['native_c_owners'], receipt=str(receipt))))


if __name__ == '__main__':
    main()
