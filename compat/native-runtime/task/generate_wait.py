#!/usr/bin/env python3
"""Generate isolated native callback queue code from the exact Linux pin."""
import hashlib
import os
import json
import re
import subprocess
from pathlib import Path

PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
REPO = Path(os.environ['NETBSD_RUNTIME_LINUX_TREE'])
OUT = Path(os.environ['NETBSD_RUNTIME_WAIT_OUTPUT'])
def source(path):
    return subprocess.check_output(['git', '-C', str(REPO), 'show',
                                    PIN + ':' + path], text=True)
header = source('include/linux/wait.h')
body = source('kernel/sched/wait.c')
originals = {'include/linux/wait.h':header, 'kernel/sched/wait.c':body}
names = ['default_wake_function', '__init_waitqueue_head', 'add_wait_queue',
         'add_wait_queue_exclusive', 'add_wait_queue_priority',
         'add_wait_queue_priority_exclusive', 'remove_wait_queue', '__wake_up',
         '__wake_up_on_current_cpu', '__wake_up_locked_key', '__wake_up_sync_key',
         '__wake_up_locked_sync_key', '__wake_up_locked', '__wake_up_sync',
         '__wake_up_pollfree', 'prepare_to_wait', 'prepare_to_wait_exclusive',
         'prepare_to_wait_event', 'init_wait_entry', 'do_wait_intr',
         'do_wait_intr_irq', 'finish_wait', 'autoremove_wake_function',
         'wait_woken', 'woken_wake_function', 'woken_wake_bit_function']
namespace = ''.join('#define ' + name + ' linux_' + name + '\n' for name in names)
header = header.replace('#include <asm/current.h>',
    '#include <linux/sched.h>\n\n' + namespace)
# NetBSD lock_class_key is forward-declared only; no invented lockdep object.
start = header.index('#define init_waitqueue_head(wq_head)')
end = header.index('\n#ifdef CONFIG_LOCKDEP', start)
header = header[:start] + '''#define init_waitqueue_head(wq_head) \\
    __init_waitqueue_head((wq_head), #wq_head, NULL)

/* Explicit native lifetime termination after callbacks/owners are drained. */
static inline void destroy_waitqueue_head(struct wait_queue_head *head)
{
    KASSERT(list_empty(&head->head));
    spin_lock_destroy(&head->lock);
}
''' + header[end:]
# Native kmutex has no public constant initializer. Selected C initializes
# all heads dynamically. File-scope constant initialization is an OPEN gate.
header = header.replace('__SPIN_LOCK_UNLOCKED(name.lock)',
    'NETBSD_STATIC_WAITQUEUE_NEEDS_EXPLICIT_NATIVE_INITIALIZATION')
header = header.replace('# define DECLARE_WAIT_QUEUE_HEAD_ONSTACK(name) DECLARE_WAIT_QUEUE_HEAD(name)',
    '''# define DECLARE_WAIT_QUEUE_HEAD_ONSTACK(name) \\
    struct wait_queue_head name; init_waitqueue_head(&(name))''')
header = header.replace('((void *)(__force uintptr_t)(__poll_t)(m))',
                        '((void *)(uintptr_t)(unsigned int)(m))')
header = header.replace('((__force __poll_t)(uintptr_t)(void *)(m))',
                        '((unsigned int)(uintptr_t)(void *)(m))')
# Linux intentionally shadows __ret to share the timeout predicate between
# wrapper and inner wait loops. Native -Wshadow is mandatory. Pass the budget
# explicitly, then give each wrapper's local a unique name; command fragments
# retain inner ___wait_event's __ret and all timeout/signal behavior.
header = header.replace('#define ___wait_cond_timeout(condition)',
                        '#define ___wait_cond_timeout(condition, budget)')
start = header.index('#define ___wait_cond_timeout(')
end = header.index('\n#define ___wait_is_interruptible(', start)
header = header[:start] + header[start:end].replace('__ret', 'budget') + header[end:]
header = header.replace('___wait_cond_timeout(condition)',
                        '___wait_cond_timeout(condition, __ret)')
lines = header.splitlines(keepends=True)
adapted = []
i = 0
while i < len(lines):
    match = re.match(r'#define\s+(\w+)', lines[i])
    if match is None:
        adapted.append(lines[i]); i += 1; continue
    chunk = [lines[i]]
    i += 1
    while chunk[-1].rstrip().endswith('\\') and i < len(lines):
        chunk.append(lines[i]); i += 1
    text = ''.join(chunk)
    if match.group(1) != '___wait_event' and re.search(r'\b(?:long|int)\s+__ret\b', text):
        text = re.sub(r'\b__ret\b', '__linux_' + match.group(1) + '_ret', text)
    adapted.append(text)
header = ''.join(adapted)

