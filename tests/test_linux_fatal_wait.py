#!/usr/bin/env python3
"""Actual shared-stage Linux runtime and native fatal policy; HP-only model/build."""
from pathlib import Path
import hashlib,json,os,platform,resource,shutil,socket,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];WORK=Path('/root/hp-driver-port-20261005')
assert platform.system()=='NetBSD' and socket.gethostname().startswith('hp-tpnw121')
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
assets=ROOT/'compat/native-fatal';tree=WORK/'netbsd-full-linux';runtime=tree/'sys/external/bsd/drm2'
contract=json.loads((assets/'expected-source.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
out=WORK/('i915-fatal-proof-'+str(time.time_ns()));out.mkdir()
for rel,row in contract['files'].items():assert sha(tree/rel)==row['after'],rel
for name,digest in contract['model_sha256'].items():assert sha(assets/name)==digest,name
with tempfile.TemporaryDirectory(prefix='hp-native-fatal-model-',dir=WORK) as name:
 temp=Path(name);patch=temp/'fatal.patch'
 subprocess.run([sys.executable,str(ROOT/'tools/generate_linux_fatal_wait_patch.py'),'--netbsd-tree','/root/netbsd-src-ref','--out',str(patch)],check=True)
 assert patch.read_bytes()==(ROOT/'patches/0035-netbsd-linux-fatal-wait.patch').read_bytes()
 task=temp/'task';(task/'include/linux').mkdir(parents=True)
 for name in ['test_wait.c','test_model.h','run_model.py']:shutil.copyfile(assets/name,task/name)
 for name in ['linux_task.c','linux_wait.c','linux_wait_var.c']:shutil.copyfile(runtime/'linux'/name,task/name)
 for name in ['sched.h','task_netbsd.h','wait.h','wait_bit.h']:shutil.copyfile(runtime/'include/linux'/name,task/'include/linux'/name)
 sleep=(tree/'sys/kern/kern_sleepq.c').read_text()
 start=sleep.index('/*\n * Native signal-post eligibility')
 end=sleep.index('/*\n * sleepq_block:',start)
 (task/'fatal_policy.c').write_text(sleep[start:end])
 assert sha(task/'fatal_policy.c')=='ff2c461d7727c24a220ae0ebb8565d1ee7ac975fbfe4736e6a4f3989a55dbb04'
 run=subprocess.run([sys.executable,str(task/'run_model.py')],env=dict(os.environ,NETBSD_RUNTIME_TEST_TASK=str(task)),text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
 (out/'model-driver.log').write_text(run.stdout);print(run.stdout,flush=True)
 for name in ['callback-task-test-status.json','tests/compile.log','tests/run.log']:
  p=task/name
  if p.exists():shutil.copyfile(p,out/p.name)
 assert run.returncode==0,run.returncode
 model=json.loads((out/'callback-task-test-status.json').read_text());assert model['state']=='PASS'
 for rel,key in [('sys/external/bsd/drm2/linux/linux_task.c','linux_task.c'),('sys/external/bsd/drm2/linux/linux_wait.c','linux_wait.c'),('sys/external/bsd/drm2/linux/linux_wait_var.c','linux_wait_var.c')]:
  assert model['files'][key]==sha(tree/rel),rel
build=WORK/('i915-fatal-native-build-'+str(time.time_ns()))
subprocess.run([sys.executable,str(ROOT/'tools/build_hp_fatal_wait.py'),'--output',str(build)],check=True)
native=json.loads((build/'status.json').read_text());assert native['state']=='PASSED'
proof={'state':'PASSED','actual_source_contract':contract,'model':model,'native':native,'native_build_directory':str(build),'acceptance':'OPEN: actual native CV/sleepq/signal-post/group-exit/ptrace execution, cold/panic contexts, full selected410/kernel/lifecycle/KMS; new core kernel is a prerequisite, not supported by running F77'}
(out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('ACTUAL_SHARED_FATAL_WAIT_SOURCE_MODEL_AND_NATIVE_BUILD_PASS',out)
