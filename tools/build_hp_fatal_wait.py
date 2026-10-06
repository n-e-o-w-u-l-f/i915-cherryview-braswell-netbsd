#!/usr/bin/env python3
"""Compile the actual shared fatal backend/runtime, HP only; no header override."""
from pathlib import Path
import argparse,datetime,hashlib,json,platform,shlex,socket,subprocess
WORK=Path('/root/hp-driver-port-20261005')
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
assert platform.system()=='NetBSD' and socket.gethostname().startswith('hp-tpnw121')
out=args.output.resolve();assert out.parent==WORK and not out.exists();out.mkdir()
tree=WORK/'netbsd-full-linux';runtime=tree/'sys/external/bsd/drm2'
line=next(x for x in (WORK/'native-math64-drm_buddy.log').read_text().splitlines() if x.startswith(str(WORK/'full-linux-tools/bin/x86_64--netbsd-gcc ')) and ' -c ' in x)
flags=shlex.split(line);flags=flags[:flags.index('-c')]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
state={'state':'RUNNING','host':socket.gethostname(),'checks':[],'source_sha256':{},'header_sha256':{},'objects':{},'acceptance':'OPEN: actual native CV/sleepq/signal/exit/group/ptrace execution, full kernel link and physical driver runtime'}
def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
for rel in ['sys/sys/condvar.h','sys/sys/sleepq.h','sys/sys/syncobj.h','sys/external/bsd/drm2/include/linux/sched.h','sys/external/bsd/drm2/include/linux/task_netbsd.h','sys/external/bsd/drm2/include/linux/wait.h','sys/external/bsd/drm2/include/linux/wait_bit.h','sys/external/bsd/drm2/include/linux/kthread.h','sys/external/bsd/common/include/linux/completion.h']:
 state['header_sha256'][rel]=sha(tree/rel)
def run(name,command):
 p=subprocess.run(command,cwd=WORK/'full-linux-obj',text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
 log=out/(name+'.log');log.write_text(p.stdout)
 state['checks'].append({'name':name,'exit':p.returncode,'command':command,'log_sha256':sha(log)})
 save();print(name,p.returncode,flush=True)
 if p.returncode:print(p.stdout,flush=True);state['state']='FAILED';save();raise SystemExit(p.returncode)
sources={name:tree/('sys/kern/'+name+'.c') for name in ['kern_condvar','kern_sleepq','kern_sig']}
sources.update({name:runtime/'linux'/(name+'.c') for name in ['linux_task','linux_wait','linux_wait_var','linux_kthread','linux_module']})
# These immutable native sources define four existing module imports.
# Compile them rather than misclassifying them as newly missing fatal APIs.
legacy={'linux_tasklet':tree/'sys/external/bsd/common/linux/linux_tasklet.c',
        'linux_wait_bit':runtime/'linux/linux_wait_bit.c'}
state['coexisting_legacy_native_sources']={}
for name,src in legacy.items():
 original=subprocess.check_output(['git','-C','/root/netbsd-src-ref','show',
      '03d918f6d0e81fa05b8f1160eca0628ad39988a6:'+str(src.relative_to(tree))])
 assert original==src.read_bytes(),name
 state['coexisting_legacy_native_sources'][name]={'sha256':sha(src),
       'scope':'native object/link coexistence only; full legacy bit/lock/IO/timeout and tasklet execution remain OPEN'}
sources.update(legacy)
objects=[]
for name,src in sources.items():
 obj=out/(name+'.o');state['source_sha256'][str(src.relative_to(tree))]=sha(src)
 run(name,flags+['-c',str(src),'-o',str(obj)])
 state['objects'][name]={'bytes':obj.stat().st_size,'sha256':sha(obj)}
 objects.append(obj)
linked=out/'native-fatal-runtime.o'
run('native-fatal-shared-link',[str(WORK/'full-linux-tools/bin/x86_64--netbsd-ld'),'-r','-o',str(linked),*map(str,objects)])
nm=subprocess.check_output(['/usr/bin/nm','-g',str(linked)],text=True);(out/'symbols.log').write_text(nm)
unresolved=[x.split()[-1] for x in nm.splitlines() if ' U ' in x]
owned=['linux_task','linux_wait','linux_kthread','linux_signal','linux_fatal_signal','linux_schedule','linux_finish_wait','linux_prepare_to_wait','linux_wake_up','linux_default_wake','linux_autoremove_wake','linux_var_wait','linux_task','linux___set_current','linux_set_current']
bad=[x for x in unresolved if x in ['cv_wait_sig_fatal','cv_timedwait_sig_fatal','sleepq_sigwake_allowed','sleepq_fatal_pending'] or any(x.startswith(p) for p in owned)]
state['unresolved_new_shared_symbols']=bad
state['linked_object']={'sha256':sha(linked),'bytes':linked.stat().st_size}
state['state']='FAILED' if bad else 'PASSED';state['updated']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
assert not bad,bad
print('REAL_SHARED_NATIVE_FATAL_KERNEL_AND_RUNTIME_OBJECTS_PASS count=10')
