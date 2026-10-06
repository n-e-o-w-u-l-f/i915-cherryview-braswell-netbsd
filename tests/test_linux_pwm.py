#!/usr/bin/env python3
"""Actual frozen consumer/layout/body probes on HP; complete-type hygiene is real."""
from pathlib import Path
import hashlib,json,platform,shutil,socket,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];WORK=Path('/root/hp-driver-port-20261005')
if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):raise SystemExit('PWM tests/builds authorized only on HP')
stage=WORK/'netbsd-full-linux/sys/external/bsd/drm2'
with tempfile.TemporaryDirectory(prefix='pwm-integration-model-',dir=WORK) as name:
 temp=Path(name)
 shutil.copytree(ROOT/'compat/native-pwm',temp,dirs_exist_ok=True)
 patch=temp/'integration.patch'
 subprocess.run([sys.executable,str(ROOT/'tools/generate_linux_pwm_patch.py'),'--netbsd-tree','/root/netbsd-src-ref','--out',str(patch)],check=True)
 assert patch.read_bytes()==(ROOT/'patches/0034-netbsd-linux-pwm-consumer.patch').read_bytes()
 subprocess.run([sys.executable,str(temp/'generate.py')],check=True)
 assert (temp/'include/linux/pwm.h').read_bytes()==(stage/'include/linux/pwm.h').read_bytes()
 subprocess.run([sys.executable,str(temp/'audit_hp.py'),'--out',str(temp)],check=True)
 subprocess.run([sys.executable,str(temp/'build_hp.py')],check=True)
 proof=json.loads((temp/'proof.json').read_text());assert all(x['validated'] for x in proof['checks'])
 out=WORK/('i915-pwm-proof-'+str(time.time_ns()));out.mkdir()
 proof['integrated_pwm_header_sha256']=hashlib.sha256((stage/'include/linux/pwm.h').read_bytes()).hexdigest()
 proof['candidate_header_matches_shared_stage']=True
 (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 for p in temp.glob('*.o'):shutil.copyfile(p,out/p.name)
 for p in temp.glob('*.log'):shutil.copyfile(p,out/p.name)
 shutil.copyfile(temp/'pwm-call-audit.json',out/'pwm-call-audit.json')
 print('PWM_NATIVE_AND_FUNCTIONAL_PROOF',out)
# Genuine complete-type dependency checks use actual full modern headers and
# shared native headers, without a candidate include override.
line=next(x for x in (WORK/'native-math64-drm_buddy.log').read_text().splitlines() if x.startswith(str(WORK/'full-linux-tools/bin/x86_64--netbsd-gcc ')) and ' -c ' in x)
import shlex
flags=shlex.split(line);flags=flags[:flags.index('-c')]
source=out/'complete_type_probe.c'
source.write_text('#include <drm/drm_atomic.h>\n#include <linux/pwm.h>\n__CTASSERT(sizeof(((struct drm_crtc_commit *)0)->flip_done) == sizeof(struct completion));\n__CTASSERT(sizeof(((struct drm_crtc_commit *)0)->hw_done) == sizeof(struct completion));\n__CTASSERT(sizeof(((struct drm_crtc_commit *)0)->cleanup_done) == sizeof(struct completion));\n__CTASSERT(sizeof(struct pwm_state) > 0);\n')
run=subprocess.run(flags+['-c',str(source),'-o',str(out/'complete_type_probe.o')],cwd=WORK/'full-linux-obj',text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
(out/'complete_type_probe.log').write_text(run.stdout)
if run.returncode:print(run.stdout);raise SystemExit(run.returncode)
proof['actual_complete_type_probe']={'exit':0,'command':flags+['-c',str(source),'-o',str(out/'complete_type_probe.o')],'object_sha256':hashlib.sha256((out/'complete_type_probe.o').read_bytes()).hexdigest()}
(out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('NATIVE_PWM_AND_COMPLETE_TYPE_PASS disabled_profile=pin enabled_provider=OPEN')
