#!/usr/bin/env python3
"""HP-only actual native task/module/DRM-entry build in the isolated stage."""
from pathlib import Path
import argparse,datetime,hashlib,json,platform,shlex,socket,subprocess

ROOT=Path(__file__).resolve().parents[1];WORK=Path('/root/hp-driver-port-20261005')
if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: native builds are authorized only on HP/NetBSD')
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
out=args.output.resolve();assert out.parent==WORK and not out.exists();out.mkdir()
tree=WORK/'netbsd-full-linux';runtime=tree/'sys/external/bsd/drm2'
contract=json.loads((ROOT/'compat/native-entry/expected-source.json').read_text())
patch=ROOT/'patches/0037-netbsd-linux-drm-ioctl-task-entry.patch'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(patch)==contract['patch_sha256']
state={'state':'RUNNING','host':socket.gethostname(),'checks':[],
    'source_sha256':{},'header_sha256':{},'objects':{},'contract':contract,
    'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'acceptance':'OPEN: other native entries/workqueues/code-owner rundown, MM/folio/UVM, selected410/kernel and actual KMS/WLAN runtime'}
def save():
    tmp=out/'status.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(out/'status.json')
save()
try:
    for rel,row in contract['files'].items():assert sha(tree/rel)==row['before_sha256'],rel
    subprocess.run(['git','-C',str(tree),'apply','--check',str(patch)],check=True)
    subprocess.run(['git','-C',str(tree),'apply',str(patch)],check=True)
    for rel,row in contract['files'].items():assert sha(tree/rel)==row['after_sha256'],rel
    state['patch_applied']=True;save()
    line=next(x for x in (WORK/'native-math64-drm_buddy.log').read_text().splitlines()
        if x.startswith(str(WORK/'full-linux-tools/bin/x86_64--netbsd-gcc ')) and ' -c ' in x)
    flags=shlex.split(line);flags=flags[:flags.index('-c')]
    for rel in ['sys/external/bsd/drm2/include/linux/task_netbsd.h','sys/external/bsd/drm2/include/linux/sched.h',
        'sys/external/bsd/drm2/include/linux/wait.h','sys/external/bsd/drm2/include/linux/kthread.h',
        'sys/sys/condvar.h','sys/sys/sleepq.h','sys/sys/syncobj.h']:
        state['header_sha256'][rel]=sha(tree/rel)
    sources={'linux_task':runtime/'linux/linux_task.c','linux_module':runtime/'linux/linux_module.c',
        'drm_cdevsw':runtime/'drm/drm_cdevsw.c'}
    failures=[]
    for name,source in sources.items():
        obj=out/(name+'.o');state['source_sha256'][str(source.relative_to(tree))]=sha(source)
        command=flags+['-c',str(source),'-o',str(obj)]
        result=subprocess.run(command,cwd=WORK/'full-linux-obj',text=True,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,timeout=180)
        log=out/(name+'.log');log.write_text(result.stdout)
        state['checks'].append({'name':name,'exit':result.returncode,'command':command,'log_sha256':sha(log)})
        print(name,result.returncode,flush=True)
        if result.returncode:failures.append(name);print(result.stdout,flush=True)
        else:state['objects'][name]={'bytes':obj.stat().st_size,'sha256':sha(obj)}
        save()
    state.update(state='FAILED' if failures else 'PASSED',failures=failures,
        updated=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
    raise SystemExit(bool(failures))
except Exception as exc:
    state.update(state='FAILED',error=str(exc));save();raise
