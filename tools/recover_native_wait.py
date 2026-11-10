#!/usr/bin/env python3
"""Recover only the pinned generic callback Wait sources, without executing the old recipe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

REPOSITORY = Path(__file__).resolve().parents[1]
LINUX_PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
NETBSD_PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
RECIPE_PATH = 'compat/native-runtime/task/generate_wait.py'
LEDGER_PATH = 'compat/native-runtime/task/SOURCE_SHA256.json'
RECIPE_SHA256 = '598d3de2afdf1e6c02ff8aecdde0f4a83c7f32341adbfc791b367a007df378d6'
LEDGER_SHA256 = '99b37dca5385fa243e3bad9867a36405caab52804423010690c5427193c82662'
SOURCE_IDENTITIES = {
    'include/linux/wait.h': dict(size=45202,
        sha256='f9f53a02fd25a1a1fefdc41310285975d5c1fdce1a1b62282cc05e737ae96417',
        git_blob='7e215330199cfea27008f718e0336d0f48bfe17d',
        source_url='https://github.com/torvalds/linux/blob/' + LINUX_PIN + '/include/linux/wait.h'),
    'kernel/sched/wait.c': dict(size=14840,
        sha256='05a9c8d9b1b4cb3a63e1dd59744adf24c8912d108307f46d7e3a6b1f26013e5f',
        git_blob='d033f600f48c6fc3a0a088ea5d9f6ed95ec4c86e',
        source_url='https://github.com/torvalds/linux/blob/' + LINUX_PIN + '/kernel/sched/wait.c'),
}
OUTPUT_SHA256 = {
    'include/linux/wait.h': '61ef59279676174b3394e88451ff828a83bff7c50d679b4a946d3daee45dfa86',
    'linux_wait.c': '4a933c0bb0cbf5c2483c22d8fb7a36b7166d0b52b2e30bf9223d69d9a8cd0c69',
}
NAMES = (
    'default_wake_function', '__init_waitqueue_head', 'add_wait_queue',
    'add_wait_queue_exclusive', 'add_wait_queue_priority',
    'add_wait_queue_priority_exclusive', 'remove_wait_queue', '__wake_up',
    '__wake_up_on_current_cpu', '__wake_up_locked_key', '__wake_up_sync_key',
    '__wake_up_locked_sync_key', '__wake_up_locked', '__wake_up_sync',
    '__wake_up_pollfree', 'prepare_to_wait', 'prepare_to_wait_exclusive',
    'prepare_to_wait_event', 'init_wait_entry', 'do_wait_intr',
    'do_wait_intr_irq', 'finish_wait', 'autoremove_wake_function',
    'wait_woken', 'woken_wake_function', 'woken_wake_bit_function',
)
SHADOW_RET_COUNTS = {
    'wait_event_freezable': 3, 'wait_event_timeout': 4,
    'wait_event_freezable_timeout': 4, 'wait_event_interruptible': 3,
    'wait_event_interruptible_timeout': 4, '__wait_event_hrtimeout': 4,
    'wait_event_hrtimeout': 3, 'wait_event_interruptible_hrtimeout': 3,
    'wait_event_interruptible_exclusive': 3, 'wait_event_killable_exclusive': 3,
    'wait_event_freezable_exclusive': 3, 'wait_event_idle_timeout': 4,
    'wait_event_idle_exclusive_timeout': 4, '__wait_event_interruptible_locked': 4,
    'wait_event_killable': 3, 'io_wait_event_killable': 3,
    'wait_event_state': 3, 'wait_event_state_exclusive': 3,
    'wait_event_killable_timeout': 4, 'wait_event_interruptible_lock_irq_cmd': 3,
    'wait_event_interruptible_lock_irq': 3, 'wait_event_interruptible_lock_irq_timeout': 4,
    'wait_event_lock_irq_timeout': 4,
}
OPEN_GATES = [
    'fatal-only sleeps', 'static native waitqueue initializer',
    'PID/mm/IO accounting', 'generic native boundary attachment',
    'module unload/owner draining', 'sync/current-CPU scheduler hints',
    'poll registrations/RCU/free lifetime', 'bit wait/lock/IO/timeouts',
]


class RecoveryError(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def regular_bytes(path):
    path = Path(path).absolute()
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise RecoveryError('input path is aliased: ' + str(path))
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RecoveryError('regular input required: ' + str(path))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read()
        if (identity(before) != identity(os.fstat(descriptor)) or path.is_symlink()
                or path.resolve(strict=True) != path
                or identity(before) != identity(path.stat())):
            raise RecoveryError('input changed during read: ' + str(path))
        return raw
    finally:
        os.close(descriptor)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise RecoveryError('duplicate provenance key: ' + name)
        result[name] = value
    return result


def input_provenance():
    return dict(schema=1, state='PINNED_SOURCE_INPUTS', linux_pin=LINUX_PIN,
        acquisition='exact two pinned upstream blobs; no checkout or clean-tree claim',
        files={name: dict(row) for name, row in SOURCE_IDENTITIES.items()})


def validate_raw(raw_sources):
    if set(raw_sources) != set(SOURCE_IDENTITIES):
        raise RecoveryError('exactly the two pinned generic Wait source paths are required')
    for name, expected in SOURCE_IDENTITIES.items():
        raw = raw_sources[name]
        if (not isinstance(raw, bytes) or len(raw) != expected['size']
                or sha(raw) != expected['sha256'] or git_blob(raw) != expected['git_blob']):
            raise RecoveryError('pinned raw size/SHA256/Git blob mismatch: ' + name)


def read_inputs(root):
    root = Path(root).absolute()
    if root.is_symlink() or root.resolve(strict=True) != root or not root.is_dir():
        raise RecoveryError('canonical regular input directory required')
    provenance = json.loads(regular_bytes(root / 'provenance.json'), object_pairs_hook=unique_object)
    if provenance != input_provenance():
        raise RecoveryError('input provenance pin/paths/identity differs')
    result = {name: regular_bytes(root / name) for name in SOURCE_IDENTITIES}
    validate_raw(result)
    return result


def checked_replace(text, old, new, count, label, audit):
    observed = text.count(old)
    if not old or observed != count:
        raise RecoveryError(label + ': expected ' + str(count) + ' occurrences, observed ' + str(observed))
    audit.append(dict(operation=label, kind='literal', count=observed))
    return text.replace(old, new)


def checked_regex(text, pattern, replacement, count, label, audit, flags=0):
    observed = len(re.findall(pattern, text, flags))
    if observed != count:
        raise RecoveryError(label + ': expected ' + str(count) + ' matches, observed ' + str(observed))
    audit.append(dict(operation=label, kind='regex', count=observed))
    return re.sub(pattern, replacement, text, flags=flags)


def checked_region(text, start, end, replacement, label, audit):
    if text.count(start) != 1 or text.count(end) != 1:
        raise RecoveryError(label + ': region boundaries must each be unique')
    first, last = text.index(start), text.index(end)
    if first >= last:
        raise RecoveryError(label + ': reversed region boundaries')
    audit.append(dict(operation=label, kind='region', count=1,
                      removed_sha256=sha(text[first:last].encode())))
    return text[:first] + replacement + text[last:]


def verify_output_hashes(outputs):
    if set(outputs) != set(OUTPUT_SHA256):
        raise RecoveryError('exactly the two generic recovered outputs are required')
    for name, expected in OUTPUT_SHA256.items():
        if not isinstance(outputs[name], bytes) or sha(outputs[name]) != expected:
            raise RecoveryError('historical output SHA256 mismatch: ' + name)


def transform_sources(raw_sources):
    """Checked transcription of the frozen recipe; no import/exec of that recipe."""
    validate_raw(raw_sources)
    header = raw_sources['include/linux/wait.h'].decode('utf8')
    body = raw_sources['kernel/sched/wait.c'].decode('utf8')
    audit = []
    namespace = ''.join('#define ' + name + ' linux_' + name + '\n' for name in NAMES)
    header = checked_replace(header, '#include <asm/current.h>',
        '#include <linux/sched.h>\n\n' + namespace, 1, 'header-task-namespace', audit)
    audit.append(dict(operation='namespace-identifiers', kind='named-set', count=len(NAMES)))
    dynamic = """#define init_waitqueue_head(wq_head) \\
    __init_waitqueue_head((wq_head), #wq_head, NULL)

/* Explicit native lifetime termination after callbacks/owners are drained. */
static inline void destroy_waitqueue_head(struct wait_queue_head *head)
{
    KASSERT(list_empty(&head->head));
    spin_lock_destroy(&head->lock);
}
"""
    header = checked_region(header, '#define init_waitqueue_head(wq_head)',
        '\n#ifdef CONFIG_LOCKDEP', dynamic, 'header-dynamic-native-init', audit)
    header = checked_replace(header, '__SPIN_LOCK_UNLOCKED(name.lock)',
        'NETBSD_STATIC_WAITQUEUE_NEEDS_EXPLICIT_NATIVE_INITIALIZATION', 1,
        'header-static-init-remains-open', audit)
    header = checked_replace(header,
        '# define DECLARE_WAIT_QUEUE_HEAD_ONSTACK(name) DECLARE_WAIT_QUEUE_HEAD(name)',
        """# define DECLARE_WAIT_QUEUE_HEAD_ONSTACK(name) \\
    struct wait_queue_head name; init_waitqueue_head(&(name))""",
        1, 'header-stack-init', audit)
    header = checked_replace(header, '((void *)(__force uintptr_t)(__poll_t)(m))',
        '((void *)(uintptr_t)(unsigned int)(m))', 1, 'header-poll-to-key', audit)
    header = checked_replace(header, '((__force __poll_t)(uintptr_t)(void *)(m))',
        '((unsigned int)(uintptr_t)(void *)(m))', 1, 'header-key-to-poll', audit)
    header = checked_replace(header, '#define ___wait_cond_timeout(condition)',
        '#define ___wait_cond_timeout(condition, budget)', 1, 'header-timeout-budget-parameter', audit)
    begin, end = '#define ___wait_cond_timeout(', '\n#define ___wait_is_interruptible('
    if header.count(begin) != 1 or header.count(end) != 1 or header.index(begin) >= header.index(end):
        raise RecoveryError('timeout budget region is missing, duplicated, or reversed')
    region = header[header.index(begin):header.index(end)]
    region = checked_replace(region, '__ret', 'budget', 3, 'header-timeout-budget-references', audit)
    header = checked_region(header, begin, end, region, 'header-timeout-budget-region', audit)
    header = checked_replace(header, '___wait_cond_timeout(condition)',
        '___wait_cond_timeout(condition, __ret)', 15, 'header-timeout-predicate-calls', audit)
    lines, adapted, seen = header.splitlines(keepends=True), [], []
    position = 0
    while position < len(lines):
        match = re.match(r'#define\s+(\w+)', lines[position])
        chunk = [lines[position]]
        position += 1
        if match is None:
            adapted.extend(chunk)
            continue
        while chunk[-1].rstrip().endswith('\\') and position < len(lines):
            chunk.append(lines[position])
            position += 1
        text = ''.join(chunk)
        if match.group(1) != '___wait_event' and re.search(r'\b(?:long|int)\s+__ret\b', text):
            name = match.group(1)
            if name not in SHADOW_RET_COUNTS:
                raise RecoveryError('unexpected local-shadow wrapper: ' + name)
            text = checked_regex(text, r'\b__ret\b', '__linux_' + name + '_ret',
                                 SHADOW_RET_COUNTS[name], 'shadow-wrapper:' + name, audit)
            seen.append(name)
        adapted.append(text)
    if seen != list(SHADOW_RET_COUNTS):
        raise RecoveryError('local-shadow wrapper names/order/count differ')
    audit.append(dict(operation='shadow-wrapper-set', kind='named-set', count=len(seen)))
    header = ''.join(adapted)

    body = checked_replace(body, '#include "sched.h"\n#include <linux/wait_bit.h>',
        """#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/systm.h>
#include <linux/kthread.h>
#include <linux/sched.h>
#include <linux/wait.h>

/* Callback hints retain pinned Linux values. Native migration/locality
 * behavior for these hints is a separate scheduler acceptance gate. */
#define WF_SYNC 0x10
#define WF_CURRENT_CPU 0x40""", 1, 'body-native-includes', audit)
    body = checked_regex(body, r'^EXPORT_SYMBOL(?:_GPL)?\([^\n]*\);[^\n]*\n', '',
                         23, 'body-export-removals', audit, flags=re.MULTILINE)
    body = checked_replace(body, '\tlockdep_set_class_and_name(&wq_head->lock, key, name);',
        '\t(void)name;\n\t(void)key;', 1, 'body-lockdep-class', audit)
    body = checked_replace(body, '\tlockdep_assert_held(&wq_head->lock);',
        '\tassert_spin_locked(&wq_head->lock);', 1, 'body-lockdep-assert', audit)
    body = checked_replace(body, '\tguard(spinlock_irqsave)(&wq_head->lock);',
        '\tunsigned long flags;\n\tspin_lock_irqsave(&wq_head->lock, flags);',
        1, 'body-explicit-lock', audit)
    body = checked_replace(body, """\tif (!list_empty(head) &&
\t    (list_first_entry(head, typeof(*wq_entry), entry)->flags & WQ_FLAG_PRIORITY))
\t\treturn -EBUSY;

\tlist_add(&wq_entry->entry, head);
\treturn 0;""", """\tif (!list_empty(head) &&
\t    (list_first_entry(head, typeof(*wq_entry), entry)->flags & WQ_FLAG_PRIORITY)) {
\t\tspin_unlock_irqrestore(&wq_head->lock, flags);
\t\treturn -EBUSY;
\t}

\tlist_add(&wq_entry->entry, head);
\tspin_unlock_irqrestore(&wq_head->lock, flags);
\treturn 0;""", 1, 'body-priority-error-and-success-unlock', audit)
    if 'guard(' in body:
        raise RecoveryError('unadapted native lock guard remains')
    body = checked_region(body, 'void finish_wait(', '\nint autoremove_wake_function(',
        """void finish_wait(struct wait_queue_head *wq_head,
    struct wait_queue_entry *wq_entry)
{
    unsigned long flags;
    __set_current_state(TASK_RUNNING);
    spin_lock_irqsave(&wq_head->lock, flags);
    if (!list_empty(&wq_entry->entry))
        list_del_init(&wq_entry->entry);
    spin_unlock_irqrestore(&wq_head->lock, flags);
}
""", 'body-finish-wait-always-locked', audit)
    body = checked_replace(body, 'list_del_init_careful(&wq_entry->entry)',
        'list_del_init(&wq_entry->entry)', 1, 'body-autoremove-list', audit)
    body = checked_replace(body, '!kthread_should_stop_or_park()',
        '!linux_wait_kthread_stop_or_park()', 1, 'body-generic-task-stop-predicate', audit)
    body = checked_replace(body, 'void __init_waitqueue_head(',
        """static bool
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

void __init_waitqueue_head(""", 1, 'body-generic-task-stop-helper', audit)
    body = checked_replace(body, 'poll_to_key(EPOLLHUP | POLLFREE)',
        'poll_to_key(0x0010U | 0x4000U)', 1, 'body-pollfree-key', audit)
    body = checked_replace(body, '\tWARN_ON_ONCE(waitqueue_active(wq_head));',
        '\tKASSERT(!waitqueue_active(wq_head));', 1, 'body-pollfree-assertion', audit)
    tail = '\nint woken_wake_bit_function('
    if body.count(tail) != 1:
        raise RecoveryError('separate keyed-bit callback tail is not unique')
    index = body.index(tail)
    audit.append(dict(operation='body-exclude-keyed-bit-callback', kind='tail', count=1,
                      removed_sha256=sha(body[index:].encode())))
    body = body[:index]
    body += """
int default_wake_function(struct wait_queue_entry *entry,
    unsigned int mode, int flags, void *key)
{
    (void)flags;
    (void)key;
    return linux_task_wake_state(entry->private, mode);
}
"""
    audit.append(dict(operation='body-task-owned-default-wake', kind='append', count=1))
    outputs = {'include/linux/wait.h': header.encode(), 'linux_wait.c': body.encode()}
    verify_output_hashes(outputs)
    return outputs, audit


def witness_inputs():
    recipe, ledger = regular_bytes(REPOSITORY / RECIPE_PATH), regular_bytes(REPOSITORY / LEDGER_PATH)
    if sha(recipe) != RECIPE_SHA256 or sha(ledger) != LEDGER_SHA256:
        raise RecoveryError('frozen recipe or historical ledger identity differs')
    recorded = json.loads(ledger, object_pairs_hook=unique_object)
    if any(recorded.get(name) != expected for name, expected in OUTPUT_SHA256.items()):
        raise RecoveryError('historical ledger output identities differ')
    return dict(recipe=dict(path=RECIPE_PATH, sha256=sha(recipe), git_blob=git_blob(recipe)),
                historical_ledger=dict(path=LEDGER_PATH, sha256=sha(ledger), git_blob=git_blob(ledger)))


def guard_output(inputs, output):
    inputs, output = Path(inputs).absolute(), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise RecoveryError('fresh output required; existing output is preserved')
    parent = output.parent
    if parent.resolve(strict=True) != parent or not parent.is_dir():
        raise RecoveryError('output parent must be canonical and existing')
    canonical_inputs = inputs.resolve(strict=True)
    if (inputs != canonical_inputs or output.is_relative_to(inputs)
            or inputs.is_relative_to(output)):
        raise RecoveryError('input/output overlap or alias is forbidden')
    if output.is_relative_to(REPOSITORY) and output != REPOSITORY / 'compat/native-runtime/wait-f43':
        raise RecoveryError('repository output is restricted to the isolated wait-f43 directory')
    info = parent.stat()
    if info.st_uid != os.getuid() and not (info.st_mode & stat.S_ISVTX):
        raise RecoveryError('output parent is not owned or sticky')
    return output


def snapshots(inputs):
    paths = [Path(inputs) / name for name in SOURCE_IDENTITIES]
    paths += [Path(inputs) / 'provenance.json', REPOSITORY / RECIPE_PATH, REPOSITORY / LEDGER_PATH]
    result = {}
    for path in paths:
        regular_bytes(path)
        result[str(path)] = identity(path.stat())
    return result


def _directory_identity(info):
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)


