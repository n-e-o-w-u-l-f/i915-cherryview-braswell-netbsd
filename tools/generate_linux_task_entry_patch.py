#!/usr/bin/env python3
"""Generate real native DRM ioctl task entry atop frozen0032/0035 sources."""
from pathlib import Path
import argparse, difflib, hashlib, json, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
TASK='sys/external/bsd/drm2/linux/linux_task.c'
HEADER='sys/external/bsd/drm2/include/linux/task_netbsd.h'
DRM='sys/external/bsd/drm2/drm/drm_cdevsw.c'

def once(text,old,new):
    assert text.count(old)==1,old[:80]
    return text.replace(old,new)

def generate(netbsd):
    assert subprocess.check_output(['git','-C',str(netbsd),'rev-parse','HEAD'],text=True).strip()==PIN
    fatal=json.loads((ROOT/'compat/native-fatal/expected-source.json').read_text())
    old_task=(ROOT/'compat/native-runtime/task/linux_task.c').read_bytes()
    assert hashlib.sha256(old_task).hexdigest()==fatal['files'][TASK]['before']
    patch=ROOT/'compat/native-fatal/task-runtime.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest()==fatal['asset_patch_sha256']['task-runtime.patch']
    with tempfile.TemporaryDirectory(prefix='native-entry-source-') as name:
        temp=Path(name);target=temp/TASK;target.parent.mkdir(parents=True);target.write_bytes(old_task)
        subprocess.run(['git','-C',str(temp),'apply','--include='+TASK,str(patch)],check=True)
        data=target.read_bytes();assert hashlib.sha256(data).hexdigest()==fatal['files'][TASK]['after']
        task=data.decode()
    header=(ROOT/'compat/native-runtime/task/task_netbsd.h').read_text()
    drm=subprocess.check_output(['git','-C',str(netbsd),'show',PIN+':'+DRM])
    blob=hashlib.sha1(b'blob '+str(len(drm)).encode()+b'\0'+drm).hexdigest()
    assert blob=='eba6fc5b25c6be53c8a51b0649f6c827c3b46d55'
    drm=drm.decode()
    body=(ROOT/'compat/native-entry/task_entry.inc').read_text()
    new_task=once(task,'void\nlinux_get_task_struct(struct task_struct *task)',
        body+'\nvoid\nlinux_get_task_struct(struct task_struct *task)')
    new_header=once(header,'struct task_struct *linux_current_task(void);',
        'struct task_struct *linux_current_task(void);\n'
        'int linux_task_entry_enter(struct task_struct **);\n'
        'void linux_task_entry_leave(struct task_struct **);')
    new_drm=once(drm,'#include <linux/err.h>\n',
        '#include <linux/err.h>\n#include <linux/sched.h>\n')
    old='''static int
drm_ioctl_shim(struct file *fp, unsigned long cmd, void *data)
{
\tstruct drm_file *file = fp->f_data;
\tstruct drm_driver *driver = file->minor->dev->driver;
\tint error;

\tif (driver->ioctl_override)
\t\terror = driver->ioctl_override(fp, cmd, data);
\telse
\t\terror = drm_ioctl(fp, cmd, data);
\tif (error == ERESTARTSYS)
\t\terror = ERESTART;

\treturn error;
}'''
    new='''static int
drm_ioctl_shim(struct file *fp, unsigned long cmd, void *data)
{
\tstruct drm_file *file = fp->f_data;
\tstruct drm_driver *driver = file->minor->dev->driver;
\tstruct task_struct *task = NULL;
\tint error;

\t/* This native file boundary is sleepable, before driver queue locks.
\t * Allocation/admission failure must not call either driver path.
\t */
\terror = linux_task_entry_enter(&task);
\tif (error != 0)
\t\treturn error;
\tif (driver->ioctl_override)
\t\terror = driver->ioctl_override(fp, cmd, data);
\telse
\t\terror = drm_ioctl(fp, cmd, data);
\tlinux_task_entry_leave(&task);
\tif (error == ERESTARTSYS)
\t\terror = ERESTART;

\treturn error;
}'''
    new_drm=once(new_drm,old,new)
    before={TASK:task,HEADER:header,DRM:drm};after={TASK:new_task,HEADER:new_header,DRM:new_drm}
    diff=''.join(''.join(difflib.unified_diff(before[p].splitlines(True),after[p].splitlines(True),
        'a/'+p,'b/'+p,n=3)) for p in before)
    metadata={'netbsd_pin':PIN,'required_prior_patches':['0032','0035'],
        'files':{p:{'before_sha256':hashlib.sha256(before[p].encode()).hexdigest(),
            'after_sha256':hashlib.sha256(after[p].encode()).hexdigest()} for p in before},
        'patch_sha256':hashlib.sha256(diff.encode()).hexdigest(),
        'scope':'Native DRM ioctl override/fallback entry and reference balance; stable per-LWP identity. Other file/workqueue/code-owner entries and MM/PID/kernel runtime remain OPEN.'}
    return diff,metadata,before,after

def main():
    p=argparse.ArgumentParser();p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--metadata',type=Path)
    a=p.parse_args();assert not a.out.exists()
    diff,metadata,_,_=generate(a.netbsd_tree);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(diff)
    if a.metadata:assert not a.metadata.exists();a.metadata.write_text(json.dumps(metadata,indent=2)+'\n')
    print('NATIVE_DRM_IOCTL_TASK_ENTRY_PATCH_GENERATED stable_lwp_identity=1')
if __name__=='__main__':main()
