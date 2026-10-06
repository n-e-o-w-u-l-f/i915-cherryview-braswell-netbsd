#!/usr/bin/env python3
"""HP only: actual bit provider source, model regressions and old-source controls."""
from pathlib import Path
import hashlib,json,os,platform,resource,shlex,shutil,socket,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];WORK=Path('/root/hp-driver-port-20261005')
assert platform.system()=='NetBSD' and socket.gethostname().startswith('hp-tpnw121')
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
assets=ROOT/'compat/native-bit-wait';contract=json.loads((assets/'expected-source.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
tree=WORK/'netbsd-full-linux';src=tree/contract['source_path']
assert sha(src)==contract['after_sha256']
assert src.read_bytes()==(assets/'linux_wait_bit.c').read_bytes()
for name,digest in contract['model_sha256'].items():assert sha(assets/name)==digest,name
for name,digest in contract['linux_input_sha256'].items():
 b=subprocess.check_output(['git','-C','/root/linux-rtl8723be-ref-fresh','show',contract['linux_pin']+':'+name])
 assert hashlib.sha256(b).hexdigest()==digest,name
sched=(tree/'sys/external/bsd/drm2/include/linux/sched.h').read_text()
for name,value in [('TASK_INTERRUPTIBLE','0x00000001'),('TASK_UNINTERRUPTIBLE','0x00000002'),('TASK_WAKEKILL','0x00000100')]:
 assert any(line.split()==['#define',name,value] for line in sched.splitlines()),name
out=WORK/('i915-bit-wait-proof-'+str(time.time_ns()));out.mkdir()
state={'state':'RUNNING','actual_source_sha256':sha(src),'source_contract':contract,'checks':[],
       'scope':'Existing native clear/wait/timed-wait ABI only. Explicit pthread/virtual-time model; native execution/full kernel/keyed-bit/lock/action/IO/admission acceptance OPEN.'}
def run(name,cmd,negative=False):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
 log=out/(name+'.log');log.write_text(p.stdout)
 state['checks'].append({'name':name,'exit':p.returncode,'expected_failure':negative,'command':cmd,'log_sha256':sha(log)})
 print(name,p.returncode,flush=True)
 if p.stdout:print(p.stdout,flush=True)
 assert (p.returncode!=0) if negative else (p.returncode==0),name
 return p
with tempfile.TemporaryDirectory(prefix='hp-bit-wait-check-',dir=WORK) as name:
 temp=Path(name);patch=temp/'policy.patch'
 run('regenerate',[sys.executable,str(ROOT/'tools/generate_linux_bit_wait_patch.py'),'--netbsd-tree','/root/netbsd-src-ref','--out',str(patch)])
 assert patch.read_bytes()==(ROOT/'patches/0036-netbsd-linux-bit-wait-policy.patch').read_bytes()
 target=temp/contract['source_path'];target.parent.mkdir(parents=True)
 old=subprocess.check_output(['git','-C','/root/netbsd-src-ref','show',contract['netbsd_pin']+':'+contract['source_path']])
 target.write_bytes(old)
 run('actual-patch-check',['git','-C',str(temp),'apply','--check',str(patch)])
 run('actual-patch-apply',['git','-C',str(temp),'apply',str(patch)])
 assert sha(target)==sha(src)
 for name in ['test_model.h','test_wait_bit.c']:shutil.copyfile(assets/name,temp/name)
 shutil.copyfile(src,temp/'linux_wait_bit.c');(temp/'legacy_linux_wait_bit.c').write_bytes(old)
 inc=temp/'include'
 for rel in ['sys/param.h','sys/bitops.h','sys/condvar.h','sys/mutex.h','sys/systm.h','linux/bitops.h','linux/sched.h','linux/wait_bit.h']:
  p=inc/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "test_model.h"\n')
 flags=['cc','-std=gnu11','-O2','-g','-pthread','-Wall','-Wextra','-Werror','-Wshadow','-I'+str(inc),'-I'+str(temp)]
 for label,extra in [('normal',[]),('ubsan',['-fsanitize=undefined','-fno-sanitize-recover=all'])]:
  dep=temp/(label+'.d');exe=temp/label
  run(label+'-compile',flags+extra+['-MD','-MF',str(dep),str(temp/'test_wait_bit.c'),'-o',str(exe)])
  deps={str(Path(x).resolve()) for x in shlex.split(dep.read_text().replace('\\\n',' ').partition(':')[2])}
  assert str((temp/'linux_wait_bit.c').resolve()) in deps
  state[label+'_compiled_dependencies']=sorted(deps)
  run(label+'-run',[str(exe)])
 oldexe=temp/'legacy'
 run('legacy-compile',flags+['-DHP_BIT_SOURCE="legacy_linux_wait_bit.c"',str(temp/'test_wait_bit.c'),'-o',str(oldexe)])
 for label in ['success','wide','fatal','ordering']:
  run('legacy-'+label,[str(oldexe),label],negative=True)
state['state']='PASSED';state['header_sha256']=sha(tree/'sys/external/bsd/drm2/include/linux/wait_bit.h')
(out/'proof.json').write_text(json.dumps(state,indent=2)+'\n')
print('ACTUAL_SHARED_NATIVE_BIT_WAIT_POLICY_MODEL_PASS',out)
