#!/usr/bin/env python3
"""Compile real provider C against a completed native patch-chain ABI snapshot."""
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'kernel-obj', 'core-status', 'provider-root', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--unit', action='append', required=True)
    parser.add_argument('--include-root', action='append', type=Path, default=[])
    args = parser.parse_args()
    if (platform.system() != 'NetBSD' or platform.release().split('.')[0] != '11'
            or platform.machine() != 'amd64' or os.geteuid() != 1004
            or socket.gethostname().split('.')[0] != 'hp-tpnw121'):
        parser.error('HP NetBSD11 amd64 owner only')
    source, obj, core_path, provider = [v.resolve(strict=True) for v in
                                       (args.source, args.kernel_obj, args.core_status, args.provider_root)]
    includes = [v.resolve(strict=True) for v in args.include_root]
    if (provider/'include').is_dir():
        includes.insert(0, provider/'include')
    output = args.output.parent.resolve(strict=True)/args.output.name
    if (args.output.name in ('', '.', '..') or args.output.is_symlink() or output.exists()
            or any(output.is_relative_to(v) for v in (source, obj, core_path.parent, provider, *includes))):
        parser.error('fresh private output outside inputs required')
    core = json.loads(core_path.read_text(encoding='utf8'))
    if core.get('state') != 'PASS' or core.get('netbsd_pin') != PIN:
        parser.error('actual successful native core receipt required')
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
    cc = shlex.split(core['flags']['CC'])
    configured = Path(core['flags']['S']).resolve(strict=True).parent
    flags = shlex.split(core['flags']['CFLAGS']) + [v.replace(str(configured)+'/',str(source)+'/')
                                               for v in shlex.split(core['flags']['CPPFLAGS'])]
    if cc != ['/usr/tools/bin/x86_64--netbsd-gcc'] or not {'-Werror','-D_KERNEL','-nostdinc'}.issubset(flags):
        parser.error('actual strict native compiler configuration required')
    state = dict(state='RUNNING',started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 pid=os.getpid(),host=socket.gethostname(),netbsd_pin=PIN,
                 core_status=str(core_path),core_status_sha256=sha(core_path),
                 sources_sha256={str(v):sha(v) for v in units},objects={},
                 full_kernel='NOT_RUN',runtime='NOT_RUN',installed=False,booted=False)
    output.mkdir()
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
                or sha(obj/'netbsd')!=core['prior_kernel_sha256']):
            raise RuntimeError('native inputs or prior kernel changed during compile')
        state.update(state='FAIL' if failures else 'PASS',failures=failures)
    except BaseException as error:
        state.update(state='FAIL',error=str(error));raise
    finally:
        state['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
    print(json.dumps(dict(state=state['state'],objects=list(state['objects']),failures=failures,status=str(output/'status.json'))))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
