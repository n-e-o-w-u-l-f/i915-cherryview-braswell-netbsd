#!/usr/bin/env python3
"""Apply the explicit four-step F32 source chain; no native compiler or boot."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

from build_hp_native_core_patch import patch_chain
from build_hp_native_fileops import DEFAULT_CHAIN, NETBSD32_GUARD, ROOT
from check_f30_native_ioctl_chain import BEFORE as F30_BEFORE, FINAL as F30_FINAL
from native_hp_build import create_private_output, private_output, require_hp_owner

RELATIVE = 'sys/compat/netbsd32/netbsd32_ioctl.c'
BEFORE = '846c5602be6de8550aae1ea03e66e3e46a5107db20708987ece89b41a5184e46'
AFTER = 'd0385949c415c1810dbdcbb91197bd0766c6bbef6bd3ff232be3f40128f72c6d'
PATCH_SHA256 = 'b1953c0a3c94fbccc079fcfeaacbb1fb4b32c8ac89c4e0dc389fccad5eb8a6d5'
GENERATED_CONFIGURATION = {'lockstat.h': '844d3989147b86eaa7fb6315a3e70934fecd634b5ad8225b71fb81188e7a25cd'}
GUARD = """\t/* Modern Linux DRM has no verified Compat32 translation here.
\t * Reject opted-in DRM before legacy marshalling or user access. */
\tif (fp->f_ops != NULL && fp->f_ops->fo_ioctl_user != NULL &&
\t    IOCGROUP(com) == 'd') {
\t\terror = ENOTTY;
\t\tgoto out;
\t}

"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stage(source, output):
    require_hp_owner()
    source = Path(source).resolve(strict=True)
    selected = DEFAULT_CHAIN + (NETBSD32_GUARD,)
    patches, contracts = [list(values) for values in zip(*selected)]
    chain, initial, final, units = patch_chain(patches, contracts)
    if (initial != dict(F30_BEFORE, **{RELATIVE: BEFORE})
            or final != dict(F30_FINAL, **{RELATIVE: AFTER})
            or set(units) != {'sys/kern/sys_generic.c', 'sys/kern/kern_descrip.c', RELATIVE}):
        raise ValueError('explicit optional chain has different source owners')
    contract = json.loads(contracts[-1].read_text())
    if (sha(patches[-1].read_bytes()) != PATCH_SHA256
            or contract.get('compat32_translation_implemented') is not False
            or contract.get('generated_configuration') != GENERATED_CONFIGURATION):
        raise ValueError('F32 patch identity or partial policy differs')
    originals = {rel: (source / rel).read_bytes() for rel in initial}
    if {rel: sha(data) for rel, data in originals.items()} != initial:
        raise ValueError('complete original source identity differs')
    output = private_output(output, (source, ROOT))
    create_private_output(output)
    tree = output / 'source'
    tree.mkdir(mode=0o700)
    for rel, data in originals.items():
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    inputs = {str(path): sha(path.read_bytes()) for path in (*patches, *contracts)}
    env = os.environ.copy()
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(key, None)
    env['GIT_CEILING_DIRECTORIES'] = str(output)
    report = dict(state='RUNNING', step='F32', started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  original_sha256=initial, final_sha256=final, chain=chain,
                  native_c_owners=units, commands=[], compat32_translation_implemented=False,
                  native_kernel_headers='NOT_RUN', full_kernel='NOT_RUN', hardware='NOT_RUN')
    receipt = output / 'native-source-receipt.json'

    def save():
        tmp = output / 'native-source-receipt.tmp'
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(receipt)

    def run(command, success=True):
        done = subprocess.run(command, cwd=tree, env=env, capture_output=True, text=True, timeout=30)
        report['commands'].append(dict(command=command, exit_code=done.returncode,
                                      stdout=done.stdout, stderr=done.stderr, expected_success=success))
        save()
        if (done.returncode == 0) != success:
            raise RuntimeError('native source Git acceptance differs')
    save()
    try:
        for index, row in enumerate(chain):
            for rel, identity in row['files'].items():
                if sha((tree / rel).read_bytes()) != identity['before_sha256']:
                    raise ValueError('source chain input drift')
            if index == 3:
                patch = patches[-1].read_bytes()
                anchor = b' \t\tfd_set_exclose(l, fd, com == FIOCLEX);\n'
                if patch.count(anchor) != 1:
                    raise ValueError('corrupt-context control anchor differs')
                corrupt = output / 'corrupt-context.patch'
                corrupt.write_bytes(patch.replace(anchor, b' \t\tfd_set_exclose_f32_corrupt(l, fd, com == FIOCLEX);\n'))
                run(['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error',
                     '--check', str(corrupt)], False)
            for mode in ('--check', None):
                command = ['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error']
                if mode:
                    command.append(mode)
                run(command + [row['patch']])
            for rel, identity in row['files'].items():
                if sha((tree / rel).read_bytes()) != identity['after_sha256']:
                    raise ValueError('source chain post-image drift')
        patched = (tree / RELATIVE).read_text()
        if patched.count(GUARD) != 1 or patched.replace(GUARD, '', 1).encode() != originals[RELATIVE]:
            raise ValueError('non-gate native source bytes changed')
        if {rel: sha((tree / rel).read_bytes()) for rel in final} != final:
            raise ValueError('final native identity differs')
        if {rel: (source / rel).read_bytes() for rel in initial} != originals:
            raise ValueError('protected originals changed')
        if {path: sha(Path(path).read_bytes()) for path in inputs} != inputs:
            raise ValueError('patch or contract changed')
        report.update(state='PASS', original_sources_unchanged=True,
                      native_bytes_outside_gate_unchanged=True, corrupt_context_rejected=True,
                      unchanged_base_default_count=len(DEFAULT_CHAIN))
    except BaseException as error:
        report.update(state='FAIL', error=str(error))
        raise
    finally:
        report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    return output, tree, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output, tree, report = stage(args.source, args.output)
    print(json.dumps(dict(state=report['state'], output=str(output), tree=str(tree))))


if __name__ == '__main__':
    main()
