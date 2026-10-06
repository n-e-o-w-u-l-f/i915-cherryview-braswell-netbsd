#!/usr/bin/env python3
"""Compile/run exact candidate queue/task sources with bounded model on HP."""
import hashlib
import os
import json
import re
import subprocess
from pathlib import Path
ROOT=Path(os.environ['NETBSD_RUNTIME_TEST_TASK'])
assert subprocess.check_output(['uname','-n'],text=True).strip()=='hp-tpnw121.fritz.box'
TEST=ROOT/'tests'; TEST.mkdir(exist_ok=True)
INCLUDE=TEST/'include'; INCLUDE.mkdir(exist_ok=True)
(INCLUDE/'wait_test_model.h').write_bytes((ROOT/'test_model.h').read_bytes())
headers=['sys/'+n+'.h' for n in ('param','atomic','condvar','intr','kmem','lwp','proc',
    'signalvar','sleepq','specificdata','systm','kernel')]
headers+=['asm/barrier.h','asm/param.h','asm/processor.h']
headers+=['linux/'+n+'.h' for n in ('list','stddef','spinlock','raw_spinlock','errno','kthread')]
for name in headers:
    p=INCLUDE/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include <wait_test_model.h>\n')
for name in ['machine/limits.h','sys/sched.h']:
    (INCLUDE/name).unlink(missing_ok=True)
(TEST/'test_wait.c').write_bytes((ROOT/'test_wait.c').read_bytes())
pin='fd179f8a05be3ccae366b9b96e176b51fbe54aab'
guc=subprocess.check_output(['git','-C','/root/linux-rtl8723be-ref-fresh','show',
    pin+':drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c'],text=True)
match=re.search(r'static long must_wait_woken\([\s\S]*?\n\}',guc)
assert match is not None
(TEST/'guc_wait.c').write_text(match.group()+'\n')
cmd=['cc','-std=gnu11','-O2','-g','-pthread','-Wall','-Wextra','-Werror','-Wshadow',
    '-Wno-unused-parameter','-I'+str(INCLUDE),'-I'+str(ROOT/'include'),
    str(TEST/'test_wait.c'),'-o',str(TEST/'test_wait')]
r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(TEST/'compile.log').write_text(r.stdout);print('compile',r.returncode);print(r.stdout)
if r.returncode: raise SystemExit(r.returncode)
r=subprocess.run([str(TEST/'test_wait')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
(TEST/'run.log').write_text(r.stdout);print(r.stdout);print('run',r.returncode)
status={'state':'PASS' if r.returncode==0 else 'FAIL','exit':r.returncode,'command':cmd,
    'linux_pin':pin,'scope':'Actual candidate C + pinned GuC helper against pthread delegation model. Not native NetBSD sleepq execution.',
    'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
      [ROOT/'linux_task.c',ROOT/'linux_wait.c',ROOT/'linux_wait_var.c',ROOT/'include/linux/wait.h',
       ROOT/'include/linux/wait_bit.h',ROOT/'include/linux/sched.h',
       ROOT/'include/linux/task_netbsd.h',ROOT/'test_model.h',ROOT/'test_wait.c',TEST/'guc_wait.c',TEST/'run.log']}}
(ROOT/'callback-task-test-status.json').write_text(json.dumps(status,indent=2)+'\n')
raise SystemExit(r.returncode)