body = body.replace('#include "sched.h"\n#include <linux/wait_bit.h>',
    '''#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/systm.h>
#include <linux/kthread.h>
#include <linux/sched.h>
#include <linux/wait.h>

/* Callback hints retain pinned Linux values. Native migration/locality
 * behavior for these hints is a separate scheduler acceptance gate. */
#define WF_SYNC 0x10
#define WF_CURRENT_CPU 0x40''')
body = re.sub(r'^EXPORT_SYMBOL(?:_GPL)?\([^\n]*\);[^\n]*\n', '', body, flags=re.M)
body = body.replace('\tlockdep_set_class_and_name(&wq_head->lock, key, name);',
                    '\t(void)name;\n\t(void)key;')
body = body.replace('\tlockdep_assert_held(&wq_head->lock);',
                    '\tassert_spin_locked(&wq_head->lock);')
body = body.replace('\tguard(spinlock_irqsave)(&wq_head->lock);',
                    '\tunsigned long flags;\n\tspin_lock_irqsave(&wq_head->lock, flags);')
body = body.replace('''\tif (!list_empty(head) &&
\t    (list_first_entry(head, typeof(*wq_entry), entry)->flags & WQ_FLAG_PRIORITY))
\t\treturn -EBUSY;

\tlist_add(&wq_entry->entry, head);
\treturn 0;''', '''\tif (!list_empty(head) &&
\t    (list_first_entry(head, typeof(*wq_entry), entry)->flags & WQ_FLAG_PRIORITY)) {
\t\tspin_unlock_irqrestore(&wq_head->lock, flags);
\t\treturn -EBUSY;
\t}

\tlist_add(&wq_entry->entry, head);
\tspin_unlock_irqrestore(&wq_head->lock, flags);
\treturn 0;''')
assert 'guard(' not in body
# Always take the queue lock before finishing. This removes the need for
# lockless list_empty_careful/list_del_init_careful while keeping stack entry
# lifetime synchronized with every callback, including custom ones.
start = body.index('void finish_wait(')
end = body.index('\nint autoremove_wake_function(', start)
body = body[:start] + '''void finish_wait(struct wait_queue_head *wq_head,
    struct wait_queue_entry *wq_entry)
{
    unsigned long flags;
    __set_current_state(TASK_RUNNING);
    spin_lock_irqsave(&wq_head->lock, flags);
    if (!list_empty(&wq_entry->entry))
        list_del_init(&wq_entry->entry);
    spin_unlock_irqrestore(&wq_head->lock, flags);
}
''' + body[end:]
body = body.replace('list_del_init_careful(&wq_entry->entry)',
                    'list_del_init(&wq_entry->entry)')
body = body.replace('!kthread_should_stop_or_park()',
                    '!linux_wait_kthread_stop_or_park()')
# Native legacy kthread queries assert that current is a Linux kthread;
# generic tasks are allowed to use wait_woken. Private backend is stable
# throughout its owning native LWP and is released only after join.
pos = body.index('void __init_waitqueue_head(')
body = body[:pos] + '''static bool
linux_wait_kthread_stop_or_park(void)
{
    struct task_struct *task = current;
    unsigned long flags;
    bool kthread;
    raw_spin_lock_irqsave(&task->lt_lock, flags);
    kthread = task->lt_kthread != NULL;
    raw_spin_unlock_irqrestore(&task->lt_lock, flags);
    return kthread && (kthread_should_stop() || kthread_should_park());
}

''' + body[pos:]
# Poll-free key bits come from the pinned Linux poll/epoll headers. Their
# native registration/freeing and RCU owner integration remain OPEN.
body = body.replace('poll_to_key(EPOLLHUP | POLLFREE)',
                    'poll_to_key(0x0010U | 0x4000U)')
body = body.replace('\tWARN_ON_ONCE(waitqueue_active(wq_head));',
                    '\tKASSERT(!waitqueue_active(wq_head));')
# Bit callback is implemented with the separate keyed-variable table below.
start = body.index('\nint woken_wake_bit_function(')
body = body[:start]
body += '''
int default_wake_function(struct wait_queue_entry *entry,
    unsigned int mode, int flags, void *key)
{
    (void)flags;
    (void)key;
    return linux_task_wake_state(entry->private, mode);
}
'''

(OUT / 'include/linux').mkdir(parents=True, exist_ok=True)
(OUT / 'include/linux/wait.h').write_text(header)
(OUT / 'linux_wait.c').write_text(body)
manifest = {'state':'CANDIDATE_NOT_INSTALLED', 'linux_pin':PIN,
            'netbsd_pin':'03d918f6d0e81fa05b8f1160eca0628ad39988a6',
            'frozen_inputs':{p:hashlib.sha256(s.encode()).hexdigest()
                             for p,s in originals.items()},
            'files':{p:hashlib.sha256((OUT/p).read_bytes()).hexdigest() for p in
                     ('include/linux/wait.h','linux_wait.c')},
            'open':['fatal-only sleeps','static native waitqueue initializer',
                    'PID/mm/IO accounting','generic native boundary attachment',
                    'module unload/owner draining','sync/current-CPU scheduler hints',
                    'poll registrations/RCU/free lifetime','bit wait/lock/IO/timeouts']}
(OUT / 'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps(manifest, indent=2))
