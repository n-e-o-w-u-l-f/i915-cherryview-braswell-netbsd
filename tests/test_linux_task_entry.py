#!/usr/bin/env python3
"""HP-only complete actual task C/native ioctl shim lifetime/error model."""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, platform, re
import resource, shutil, socket, subprocess, tempfile, time

ROOT=Path(__file__).resolve().parents[1];WORK=Path('/root/hp-driver-port-20261005')
if platform.system()!='NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
    raise SystemExit('REFUSED: compiler-invoking tests are authorized only on HP/NetBSD')
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ap=argparse.ArgumentParser();ap.add_argument('--netbsd-tree',type=Path,default=Path('/root/netbsd-src-ref'))
args=ap.parse_args()
spec=importlib.util.spec_from_file_location('entry_generator',ROOT/'tools/generate_linux_task_entry_patch.py')
gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
patch,contract,before,after=gen.generate(args.netbsd_tree)
assert (ROOT/'patches/0037-netbsd-linux-drm-ioctl-task-entry.patch').read_text()==patch
assert json.loads((ROOT/'compat/native-entry/expected-source.json').read_text())==contract
out=WORK/('i915-drm-task-entry-proof-'+str(time.time_ns()));out.mkdir()
proof={'state':'RUNNING','host':socket.gethostname(),'netbsd_pin':gen.PIN,
    'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runs':[],'negative_controls':[]}
def save():
    tmp=out/'proof.tmp';tmp.write_text(json.dumps(proof,indent=2)+'\n');tmp.replace(out/'proof.json')
save()
try:
    with tempfile.TemporaryDirectory(prefix='i915-drm-task-entry-',dir=WORK) as name:
        temp=Path(name);include=temp/'include';include.mkdir()
        model=(ROOT/'compat/native-runtime/task/test_model.h').read_text()
        # The fatal scheduler is compiled unchanged, but not executed by
        # these entry-only tests. Unsupported delegated fatal waits trap.
        extra='''
#undef ERESTARTSYS
#define ERESTARTSYS (ELAST+1)
#define LW_WEXIT 2U
#define LW_WCORE 4U
static inline bool sleepq_fatal_pending(struct lwp *l) {
    return (l->l_flag & (LW_WEXIT|LW_WCORE))!=0 || sigispending(l,SIGKILL)!=0;
}
static inline int cv_wait_sig_fatal(kcondvar_t *c,kmutex_t *m) {
    (void)c;(void)m;assert(false);return 0;
}
static inline int cv_timedwait_sig_fatal(kcondvar_t *c,kmutex_t *m,int n) {
    (void)c;(void)m;(void)n;assert(false);return 0;
}
'''
        assert model.endswith('#endif\n');model=model[:-len('#endif\n')]+extra+'#endif\n'
        (include/'wait_test_model.h').write_text(model)
        headers=['sys/'+n+'.h' for n in ('param','atomic','condvar','intr','kmem','lwp','proc','signalvar','sleepq','specificdata','systm','kernel')]
        headers+=['asm/barrier.h','asm/param.h','asm/processor.h']
        headers+=['linux/'+n+'.h' for n in ('list','stddef','spinlock','raw_spinlock','errno','kthread')]
        for rel in headers:
            p=include/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include <wait_test_model.h>\n')
        (include/'linux/task_netbsd.h').write_text(after[gen.HEADER])
        shutil.copyfile(ROOT/'compat/native-runtime/task/sched.h',include/'linux/sched.h')
        task=temp/'linux_task.c';task.write_text(after[gen.TASK])
        assert hashlib.sha256(task.read_bytes()).hexdigest()==contract['files'][gen.TASK]['after_sha256']
        shim=re.search(r'static int\ndrm_ioctl_shim\([\s\S]*?\n\}',after[gen.DRM]).group()
        (temp/'drm_ioctl_shim.inc').write_text(shim+'\n')
        shutil.copyfile(ROOT/'compat/native-entry/test_entry.c',temp/'test_entry.c')
        def compile_to(label,flags=()):
            exe=temp/label;cmd=['/usr/bin/cc','-D_NETBSD_SOURCE','-std=gnu11','-O2','-g','-pthread',
                '-Wall','-Wextra','-Werror','-Wshadow','-Wno-unused-parameter',*flags,
                '-I'+str(include),'-I'+str(temp),str(temp/'test_entry.c'),'-o',str(exe)]
            result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
            (out/(label+'-compile.log')).write_text(result.stdout)
            if result.returncode:print(result.stdout);raise RuntimeError('compile: '+label)
            return exe,cmd
        for label,flags in [('normal',()),('ubsan',('-fsanitize=undefined','-fno-sanitize-recover=all'))]:
            exe,cmd=compile_to(label,flags)
            run=subprocess.run([str(exe)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
            (out/(label+'-run.log')).write_text(run.stdout);print(run.stdout,flush=True)
            if run.returncode:raise RuntimeError('run: '+label)
            counts=re.search(r'DRM_TASK_ENTRY_SCENARIOS=(\d+) CHECKS=(\d+)',run.stdout);assert counts
            proof['runs'].append({'kind':label,'scenarios':int(counts[1]),'checks':int(counts[2]),
                'compile_exit':0,'run_exit':0,'command':cmd});save()
        controls=[('no-native-entry',re.search(r'static int\ndrm_ioctl_shim\([\s\S]*?\n\}',before[gen.DRM]).group()),
            ('leaked-entry-reference',shim.replace('\tlinux_task_entry_leave(&task);','\t(void)task;'))]
        for label,changed in controls:
            (temp/'drm_ioctl_shim.inc').write_text(changed+'\n');exe,cmd=compile_to(label)
            run=subprocess.run([str(exe)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
            (out/(label+'-run.log')).write_text(run.stdout)
            assert run.returncode!=0,'semantic control unexpectedly passed: '+label
            proof['negative_controls'].append({'name':label,'compile_exit':0,'run_exit':run.returncode,
                'expected':'nonzero task-identity/reference assertion'});save()
    proof.update(state='PASSED',contract=contract,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [ROOT/'compat/native-entry/task_entry.inc',ROOT/'compat/native-entry/test_entry.c',
             ROOT/'tools/generate_linux_task_entry_patch.py',ROOT/'patches/0037-netbsd-linux-drm-ioctl-task-entry.patch',Path(__file__)]},
        scope='Complete actual task runtime plus exact changed native DRM ioctl shim with delegated pthread/specificdata/softint and bounded DRM callback models.',
        limitations=['Only the ioctl override/fallback entry is bound. Workqueue, other DRM/file/attach/PM entries and external callback/code-owner rundown remain OPEN.',
            'LWP TLS identity deliberately persists until real exit; module unload stays EBUSY while tasks/external references remain.',
            'Native CV/signal/scheduler/softint execution, MM/folio/UVM, PID semantics, selected410/full kernel and physical KMS are not accepted.'],
        acceptance='OPEN: both full ports and HP WLAN online')
except Exception as exc:
    proof.update(state='FAILED',error=str(exc));save();raise
save();print('DRM_TASK_ENTRY_PROOF',out,flush=True)
