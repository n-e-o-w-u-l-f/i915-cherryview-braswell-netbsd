#!/usr/bin/env python3
"""HP-only real native ABI check of ordered hash-bound patches, without install."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shlex
import socket
import subprocess

PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(argv, **kwargs):
    return subprocess.check_output([str(v) for v in argv], text=True, **kwargs).strip()


def patch_chain(patches, contracts):
    """Validate composition before creating any output or invoking git apply."""
    if len(patches) != len(contracts) or not patches:
        raise ValueError('one ordered contract per patch required')
    chain, initial, final = [], {}, {}
    seen = set()
    for patch, contract_path in zip(patches, contracts):
        patch_hash = digest(patch)
        contract = json.loads(contract_path.read_text(encoding='utf8'))
        if (contract.get('netbsd_pin') != PIN
                or patch_hash != contract.get('patch_sha256')
                or patch_hash in seen):
            raise ValueError('patch/source identity mismatch or duplicate patch')
        prior = contract.get('prior_patch_sha256',contract.get('prior_entry_patch_sha256'))
        if (contract.get('prior_patch_sha256') is not None and
                contract.get('prior_entry_patch_sha256') is not None and
                contract['prior_patch_sha256'] != contract['prior_entry_patch_sha256']):
            raise ValueError('contradictory patch predecessor identity')
        if prior is not None and (not chain or prior != chain[-1]['patch_sha256']):
            raise ValueError('patch predecessor identity mismatch')
        paths = contract.get('files')
        if not isinstance(paths, dict) or not paths:
            raise ValueError('empty patch source contract')
        for rel, row in paths.items():
            path = PurePosixPath(rel)
            if (not rel.startswith('sys/') or path.is_absolute()
                    or '..' in path.parts or '\\' in rel
                    or path.suffix not in ('.h', '.c')):
                raise ValueError('unqualified native patch input: ' + rel)
            for key in ('before_sha256', 'after_sha256'):
                value = row.get(key)
                if (not isinstance(value, str) or len(value) != 64
                        or any(c not in '0123456789abcdef' for c in value)):
                    raise ValueError('invalid source digest: ' + rel)
            if rel in final and final[rel] != row['before_sha256']:
                raise ValueError('noncomposing native source contract: ' + rel)
            initial.setdefault(rel, row['before_sha256'])
            final[rel] = row['after_sha256']
        chain.append(dict(patch=str(patch), contract=str(contract_path),
                          patch_sha256=patch_hash,
                          contract_sha256=digest(contract_path), files=paths))
        seen.add(patch_hash)
    units = [rel for rel in final if rel.endswith('.c')]
    if not units or len({PurePosixPath(v).stem for v in units}) != len(units):
        raise ValueError('missing or ambiguous native C owners in patch chain')
    return chain, initial, final, units


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'kernel-obj', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('patch', 'contract'):
        p.add_argument('--' + name, type=Path, required=True, action='append')
    a = p.parse_args()
    if (platform.system() != 'NetBSD' or platform.release().split('.')[0] != '11'
            or platform.machine() != 'amd64' or os.geteuid() == 0
            or socket.gethostname().split('.')[0] != 'hp-tpnw121'):
        p.error('HP NetBSD11 amd64 non-root only')
    source, obj = [x.resolve(strict=True) for x in (a.source, a.kernel_obj)]
    patches = [x.resolve(strict=True) for x in a.patch]
    contracts = [x.resolve(strict=True) for x in a.contract]
    output = a.output.parent.resolve(strict=True) / a.output.name
    if (a.output.name in ('', '.', '..') or output.exists() or a.output.is_symlink()
            or any(output.is_relative_to(x) for x in
                   (source, obj, *patches, *contracts, Path(__file__).resolve().parents[1]))):
        p.error('new output outside protected source/config/patch inputs required')
    try:
        chain, initial, final, units = patch_chain(patches, contracts)
    except (ValueError, KeyError) as error:
        p.error(str(error))
    if checked(['git', '-C', source, 'rev-parse', 'HEAD']) != PIN:
        p.error('wrong native source pin')
    if checked(['git', '-C', source, 'status', '--porcelain']):
        p.error('native reference dirty')
    for rel, before in initial.items():
        if digest(source / rel) != before:
            p.error('changed native patch input: ' + rel)
    values = {key: checked(['/usr/tools/bin/nbmake-amd64', '-C', obj, '-v', key])
              for key in ('CC', 'CFLAGS', 'CPPFLAGS', 'S')}
    cc = shlex.split(values['CC'])
    if cc != ['/usr/tools/bin/x86_64--netbsd-gcc']:
        p.error('unexpected native compiler')
    configured = Path(values['S']).resolve(strict=True).parent
    flags = shlex.split(values['CFLAGS']) + [v.replace(str(configured) + '/', str(source) + '/')
                                            for v in shlex.split(values['CPPFLAGS'])]
    if not {'-Werror', '-D_KERNEL', '-nostdinc'}.issubset(flags):
        p.error('kernel flags missing')
    state = dict(state='RUNNING', pid=os.getpid(), host=socket.gethostname(),
                 started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 netbsd_pin=PIN, patch_chain=chain,
                 configured_makefile_sha256=digest(obj/'Makefile'),
                 prior_kernel_sha256=digest(obj/'netbsd'), flags=values,
                 commands=[], objects={}, scope='actual native changed C units only',
                 full_kernel='NOT_RUN', runtime='NOT_RUN', installed=False, booted=False)
    output.mkdir()
    status = output/'status.json'
    def save():
        status.write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
    def run(argv, cwd):
        row = dict(command=[str(v) for v in argv], cwd=str(cwd))
        result = subprocess.run(row['command'], cwd=cwd, capture_output=True, text=True)
        row.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        state['commands'].append(row);save()
        if result.returncode:
            raise RuntimeError('native command failed: ' + ' '.join(row['command']))
    save()
    try:
        overlay = output/'source';overlay.mkdir()
        for rel in final:
            target=overlay/rel;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((source/rel).read_bytes())
        for step in chain:
            for rel, row in step['files'].items():
                if digest(overlay/rel) != row['before_sha256']:
                    raise RuntimeError('native patch step input drift: ' + rel)
            run(['git','apply','--check',step['patch']],overlay)
            run(['git','apply',step['patch']],overlay)
            for rel, row in step['files'].items():
                if digest(overlay/rel) != row['after_sha256']:
                    raise RuntimeError('patched native source hash mismatch: ' + rel)
        state['patched_inputs']={rel:digest(overlay/rel) for rel in final}
        consumed_patched_headers = set()
        for rel in units:
            unit=PurePosixPath(rel).stem;artifact=output/(unit+'.o');dep=output/(unit+'.d')
            run(cc+['-I'+str(overlay/'sys')]+flags+['-MD','-MF',str(dep),'-c',str(overlay/rel),'-o',str(artifact)],obj)
            tokens=shlex.split(dep.read_text(encoding='utf8').replace('\\\n',' ').split(':',1)[1])
            headers=sorted({(Path(v) if Path(v).is_absolute() else obj/v).resolve(strict=True)
                            for v in tokens if v.endswith('.h')})
            for header in [name for name in final if name.endswith('.h')]:
                if (source/header).resolve() in headers:
                    raise RuntimeError('original version of patched header consumed: '+header)
                if (overlay/header).resolve() in headers:
                    consumed_patched_headers.add(header)
            state['objects'][unit]=dict(bytes=artifact.stat().st_size,sha256=digest(artifact),
                headers_sha256={str(v):digest(v) for v in headers})
            save()
        missing_headers = {name for name in final if name.endswith('.h')} - consumed_patched_headers
        if missing_headers:
            raise RuntimeError('patched headers not consumed by any C owner: '+str(sorted(missing_headers)))
        state['consumed_patched_headers'] = sorted(consumed_patched_headers)
        if (any(digest(v['patch']) != v['patch_sha256'] or
                digest(v['contract']) != v['contract_sha256'] for v in chain)
                or any(digest(source/rel) != before for rel, before in initial.items())
                or digest(obj/'Makefile')!=state['configured_makefile_sha256']
                or digest(obj/'netbsd')!=state['prior_kernel_sha256']):
            raise RuntimeError('input/config/prior kernel changed')
        state['state']='PASS'
    except BaseException as error:
        state.update(state='FAIL',error=str(error));raise
    finally:
        state['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    print(json.dumps(dict(state=state['state'],status=str(status),objects=list(state['objects']))))


if __name__=='__main__':
    main()