def _check_parent(parent, descriptor, admitted):
    if (parent.is_symlink() or parent.resolve(strict=True) != parent
            or _directory_identity(os.fstat(descriptor)) != admitted
            or _directory_identity(parent.stat()) != admitted):
        raise RecoveryError('admitted output parent changed or became aliased')


def _check_output(output, descriptor, parent_descriptor, admitted_parent):
    _check_parent(output.parent, parent_descriptor, admitted_parent)
    if (output.is_symlink() or output.resolve(strict=True) != output
            or _directory_identity(output.stat()) != _directory_identity(os.fstat(descriptor))):
        raise RecoveryError('private output directory changed or became aliased')


def _write_file_at(directory_fd, name, raw):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)


def recover(inputs, output):
    inputs = Path(inputs).absolute()
    output = guard_output(inputs, output)
    if (os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd
            or not hasattr(os, 'O_DIRECTORY') or not hasattr(os, 'O_NOFOLLOW')):
        raise RecoveryError('safe directory-relative output creation is unavailable')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(output.parent, flags)
    opened = []
    try:
        admitted_parent = _directory_identity(os.fstat(parent_fd))
        _check_parent(output.parent, parent_fd, admitted_parent)
        before = snapshots(inputs)
        sources, witnesses = read_inputs(inputs), witness_inputs()
        outputs, audit = transform_sources(sources)
        verify_output_hashes(outputs)
        if snapshots(inputs) != before or read_inputs(inputs) != sources or witness_inputs() != witnesses:
            raise RecoveryError('input or witness changed before output creation')
        provenance = dict(schema=1, state='RECOVERED_SOURCE_ONLY_NOT_INSTALLED',
            linux_pin=LINUX_PIN, netbsd_pin=NETBSD_PIN,
            source_mode='PINNED_UPSTREAM_BLOB_SNAPSHOTS; NO CHECKOUT/CLEAN-TREE CLAIM',
            inputs={name: dict(row) for name, row in SOURCE_IDENTITIES.items()}, witnesses=witnesses,
            recovery_tool_sha256=sha(regular_bytes(Path(__file__))),
            files={name: dict(size=len(raw), sha256=sha(raw)) for name, raw in outputs.items()},
            operations=audit, open_gates=list(OPEN_GATES),
            native_preprocessing='NOT_RUN', native_compilation='NOT_RUN',
            linked=False, installed=False, runtime='NOT_RUN')
        payloads = dict(outputs, **{
            'provenance.json': (json.dumps(provenance, indent=2) + '\n').encode('utf8')})
        _check_parent(output.parent, parent_fd, admitted_parent)
        try:
            os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as error:
            raise RecoveryError('output was created after preflight; preserved') from error
        output_fd = os.open(output.name, flags, dir_fd=parent_fd)
        opened.append(output_fd)
        _check_output(output, output_fd, parent_fd, admitted_parent)
        os.mkdir('include', mode=0o700, dir_fd=output_fd)
        include_fd = os.open('include', flags, dir_fd=output_fd)
        opened.append(include_fd)
        os.mkdir('linux', mode=0o700, dir_fd=include_fd)
        linux_fd = os.open('linux', flags, dir_fd=include_fd)
        opened.append(linux_fd)
        _write_file_at(linux_fd, 'wait.h', payloads['include/linux/wait.h'])
        _write_file_at(output_fd, 'linux_wait.c', payloads['linux_wait.c'])
        _write_file_at(output_fd, 'provenance.json', payloads['provenance.json'])
        _check_output(output, output_fd, parent_fd, admitted_parent)
        if snapshots(inputs) != before or read_inputs(inputs) != sources or witness_inputs() != witnesses:
            raise RecoveryError('input or witness changed during recovery; output preserved')
        if any(regular_bytes(output / name) != raw for name, raw in payloads.items()):
            raise RecoveryError('recovered output/provenance changed during write; preserved')
        _check_output(output, output_fd, parent_fd, admitted_parent)
        return provenance
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)
        os.close(parent_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = recover(arguments.inputs, arguments.output)
    except (RecoveryError, OSError, UnicodeError, json.JSONDecodeError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(dict(state=result['state'], files=result['files'], operations=len(result['operations']))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
