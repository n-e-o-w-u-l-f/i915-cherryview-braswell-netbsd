#!/usr/bin/env python3
"""Compose actual native common-runtime init/unwind/quiesce at exact0032."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
TARGET='sys/external/bsd/drm2/linux/linux_module.c'
PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
ORIGINAL='454f2f2ece607c75379fae48c81ec07f8946e56e9aa590cdfa0e824df169e6be'
def sha(data):return hashlib.sha256(data).hexdigest()
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('native runtime anchor drift: '+old[:100])
    return text.replace(old,new)
def prepare(reference,output):
    if output.exists() or output.is_symlink():raise ValueError('new output required')
    original=(reference/TARGET).read_bytes()
    if sha(original)!=ORIGINAL:raise ValueError('wrong native runtime source identity')
    patch=(ROOT/'patches/0032-netbsd-linux-task-wait-worker.patch').read_bytes().replace(b'\r\n',b'\n')
    with tempfile.TemporaryDirectory(prefix='native-runtime-owner-') as name:
        temp=Path(name);source=temp/TARGET;source.parent.mkdir(parents=True);source.write_bytes(original)
        subprocess.run(['git','-c','core.autocrlf=false','-C',str(temp),'apply','--include='+TARGET,'-'],input=patch,check=True)
        before=source.read_bytes()
    text=before.decode()
    text=once(text,'#include <linux/atomic.h>\n','#include <linux/atomic.h>\n#include <linux/native_runtime_owner_netbsd.h>\n')
    shutdown='''/* All external identity publication is closed before the aggregate drain.
 * The actual MM queue join and native callback call count cover code return.
 * Init failure reaches this only after a successful MM init and before any
 * external caller can pass the enclosing native once/module admission.
 */
static void
linux_mm_shutdown(void)
{
\tint error = linux_mm_identity_quiesce();
\tif (error != 0)
\t\tpanic("linux MM shutdown: live owner after quiesce: %d", error);
\terror = linux_mm_identity_fini();
\tif (error != 0)
\t\tpanic("linux MM shutdown: incomplete native drain: %d", error);
}

'''
    text=once(text,'static int\nlinux_init(void)',shutdown+'static int\nlinux_init(void)')
    text=once(text,'\terror = linux_workqueue_init();\n',
        '\t/* Native MM retirement uses its own native queue, and must exist\n'
        '\t * before any Linux callback worker can publish a task MM. */\n'
        '\terror = linux_mm_identity_init();\n'
        '\tif (error) {\n\t\tprintf("linux: unable to initialize MM owners: %d\\n", error);\n'
        '\t\tgoto fail_mm;\n\t}\n\n\terror = linux_workqueue_init();\n')
    text=once(text,'\tlinux_irq_work_init();\n',
        '\t/* Task/specificdata resources already exist; FILE init owns its\n'
        '\t * queues, shared anon inode, page retirement and commit ledger. */\n'
        '\terror = linux_file_system_init();\n'
        '\tif (error) {\n\t\tprintf("linux: unable to initialize FILE owners: %d\\n", error);\n'
        '\t\tgoto fail_file;\n\t}\n\n\tlinux_irq_work_init();\n')
    text=once(text,'fail9:\n', 'fail_file:\n\tlinux_wait_var_fini();\nfail9:\n')
    text=once(text,'fail3:\tlinux_rcu_gc_fini();\n',
        'fail3:\tlinux_mm_shutdown();\nfail_mm:\n\tlinux_rcu_gc_fini();\n')
    text=once(text,'\tlinux_workqueue_fini();\n\tlinux_rcu_gc_fini();\n',
        '\tlinux_workqueue_fini();\n\tlinux_mm_shutdown();\n\tlinux_rcu_gc_fini();\n')
    text=once(text,'\t\tint error = linux_task_system_quiesce();\n'
        '\t\tif (error != 0)\n\t\t\treturn error;\n\t\tlinux_fini();',
        '\t\tint error = linux_mm_identity_quiesce();\n'
        '\t\tif (error != 0)\n\t\t\treturn error;\n'
        '\t\t/* FILE performs the retained-LWP task quiesce and queue join.\n'
        '\t\t * A refusal preserves FILE resources and restores MM admission. */\n'
        '\t\terror = linux_file_system_fini();\n'
        '\t\tif (error != 0) {\n\t\t\tlinux_mm_identity_resume();\n\t\t\treturn error;\n\t\t}\n'
        '\t\tlinux_fini();')
    after=text.encode()
    diff=''.join(difflib.unified_diff(before.decode().splitlines(True),text.splitlines(True),
                                    'a/'+TARGET,'b/'+TARGET)).encode()
    header=ROOT/'compat/native-runtime-owner/include/linux/native_runtime_owner_netbsd.h'
    contract=dict(netbsd_pin=PIN,required_prior='exact0032 runtime at native pin;0035/0037 do not alter this unit',
        prior_source_patch_sha256=sha(patch),patch_sha256=sha(diff),
        files={TARGET:dict(before_sha256=sha(before),after_sha256=sha(after))},
        header_sha256=sha(header.read_bytes().replace(b'\r\n',b'\n')),
        acceptance='Source preparation only; actual Native init/refusal/unwind/lifecycle compilation and full aggregate link remain mandatory.')
    output.mkdir(parents=True)
    target=output/TARGET;target.parent.mkdir(parents=True);target.write_bytes(after)
    (output/'runtime-owner.patch').write_bytes(diff)
    (output/'runtime-owner.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(patch_sha256=sha(diff),source_sha256=sha(after))))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.reference,args.output)
