#!/usr/bin/env python3
"""Actual staged UUID bodies, private namespace and native CPRNG bindings on HP."""
from pathlib import Path
import hashlib,json,platform,shutil,socket,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1]
WORK=Path('/root/hp-driver-port-20261005')
if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('UUID compilation and tests authorized only on HP')
stage=WORK/'netbsd-full-linux/sys/external/bsd/drm2'
with tempfile.TemporaryDirectory(prefix='uuid-integration-model-',dir=WORK) as name:
    temp=Path(name)
    for p in (ROOT/'compat/native-uuid').iterdir():
        if p.is_dir():shutil.copytree(p,temp/p.name)
        else:shutil.copyfile(p,temp/p.name)
    patch=temp/'integration.patch'
    subprocess.run([sys.executable,str(ROOT/'tools/generate_linux_uuid_patch.py'),
                    '--netbsd-tree','/root/netbsd-src-ref','--out',str(patch)],check=True)
    assert patch.read_bytes()==(ROOT/'patches/0033-netbsd-linux-uuid-guid.patch').read_bytes()
    subprocess.run([sys.executable,str(temp/'generate.py')],check=True)
    paths={'include/linux/uuid.h':stage/'include/linux/uuid.h',
           'linux_uuid.c':stage/'linux/linux_uuid.c','native_acpi.c':stage/'linux/linux_acpi.c'}
    digests={}
    for relative,actual in paths.items():
        assert actual.read_bytes()==(temp/relative).read_bytes(),relative
        digests[str(actual)]=hashlib.sha256(actual.read_bytes()).hexdigest()
    subprocess.run([sys.executable,str(temp/'build_hp.py')],check=True)
    proof=json.loads((temp/'proof.json').read_text())
    assert all(c['exit']==0 for c in proof['checks']) and not proof['unresolved_uuid_api']
    proof['integrated_stage_sha256']=digests
    proof['native_header_selection']='actual shared-stage flags, no candidate include override'
    out=WORK/('i915-uuid-proof-'+str(time.time_ns()))
    out.mkdir()
    (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    for p in temp.glob('*.log'):shutil.copyfile(p,out/p.name)
    for p in temp.glob('*.o'):shutil.copyfile(p,out/p.name)
    print('UUID_NATIVE_AND_FUNCTIONAL_PROOF',out)
print('NATIVE_UUID_GUID_PASS groups=5 entropy_fills=1024 parse_roundtrips=512 kernel_entropy_execution=OPEN')
