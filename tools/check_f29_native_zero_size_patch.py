#!/usr/bin/env python3
"""Apply the standalone F29 candidate to four complete pinned native originals.

Only private source copies change. No compiler, kernel, installation or boot.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

from native_hp_build import create_private_output, private_output, require_hp_owner

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/candidates/netbsd-11-drm-fileops-bridge-zero-size-kernel-data-20261110.patch'
PATCH_SHA256 = '32ee8fa0ba8e301c560e696200a14ca16e9b2396cd317ca294758585a92c035f'
NETBSD_PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
BEFORE = {
    'sys/sys/file.h': 'a6019f187474dddf7eac80eff44ea652fc9d3bb43459d076bbf106c5bac69a4c',
    'sys/sys/filedesc.h': '3ef72d7490544b5cd806abe869e80a03ba0414f9b621b0351b26587ede81a72c',
    'sys/kern/sys_generic.c': '532ff66e2560a93be706032fd5f69e1a1b69d57f165621ea66d3f3e0aea69514',
    'sys/kern/kern_descrip.c': '48006299c61b697c7342f2341cd867066f5ea5851efc174f93ce3aa284df4de1',
}
AFTER = {
    'sys/sys/file.h': 'a1877ef189c59eab925487927932c9ea55681a0e8dfb460b56ebf6fc47f59770',
    'sys/sys/filedesc.h': '0bfa222bfaeaf1c1ac049ff6525a2df4343741e2dd30d91f000460e9fc604519',
    'sys/kern/sys_generic.c': '36d9743f193d7a7e40e0bbf0c2a84ee4183cadc21363d8261a54e60af443e977',
    'sys/kern/kern_descrip.c': '55d4c5b492535d1c281ce7962eccb1f4f6d684b4fd85ef7f1d317cdcbc39472d',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_originals(source):
    source = Path(source).resolve(strict=True)
    data = {rel: (source / rel).read_bytes() for rel in BEFORE}
    if {rel: sha(value) for rel, value in data.items()} != BEFORE:
        raise ValueError('complete pinned native original bytes differ')
    return source, data


def stage(source, output):
    require_hp_owner()
    source, originals = checked_originals(source)
    patch = PATCH.read_bytes()
    if sha(patch) != PATCH_SHA256:
        raise ValueError('F29 standalone patch identity drift')
    old_paths = [line[6:] for line in patch.decode().splitlines() if line.startswith('--- a/')]
    new_paths = [line[6:] for line in patch.decode().splitlines() if line.startswith('+++ b/')]
    if old_paths != list(BEFORE) or new_paths != list(BEFORE):
        raise ValueError('standalone candidate must own exactly four pinned originals')
    output = private_output(output, (source, ROOT))
    create_private_output(output)
    tree = output / 'native-source'
    tree.mkdir(mode=0o700)
    for rel, data in originals.items():
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    env = os.environ.copy()
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(key, None)
    env['GIT_CEILING_DIRECTORIES'] = str(output)
    report = dict(state='RUNNING', netbsd_pin=NETBSD_PIN, source=str(source),
                  source_has_git=(source / '.git').exists(), original_sha256=BEFORE,
                  patch_sha256=sha(patch), private_tree=str(tree),
                  parent_git_discovery='disabled by ceiling and cleared Git directory/index variables',
                  commands=[], full_kernel='NOT_RUN', native_kernel_headers='NOT_RUN')
    receipt = output / 'native-source-receipt.json'

    def save():
        receipt.write_text(json.dumps(report, indent=2) + '\n')

    def run(argv, expected_success=True):
        result = subprocess.run(argv, cwd=tree, env=env, capture_output=True,
                                text=True, timeout=30)
        row = dict(command=argv, exit_code=result.returncode, stdout=result.stdout,
                   stderr=result.stderr, expected_success=expected_success)
        report['commands'].append(row)
        save()
        if (result.returncode == 0) != expected_success:
            raise RuntimeError('native original-byte patch acceptance differs: ' + str(argv))
        return result

    save()
    try:
        corrupt = patch.replace(b' struct uio;\n', b' struct f29_corrupt_original;\n', 1)
        if corrupt == patch:
            raise ValueError('corrupt-context control anchor missing')
        bad_patch = output / 'corrupt-context.patch'
        bad_patch.write_bytes(corrupt)
        run(['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error', '--check', str(bad_patch)], False)
        run(['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error', '--check', str(PATCH)])
        run(['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=error', str(PATCH)])
        actual = {rel: sha((tree / rel).read_bytes()) for rel in BEFORE}
        if actual != AFTER:
            raise ValueError('standalone F29 post-image differs from exact reviewed source')
        if {rel: sha((source / rel).read_bytes()) for rel in BEFORE} != BEFORE:
            raise ValueError('protected original changed')
        if PATCH.read_bytes() != patch:
            raise ValueError('candidate changed while checking')
        report.update(state='PASS', patched_sha256=actual, originals_unchanged=True)
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
