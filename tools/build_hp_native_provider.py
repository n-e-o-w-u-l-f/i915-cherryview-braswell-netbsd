#!/usr/bin/env python3
"""Compile real provider C against a completed native patch-chain ABI snapshot."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import socket
import subprocess

from native_hp_build import (configured_compiler, core_toolchain_receipt, create_private_output,
                             private_output, require_hp_owner, toolchain_paths)

PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'kernel-obj', 'core-status', 'provider-root', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--unit', action='append', required=True)
    parser.add_argument('--include-root', action='append', type=Path, default=[])
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--provider-contract', type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if (args.source_archive is None) != (args.provider_contract is None):
        parser.error('--source-archive and --provider-contract must be selected together')
    if args.preflight_only and args.source_archive is None:
        parser.error('--preflight-only requires the explicit reviewed archive mode')
    try:
        require_hp_owner()
        tools = toolchain_paths(args.toolchain)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.source_archive is not None:
        return archive_provider(args, parser, tools)
    source, obj, core_path, provider = [v.resolve(strict=True) for v in
                                       (args.source, args.kernel_obj, args.core_status, args.provider_root)]
    includes = [v.resolve(strict=True) for v in args.include_root]
    if (provider/'include').is_dir():
        includes.insert(0, provider/'include')
    try:
        output = private_output(args.output, (source, obj, core_path.parent, provider,
                                *includes, tools['root'], Path(__file__).resolve().parents[1]))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    core = json.loads(core_path.read_text(encoding='utf8'))
    if core.get('state') != 'PASS' or core.get('netbsd_pin') != PIN:
        parser.error('actual successful native core receipt required')
    try:
        core_tools = core_toolchain_receipt(core, tools)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    overlay = core_path.parent/'source'
    if any(sha(overlay/rel) != expected for rel, expected in core['patched_inputs'].items()):
        parser.error('native core overlay drift')
    for step in core['patch_chain']:
        if sha(step['patch']) != step['patch_sha256'] or sha(step['contract']) != step['contract_sha256']:
            parser.error('native patch-chain input drift')
    for record in core['objects'].values():
        if any(sha(path) != expected for path, expected in record['headers_sha256'].items()):
            parser.error('native core header drift')
    if (subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() != PIN
            or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
            or sha(obj/'Makefile') != core['configured_makefile_sha256']
            or sha(obj/'netbsd') != core['prior_kernel_sha256']):
        parser.error('native source/configuration/prior kernel drift')
    units = []
    for rel in args.unit:
        path = PurePosixPath(rel)
        if path.is_absolute() or '..' in path.parts or '\\' in rel or path.suffix != '.c':
            parser.error('explicit provider C unit required')
        unit = (provider/rel).resolve(strict=True)
        if not unit.is_relative_to(provider):
            parser.error('provider source escapes root')
        units.append(unit)
    if len({v.stem for v in units}) != len(units):
        parser.error('ambiguous provider object names')
    try:
        cc = configured_compiler(core['flags']['CC'], tools)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    configured = Path(core['flags']['S']).resolve(strict=True).parent
    flags = shlex.split(core['flags']['CFLAGS']) + [v.replace(str(configured)+'/',str(source)+'/')
                                               for v in shlex.split(core['flags']['CPPFLAGS'])]
    if not {'-Werror','-D_KERNEL','-nostdinc'}.issubset(flags):
        parser.error('actual strict native compiler configuration required')
    state = dict(state='RUNNING',started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 pid=os.getpid(),host=socket.gethostname(),netbsd_pin=PIN,
                 core_status=str(core_path),core_status_sha256=sha(core_path),
                 toolchain=str(tools['root']),
                 native_tool_sha256=core_tools,
                 sources_sha256={str(v):sha(v) for v in units},objects={},
                 full_kernel='NOT_RUN',runtime='NOT_RUN',installed=False,booted=False)
    create_private_output(output)
    def save():
        tmp=output/'status.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n',encoding='utf8');tmp.replace(output/'status.json')
    save()
    try:
        failures=[]
        for unit in units:
            artifact=output/(unit.stem+'.o');dep=output/(unit.stem+'.d')
            command=cc+['-I'+str(overlay/'sys')]+['-I'+str(v) for v in includes]+flags+[
                '-MD','-MF',str(dep),'-c',str(unit),'-o',str(artifact)]
            result=subprocess.run(command,cwd=obj,capture_output=True,text=True,timeout=180)
            log=output/(unit.stem+'.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
            row=dict(command=command,exit_code=result.returncode,log_sha256=sha(log))
            if result.returncode:
                failures.append(unit.stem)
            else:
                tokens=shlex.split(dep.read_text(encoding='utf8').replace('\\\n',' ').split(':',1)[1])
                headers=sorted({(Path(v) if Path(v).is_absolute() else obj/v).resolve(strict=True)
                                for v in tokens if v.endswith('.h')})
                for rel in core['patched_inputs']:
                    if rel.endswith('.h') and (source/rel).resolve() in headers:
                        raise RuntimeError('original version of patched native header consumed: '+rel)
                row.update(bytes=artifact.stat().st_size,sha256=sha(artifact),
                           headers_sha256={str(v):sha(v) for v in headers})
            state['objects'][unit.stem]=row;save()
        if (sha(core_path)!=state['core_status_sha256']
                or any(sha(v)!=expected for v,expected in state['sources_sha256'].items())
                or sha(obj/'netbsd')!=core['prior_kernel_sha256']
                or any(sha(path)!=expected for path,expected in state['native_tool_sha256'].items())):
            raise RuntimeError('native inputs or prior kernel changed during compile')
        state.update(state='FAIL' if failures else 'PASS',failures=failures)
    except BaseException as error:
        state.update(state='FAIL',error=str(error));raise
    finally:
        state['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    print(json.dumps(dict(state=state['state'],objects=list(state['objects']),failures=failures,status=str(output/'status.json'))))
    return bool(failures)


def archive_provider(args, parser, tools):
    """Explicit reviewed archive mode; its dependency scan is independent of compilation."""
    from native_provider_inputs import (
        REPOSITORY, load_contract, native_archive_expectations, provider_header_policy,
        provider_dependencies, recheck_provider_dependencies, repository_inputs,
        require_provider_headers, require_task_fragments, require_task_worker_inputs,
        reviewed_contract_sha256, selected_inputs, task_fragment_policy,
        task_worker_input_policy, verify_core, wait_input_policy, require_wait_inputs,
        verify_wait_generation, poll_input_policy, require_poll_inputs, verify_poll_generation)
    from native_source_archive import (
        ArchiveSource, dependency_paths, recheck_prior_artifacts, snapshot_prior_artifacts)
    try:
        contract = load_contract(args.provider_contract)
        source, obj, core_path, provider = [v.resolve(strict=True) for v in
            (args.source, args.kernel_obj, args.core_status, args.provider_root)]
        includes = selected_inputs(contract, REPOSITORY, source, provider, args.unit,
                                   args.include_root)
        inputs = repository_inputs(REPOSITORY, contract)
        core = verify_core(core_path, contract, source, obj, tools)
        contract_digest = reviewed_contract_sha256(args.provider_contract, REPOSITORY)
        required_headers = provider_header_policy(core, contract, contract_digest)
        required_fragments = task_fragment_policy(contract, contract_digest)
        required_worker_inputs = task_worker_input_policy(contract, contract_digest)
        required_poll_inputs = poll_input_policy(contract, contract_digest)
        if required_poll_inputs:
            required_wait_inputs, wait_generation = [], {}
            poll_generation = verify_poll_generation(REPOSITORY, contract, inputs, contract_digest)
        else:
            required_wait_inputs = wait_input_policy(contract, contract_digest)
            wait_generation = verify_wait_generation(REPOSITORY, contract, inputs, contract_digest)
            poll_generation = {}
        overlay = core_path.parent / 'source'
        cc = configured_compiler(core['flags']['CC'], tools)
        configured = Path(core['flags']['S']).resolve(strict=True).parent
        flags = shlex.split(core['flags']['CFLAGS']) + [
            value.replace(str(configured) + '/', str(source) + '/')
            for value in shlex.split(core['flags']['CPPFLAGS'])]
        if not {'-Werror', '-D_KERNEL', '-nostdinc'}.issubset(flags):
            raise ValueError('actual strict native compiler configuration required')
        output = private_output(args.output, (source, obj, core_path.parent, provider,
            *includes, tools['root'], REPOSITORY, args.source_archive.resolve(strict=True)))
        units = [provider / relative for relative in contract['units']]
        prior = snapshot_prior_artifacts(obj, [unit.stem for unit in units])
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    state = dict(state='RUNNING', stage='ADMITTED', started=datetime.datetime.now(
        datetime.timezone.utc).isoformat(), pid=os.getpid(), host=socket.gethostname(),
        netbsd_pin=PIN, core_status=str(core_path),
        core_status_sha256=contract['core_status_sha256'],
        provider_contract=str(args.provider_contract.resolve()),
        provider_contract_sha256=contract_digest, required_patched_headers=required_headers,
        required_task_fragments=required_fragments,
        required_task_worker_inputs=required_worker_inputs,
        required_wait_inputs=required_wait_inputs, wait_generation_proof=wait_generation,
        required_poll_inputs=required_poll_inputs, poll_generation_proof=poll_generation,
        repository_commit=contract['repository_commit'], repository_inputs=inputs,
        toolchain=str(tools['root']), native_tool_sha256=core['native_tool_sha256'],
        flags=core['flags'], include_roots=[str(path) for path in includes],
        prior_artifacts=prior, commands=[], precompile_dependencies={}, objects={},
        full_kernel='NOT_RUN', runtime='NOT_RUN', installed=False, booted=False)
    create_private_output(output)

    def save():
        temporary = output / 'status.tmp'
        temporary.write_text(json.dumps(state, indent=2) + '\n', encoding='utf8')
        temporary.replace(output / 'status.json')

    def stage(name):
        state['stage'] = name
        save()

    def run(command):
        result = subprocess.run(command, cwd=obj, capture_output=True, text=True, timeout=180)
        log = output / ('command-' + str(len(state['commands'])).zfill(3) + '.log')
        log.write_text(result.stdout + result.stderr, encoding='utf8')
        state['commands'].append(dict(command=command, cwd=str(obj),
            exit_code=result.returncode, log=str(log), log_sha256=sha(log)))
        save()
        if result.returncode:
            raise RuntimeError('native provider command failed: ' + str(log))

    binding_arguments = (REPOSITORY, inputs, source, overlay, obj,
                         core['patched_inputs'], core['declared_generated_configuration'])
    save()
    try:
        with ArchiveSource(args.source_archive) as archive:
            stage('SCANNING_PROVIDER_DEPENDENCIES')
            all_bindings = {}
            for unit in units:
                dep = output / (unit.stem + '.pre.d')
                command = cc + ['-I' + str(overlay / 'sys')] + [
                    '-I' + str(path) for path in includes] + flags
                run(command + ['-M', '-MF', str(dep), '-MT', unit.stem + '.o', str(unit)])
                bindings = provider_dependencies(dependency_paths(dep, obj), *binding_arguments)
                if str(unit) not in bindings:
                    raise ValueError('dependency scan omitted the reviewed provider unit')
                require_provider_headers(bindings, REPOSITORY, core, contract, contract_digest)
                require_task_fragments(bindings, REPOSITORY, contract, contract_digest)
                require_task_worker_inputs(bindings, REPOSITORY, contract, contract_digest)
                if required_poll_inputs:
                    require_poll_inputs(bindings, REPOSITORY, contract, contract_digest)
                else:
                    require_wait_inputs(bindings, REPOSITORY, contract, contract_digest)
                for path, row in bindings.items():
                    if path in all_bindings and all_bindings[path] != row:
                        raise ValueError('provider dependency changed between scans')
                    all_bindings[path] = row
                state['precompile_dependencies'][unit.stem] = bindings
            stage('VERIFYING_PROVIDER_DEPENDENCIES')
            archive.verify_source_members(native_archive_expectations(core, all_bindings))
            state['source_provenance'] = archive.receipt()
            recheck_provider_dependencies(set(map(Path, all_bindings)), all_bindings,
                                          *binding_arguments)
            save()
            if not args.preflight_only:
                for unit in units:
                    stage('COMPILING_' + unit.stem.upper())
                    artifact, dep = output / (unit.stem + '.o'), output / (unit.stem + '.d')
                    command = cc + ['-I' + str(overlay / 'sys')] + [
                        '-I' + str(path) for path in includes] + flags
                    run(command + ['-MD', '-MF', str(dep), '-c', str(unit),
                                   '-o', str(artifact)])
                    proof = recheck_provider_dependencies(dependency_paths(dep, obj),
                        state['precompile_dependencies'][unit.stem], *binding_arguments)
                    require_task_fragments(proof, REPOSITORY, contract, contract_digest)
                    require_task_worker_inputs(proof, REPOSITORY, contract, contract_digest)
                    if required_poll_inputs:
                        require_poll_inputs(proof, REPOSITORY, contract, contract_digest)
                    else:
                        require_wait_inputs(proof, REPOSITORY, contract, contract_digest)
                    state['objects'][unit.stem] = dict(bytes=artifact.stat().st_size,
                        sha256=sha(artifact), dependency_proof=proof)
                    save()
            archive.check_identity()
            recheck_provider_dependencies(set(map(Path, all_bindings)), all_bindings,
                                          *binding_arguments)
        state.update(state='PREFLIGHT_PASS' if args.preflight_only else 'PASS',
                     stage='ADMITTED_NO_OBJECTS' if args.preflight_only else 'COMPLETE',
                     object_compilation='NOT_RUN' if args.preflight_only else 'COMPLETE')
    except BaseException as error:
        state.update(state='FAIL', stage='FAILED', error=str(error))
        raise
    finally:
        try:
            load_contract(args.provider_contract)
            if repository_inputs(REPOSITORY, contract) != inputs:
                raise ValueError('reviewed provider identity changed')
            if required_poll_inputs:
                if verify_poll_generation(REPOSITORY, contract, inputs, contract_digest) != poll_generation:
                    raise ValueError('Poll generation proof changed')
            elif verify_wait_generation(REPOSITORY, contract, inputs, contract_digest) != wait_generation:
                raise ValueError('Wait generation proof changed')
            verify_core(core_path, contract, source, obj, tools, core=core)
            recheck_prior_artifacts(obj, prior)
        except BaseException as error:
            state.update(state='FAIL', stage='FAILED', integrity_error=str(error))
        state['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    if state['state'] == 'FAIL':
        raise RuntimeError(state.get('integrity_error', 'provider admission failed'))
    print(json.dumps(dict(state=state['state'], objects=list(state['objects']),
                          status=str(output / 'status.json'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
