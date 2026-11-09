#!/usr/bin/env python3
"""HP-only real native ABI check of ordered hash-bound patches, without install."""
import argparse
import datetime
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import socket
import subprocess

from native_hp_build import (configured_compiler, create_private_output,
                             private_output, require_hp_owner, toolchain_paths)

from native_source_archive import (ArchiveSource, archive_expectations, bind_dependencies,
                                   dependency_paths, recheck_dependencies,
                                   private_git_environment, snapshot_prior_artifacts,
                                   recheck_prior_artifacts)

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
    p.add_argument('--toolchain', type=Path, required=True)
    p.add_argument('--source-archive', type=Path,
                   help='explicit fixed-pin archive proof for used source subset; not clean Git')
    a = p.parse_args()
    try:
        require_hp_owner()
        tools = toolchain_paths(a.toolchain)
    except (ValueError, OSError) as error:
        p.error(str(error))
    source, obj = [x.resolve(strict=True) for x in (a.source, a.kernel_obj)]
    patches = [x.resolve(strict=True) for x in a.patch]
    contracts = [x.resolve(strict=True) for x in a.contract]
    protected = (source, obj, *patches, *contracts,
                 tools['root'], Path(__file__).resolve().parents[1])
    if a.source_archive is not None:
        protected += (a.source_archive.resolve(strict=True),)
    try:
        output = private_output(a.output, protected)
    except (ValueError, OSError) as error:
        p.error(str(error))
    try:
        chain, initial, final, units = patch_chain(patches, contracts)
    except (ValueError, KeyError) as error:
        p.error(str(error))
    if a.source_archive is None:
        if checked(['git', '-C', source, 'rev-parse', 'HEAD']) != PIN:
            p.error('wrong native source pin')
        if checked(['git', '-C', source, 'status', '--porcelain']):
            p.error('native reference dirty')
    for rel, before in initial.items():
        if digest(source / rel) != before:
            p.error('changed native patch input: ' + rel)

    state = dict(state='RUNNING', stage='PREPARING_NATIVE_ABI', pid=os.getpid(),
                 host=socket.gethostname(),
                 started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 netbsd_pin=PIN, patch_chain=chain, toolchain=str(tools['root']),
                 native_tool_sha256={str(tools[k]): digest(tools[k])
                                     for k in ('make', 'compiler')},
                 configured_makefile_sha256=digest(obj / 'Makefile'),
                 prior_kernel_sha256=digest(obj / 'netbsd'),
                 prior_artifacts=snapshot_prior_artifacts(
                     obj, [PurePosixPath(rel).stem for rel in units]),
                 source_provenance=dict(mode=('ARCHIVE_USED_SUBSET' if a.source_archive
                                               else 'GIT_CLEAN_PIN'),
                                        full_tree_clean_git=('NOT_CLAIMED' if a.source_archive
                                                             else 'VERIFIED_AT_START')),
                 commands=[], objects={}, scope='actual native changed C units only',
                 full_kernel='NOT_RUN', runtime='NOT_RUN', installed=False, booted=False)
    create_private_output(output)
    status = output / 'status.json'

    def save():
        temporary = output / 'status.tmp'
        temporary.write_text(json.dumps(state, indent=2) + '\n', encoding='utf8')
        temporary.replace(status)

    def stage(name):
        state['stage'] = name
        save()
        print(name, 'pid=' + str(os.getpid()), flush=True)

    def run(argv, cwd):
        row = dict(command=[str(v) for v in argv], cwd=str(cwd))
        environment = (private_git_environment(output)
                       if row['command'][0] == 'git' else dict(os.environ))
        result = subprocess.run(row['command'], cwd=cwd, env=environment,
                                capture_output=True, text=True)
        row.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        log = output / ('command-' + str(len(state['commands'])).zfill(3) + '.log')
        log.write_text(result.stdout + result.stderr, encoding='utf8')
        row['log'] = str(log)
        state['commands'].append(row)
        save()
        if result.returncode:
            raise RuntimeError('native command failed: ' + ' '.join(row['command']))

    save()
    try:
        stage('QUERYING_NATIVE_CONFIGURATION')
        values = {key: checked([tools['make'], '-C', obj, '-v', key])
                  for key in ('CC', 'CFLAGS', 'CPPFLAGS', 'S')}
        cc = configured_compiler(values['CC'], tools)
        configured = Path(values['S']).resolve(strict=True).parent
        flags = shlex.split(values['CFLAGS']) + [
            value.replace(str(configured) + '/', str(source) + '/')
            for value in shlex.split(values['CPPFLAGS'])]
        if not {'-Werror', '-D_KERNEL', '-nostdinc'}.issubset(flags):
            raise ValueError('kernel flags missing')
        state['flags'] = values
        stage('PREPARING_PATCHED_SOURCE')
        overlay = output / 'source'
        overlay.mkdir()
        for rel in final:
            target = overlay / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / rel).read_bytes())
        for step in chain:
            for rel, row in step['files'].items():
                if digest(overlay / rel) != row['before_sha256']:
                    raise RuntimeError('native patch step input drift: ' + rel)
            run(['git', 'apply', '--check', step['patch']], overlay)
            run(['git', 'apply', step['patch']], overlay)
            for rel, row in step['files'].items():
                if digest(overlay / rel) != row['after_sha256']:
                    raise RuntimeError('patched native source hash mismatch: ' + rel)
        state['patched_inputs'] = {rel: digest(overlay / rel) for rel in final}
        with ExitStack() as context:
            archive = None
            dependencies = {}
            all_bindings = {}
            if a.source_archive is not None:
                stage('VERIFYING_ARCHIVE')
                archive = context.enter_context(ArchiveSource(a.source_archive))
                state['source_provenance'] = archive.receipt()
                stage('SCANNING_NATIVE_DEPENDENCIES')
                for rel in units:
                    unit = PurePosixPath(rel).stem
                    dep = output / (unit + '.pre.d')
                    run(cc + ['-I' + str(overlay / 'sys')] + flags +
                        ['-M', '-MF', str(dep), '-MT', unit + '.o',
                         str(overlay / rel)], obj)
                    bindings = bind_dependencies(dependency_paths(dep, obj), source,
                                                 overlay, obj, state['patched_inputs'])
                    for path, record in bindings.items():
                        if path in all_bindings and all_bindings[path] != record:
                            raise ValueError('dependency changed between owner scans: ' + path)
                        all_bindings[path] = record
                    dependencies[unit] = bindings
                stage('VERIFYING_DEPENDENCIES')
                archive.verify_source_members(archive_expectations(initial, all_bindings))
                state['source_provenance'] = archive.receipt()
                state['precompile_dependencies'] = dependencies
                state['generated_configuration_sha256'] = {
                    path: row['sha256'] for path, row in all_bindings.items()
                    if row['kind'] == 'generated_configuration'}
                save()
                recheck_dependencies(set(map(Path, all_bindings)), all_bindings, source,
                                     overlay, obj, state['patched_inputs'])

            consumed_patched_headers = set()
            for rel in units:
                unit = PurePosixPath(rel).stem
                artifact, dep = output / (unit + '.o'), output / (unit + '.d')
                stage('COMPILING_' + unit.upper())
                run(cc + ['-I' + str(overlay / 'sys')] + flags +
                    ['-MD', '-MF', str(dep), '-c', str(overlay / rel),
                     '-o', str(artifact)], obj)
                paths = dependency_paths(dep, obj)
                headers = sorted(path for path in paths if path.suffix == '.h')
                if archive is not None:
                    state['objects'].setdefault(unit, {})['dependency_proof'] = (
                        recheck_dependencies(paths, dependencies[unit], source, overlay,
                                             obj, state['patched_inputs']))
                for header in [name for name in final if name.endswith('.h')]:
                    if (source / header).resolve() in headers:
                        raise RuntimeError('original version of patched header consumed: ' + header)
                    if (overlay / header).resolve() in headers:
                        consumed_patched_headers.add(header)
                state['objects'].setdefault(unit, {}).update(
                    bytes=artifact.stat().st_size, sha256=digest(artifact),
                    headers_sha256={str(value): digest(value) for value in headers})
                save()
            missing_headers = {name for name in final if name.endswith('.h')} - consumed_patched_headers
            if missing_headers:
                raise RuntimeError('patched headers not consumed by any C owner: ' +
                                   str(sorted(missing_headers)))
            state['consumed_patched_headers'] = sorted(consumed_patched_headers)
            stage('VERIFYING_NATIVE_INPUTS_AND_ARTIFACTS')
            if archive is not None:
                archive.check_identity()
                recheck_dependencies(set(map(Path, all_bindings)), all_bindings, source,
                                     overlay, obj, state['patched_inputs'])
            recheck_prior_artifacts(obj, state['prior_artifacts'])
            if (any(digest(v['patch']) != v['patch_sha256'] or
                    digest(v['contract']) != v['contract_sha256'] for v in chain)
                    or any(digest(source / rel) != before for rel, before in initial.items())
                    or digest(obj / 'Makefile') != state['configured_makefile_sha256']
                    or digest(obj / 'netbsd') != state['prior_kernel_sha256']
                    or any(digest(path) != expected for path, expected
                           in state['native_tool_sha256'].items())):
                raise RuntimeError('input/config/prior artifacts/kernel changed')
            state['state'] = 'PASS'
            state['stage'] = 'COMPLETE'
    except BaseException as error:
        state.update(state='FAIL', stage='FAILED', error=str(error))
        raise
    finally:
        state['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print(json.dumps(dict(state=state['state'], status=str(status),
                          objects=list(state['objects']))))


if __name__ == '__main__':
    main()
