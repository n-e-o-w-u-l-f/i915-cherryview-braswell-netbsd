#!/usr/bin/env python3
"""Exact0032/0035/0037 task owner -> one real native notifier workqueue.

Source processing only. Does not build, stage a kernel, or modify old assets.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TASK = 'sys/external/bsd/drm2/linux/linux_task.c'
HEADER = 'sys/external/bsd/drm2/include/linux/task_netbsd.h'
BEFORE = {TASK: '375113319b162867a34263bb8fa642f5e4e1d09a71d9329e9d82e6ed5a9b8a1c',
          HEADER: 'e6aca23639d618eb2f49b808c856ac55b0b0d9954406964b18e63f5d4cd5df0b'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('non-unique source anchor: ' + old[:100])
    return text.replace(old, new)


def sources():
    with tempfile.TemporaryDirectory(prefix='task-notifier-source-') as name:
        temp = Path(name)
        for path, asset in ((TASK, 'linux_task.c'), (HEADER, 'task_netbsd.h')):
            target = temp / path
            target.parent.mkdir(parents=True, exist_ok=True)
            # Canonical Git text is LF; Windows checkout CRLF is the only
            # admitted normalization. The resulting exact0037 hash is fixed.
            data = (ROOT / 'compat/native-runtime/task' / asset).read_bytes()
            target.write_bytes(data.replace(b'\r\n', b'\n'))
        for patch in ('compat/native-fatal/task-runtime.patch',
                      'patches/0037-netbsd-linux-drm-ioctl-task-entry.patch'):
            patch_data = (ROOT / patch).read_bytes().replace(b'\r\n', b'\n')
            subprocess.run(['git', '-c', 'core.autocrlf=false', '-C', str(temp), 'apply', '--include=' + TASK,
                            '--include=' + HEADER, '-'], input=patch_data, check=True)
        before = {p: (temp / p).read_bytes().replace(b'\r\n', b'\n') for p in BEFORE}
    for path, data in before.items():
        if sha(data) != BEFORE[path]:
            raise ValueError('frozen0037 mismatch: ' + path)
    task, header = before[TASK].decode(), before[HEADER].decode()
    task = once(task, '#include <sys/systm.h>\n',
                '#include <sys/systm.h>\n#include <sys/workqueue.h>\n')
    start = task.index('/* Per-task notifier:')
    end = task.index('static void\nlinux_task_owner_exit', start)
    task = task[:start] + (HERE / 'notifier.inc').read_text() + '\n' + task[end:]
    task = once(task, '    linux_task_system_resume();\n    return 0;\n', '''    error = workqueue_create(&task_notify_queue, "lnxtask", linux_task_notify,
        NULL, PRI_NONE, IPL_HIGH, WQ_MPSAFE);
    if (error != 0) {
        lwp_specific_key_delete(task_key);
        task_key = (specificdata_key_t)-1;
        raw_spin_lock_destroy(&task_system_lock);
        return error;
    }
    linux_task_system_resume();
    return 0;
''')
    task = once(task, '    KASSERT(task_key != (specificdata_key_t)-1);\n    task_system_state = TASK_SYSTEM_OPEN;',
                '    KASSERT(task_key != (specificdata_key_t)-1);\n'
                '    KASSERT(task_notify_queue != NULL);\n    task_system_state = TASK_SYSTEM_OPEN;')
    task = once(task, '''linux_task_system_fini(void)
{
    int error;

    error = linux_task_system_quiesce();''', '''linux_task_system_fini(void)
{
    unsigned long flags;
    bool closed;
    int error;

    ASSERT_SLEEPABLE();
    /* Teardown is externally serialized. If a subsystem has already closed
     * admission (retained native worker exit), drain its queued final put
     * before checking zero reservations. Wait outside task/system locks and
     * outside any code-owner lock needed by worker/owner rundown. */
    raw_spin_lock_irqsave(&task_system_lock, flags);
    closed = task_system_state == TASK_SYSTEM_QUIESCED;
    if (closed)
        workqueue_enqueue(task_notify_queue, &task_notify_barrier, NULL);
    raw_spin_unlock_irqrestore(&task_system_lock, flags);
    if (closed)
        workqueue_wait(task_notify_queue, &task_notify_barrier);
    error = linux_task_system_quiesce();''')
    task = once(task, '    lwp_specific_key_delete(task_key);\n    task_key = (specificdata_key_t)-1;',
                '    /* Zero charged tasks means no pending task work; join the\n'
                '     * possibly returning final callback before resource/code teardown. */\n'
                '    workqueue_destroy(task_notify_queue);\n    task_notify_queue = NULL;\n'
                '    lwp_specific_key_delete(task_key);\n    task_key = (specificdata_key_t)-1;')
    start = task.index('    task->lt_softint = softint_establish(')
    end = task.index('    return task;', start)
    task = task[:start] + task[end:]
    task = once(task, 'void\nlinux_task_attach_current(struct task_struct *task)',
                (HERE / 'owner_wait.inc').read_text() + '\nvoid\nlinux_task_attach_current(struct task_struct *task)')
    start = task.index('void\nlinux_put_task_struct(struct task_struct *task)')
    end = task.index('struct lwp *\nlinux_task_lwp', start)
    task = task[:start] + '''void
linux_put_task_struct(struct task_struct *task)
{
    unsigned long flags;

    raw_spin_lock_irqsave(&task->lt_lock, flags);
    if (task->lt_refs == 0)
        panic("linux_put_task_struct: reference underflow");
    if (--task->lt_refs == 0) {
        KASSERT(task->lt_lwp == NULL && task->lt_kthread == NULL);
        /* Last put may run under IRQ/RCU locks: no allocation, sleep or free.
         * The same embedded work coalesces wake and final destruction. */
        linux_task_notify_locked(task);
    }
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
}

''' + task[end:]
    task = task.replace('softint_schedule(task->lt_softint);', 'linux_task_notify_locked(task);')
    if 'softint_' in task or 'lt_softint' in task:
        raise ValueError('unconverted softint owner')
    header = once(header, '#include <sys/lwp.h>\n',
                  '#include <sys/lwp.h>\n#include <sys/workqueue.h>\n')
    header = once(header, '    void *lt_softint;', '''    struct work lt_notify_work;
    /* Both flags protected by lt_lock. Pending includes a running callback. */
    bool lt_notify_pending;
    bool lt_notify_again;''')
    header = once(header, 'struct task_struct *linux_task_alloc(void);',
                  'struct task_struct *linux_task_alloc(void);\n'
                  '/* Sleepable internal owner clone; caller retains an exclusive,\n'
                  ' * never-attached parent spare, including while admission is closed. */\n'
                  'struct task_struct *linux_task_alloc_owner_wait(struct task_struct *);')
    after = {TASK: task.encode(), HEADER: header.encode()}
    diff = ''.join(''.join(difflib.unified_diff(before[p].decode().splitlines(True),
                    after[p].decode().splitlines(True), 'a/' + p, 'b/' + p)) for p in BEFORE)
    metadata = {
        'required_prior_patches': ['0032', '0035', '0037'],
        'files': {p: {'before_sha256': sha(before[p]), 'after_sha256': sha(after[p])} for p in BEFORE},
        'patch_sha256': sha(diff.encode()),
        'assets_sha256': {n: sha((HERE / n).read_bytes().replace(b'\r\n', b'\n'))
                          for n in ('generate.py', 'notifier.inc', 'owner_wait.inc')},
        'scope': 'One fallible native workqueue at init; embedded coalesced work, deferred final task destruction, retained-parent internal allocation. Native ABI/lifecycle and module/code-owner teardown require independent native validation.'}
    return before, after, diff, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('output must be new')
    _, after, patch, metadata = sources()
    args.output.mkdir(parents=True)
    for path, data in after.items():
        target = args.output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (args.output / 'task-notifier.patch').write_bytes(patch.encode())
    (args.output / 'expected-source.json').write_bytes((json.dumps(metadata, indent=2) + '\n').encode())
    print('TASK_NOTIFIER_SOURCE_GENERATED native_acceptance=OPEN')


if __name__ == '__main__':
    main()
