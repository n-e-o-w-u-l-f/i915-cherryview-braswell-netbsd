"""F41 wrapper/API/locking source proof; no native build or model execution."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest

from test_native_task_owner_composition import code_only, function_bounds

REPOSITORY = Path(__file__).resolve().parents[1]
BASELINE = '949206aaba2ca8d91acb81db0e42f448f2700c70'
DIRECTORY = 'compat/native-runtime/task/'
WRAPPER = DIRECTORY + 'linux_task_worker_owner.c'
HEADER = DIRECTORY + 'task_worker_wake_netbsd.h'
ORIGINAL = DIRECTORY + 'linux_task.c'
DECLARATION_OWNER = 'compat/native-runtime/worker/worker_header.inc'
IMPLEMENTATION_OWNER = 'compat/native-runtime/worker/worker.inc'
HASHES = {
    ORIGINAL: '43c9aded415ce9794704c7bababc6475012365e0876fa7f3a8f493b93eff685d',
    DECLARATION_OWNER: '9f3887613605b06fad70f45bd69f92cd7015de7775a859082bbedb991a2dc1a2',
    IMPLEMENTATION_OWNER: '2ad653da9cb181aa9966e4e0e98b12c3fa0c197574f9d4f0021b9e744359001d'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def baseline_bytes(relative):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_')}
    environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
                       GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.check_output(
        ['git', '--no-replace-objects', '-C', str(REPOSITORY), 'show',
         BASELINE + ':' + relative], env=environment, timeout=30)


def body(raw, function):
    cleaned = code_only(raw.decode())
    start, end = function_bounds(cleaned, function)
    return re.sub(r'\s+', '', cleaned[start:end])


def verify_wrapper(raw):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', raw.decode(), flags=re.DOTALL)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines != ['#include "task_worker_wake_netbsd.h"', '#include "linux_task.c"']:
        raise ValueError('wrapper must declare the real API then include exactly one original owner')


def verify_header(raw):
    text = raw.decode()
    clean = code_only(text)
    if '{' in clean or clean.count('struct task_struct;') != 1:
        raise ValueError('API companion must not create a replacement layout or body')
    if re.search(r'^\s*#\s*include\b', text, re.MULTILINE):
        raise ValueError('API companion must not consume worker implementation/layout headers')
    declarations = re.findall(r'\b(int|void)\s+(linux_kthread_\w+)\(([^)]*)\)\s*;', clean)
    owner = (REPOSITORY / DECLARATION_OWNER).read_bytes()
    if digest(owner) != HASHES[DECLARATION_OWNER]:
        raise ValueError('real declaration owner identity drift')
    expected = re.findall(
        r'\b(int|void)\s+(linux_kthread_wake_locked)\(([^)]*)\)\s*;', owner.decode())
    normalize = lambda rows: [(returned, name, re.sub(r'\s+', '', parameters))
                              for returned, name, parameters in rows]
    if len(expected) != 1 or normalize(declarations) != normalize(expected):
        raise ValueError('API companion signature differs from the actual locked declaration')


def verify_locked_caller(raw):
    actual = body(raw, 'linux_wake_up_process')
    acquire = 'raw_spin_lock_irqsave(&task->lt_lock,flags);'
    locked = 'linux_kthread_wake_locked(task)'
    release = 'raw_spin_unlock_irqrestore(&task->lt_lock,flags);'
    if any(actual.count(token) != 1 for token in (acquire, locked, release)):
        raise ValueError('caller must retain exactly one real task-lock boundary and locked call')
    if not actual.index(acquire) < actual.index(locked) < actual.index(release):
        raise ValueError('worker wake escaped the caller-owned task lock')
    if 'linux_kthread_wake(task)' in actual:
        raise ValueError('unlocked wake would reacquire the already-held task lock')


def verify_locked_definition(raw):
    text = raw.decode()
    if len(re.findall(r'^int\s+linux_kthread_wake_locked\(struct task_struct \*task\)\s*\{',
                      text, re.MULTILINE)) != 1:
        raise ValueError('real locked implementation signature differs')
    actual = body(raw, 'linux_kthread_wake_locked')
    assertion = 'KASSERT(mutex_owned(&task->lt_lock.rsl_lock));'
    worker_lock = 'raw_spin_lock_irqsave(&worker->lock,flags);'
    if assertion not in actual or worker_lock not in actual:
        raise ValueError('real implementation must assert Task ownership before taking worker lock')
    if actual.index(assertion) > actual.index(worker_lock):
        raise ValueError('Task ownership assertion follows worker lock')
    if 'raw_spin_lock_irqsave(&task->lt_lock,' in actual:
        raise ValueError('locked implementation must not reacquire caller task lock')


class TaskWorkerWakeSourceTests(unittest.TestCase):
    def test_wrapper_is_regular_and_composes_api_then_one_unchanged_actual_owner(self):
        path = REPOSITORY / WRAPPER
        self.assertFalse(path.is_symlink())
        self.assertEqual(path.resolve(strict=True), path)
        verify_wrapper(path.read_bytes())
        self.assertEqual((path.parent / 'task_worker_wake_netbsd.h').resolve(strict=True),
                         REPOSITORY / HEADER)
        self.assertEqual((path.parent / 'linux_task.c').resolve(strict=True), REPOSITORY / ORIGINAL)

    def test_original_task_and_actual_worker_owners_remain_exact_git_bytes(self):
        for relative, expected in HASHES.items():
            with self.subTest(relative=relative):
                raw = (REPOSITORY / relative).read_bytes()
                self.assertEqual(digest(raw), expected)
                self.assertEqual(raw, baseline_bytes(relative))

    def test_companion_signature_matches_the_actual_worker_declaration_and_definition(self):
        verify_header((REPOSITORY / HEADER).read_bytes())
        verify_locked_definition((REPOSITORY / IMPLEMENTATION_OWNER).read_bytes())

    def test_actual_task_call_retains_its_original_task_lock_boundary(self):
        verify_locked_caller((REPOSITORY / ORIGINAL).read_bytes())

    def test_unlocked_alternative_would_take_the_same_task_lock_again(self):
        actual = body((REPOSITORY / IMPLEMENTATION_OWNER).read_bytes(), 'linux_kthread_wake')
        self.assertLess(actual.index('raw_spin_lock_irqsave(&task->lt_lock,flags);'),
                        actual.index('linux_kthread_wake_locked(task)'))
        self.assertLess(actual.index('linux_kthread_wake_locked(task)'),
                        actual.index('raw_spin_unlock_irqrestore(&task->lt_lock,flags);'))

    def test_companion_uses_opaque_real_task_tag_and_own_distinct_guard(self):
        path = REPOSITORY / HEADER
        self.assertFalse(path.is_symlink())
        self.assertEqual(path.resolve(strict=True), path)
        raw = path.read_bytes()
        verify_header(raw)
        self.assertIn(b'Caller holds task->lt_lock', raw)
        guard = re.search(rb'^#ifndef (\w+)', raw, re.MULTILINE).group(1)
        self.assertEqual(guard, b'_NB_NATIVE_TASK_WORKER_WAKE_NETBSD_H_')
        for relative in (DIRECTORY + 'task_entry_netbsd.h', DIRECTORY + 'task_netbsd.h'):
            owner_guard = re.search(rb'^#ifndef (\w+)',
                                    (REPOSITORY / relative).read_bytes(), re.MULTILINE).group(1)
            self.assertNotEqual(guard, owner_guard)

    def test_three_existing_task_fragments_are_unchanged_and_not_replaced_by_worker_body(self):
        original = (REPOSITORY / ORIGINAL).read_bytes()
        for relative in ('compat/native-entry/task_entry.inc',
                         'compat/native-file/task_entry_preallocated.inc',
                         'compat/native-file/task_quiesce_retained.inc'):
            self.assertEqual((REPOSITORY / relative).read_bytes(), baseline_bytes(relative))
        self.assertNotIn(b'worker/worker.inc', original)
        self.assertNotIn(b'worker/worker_header.inc', original)

    def test_reversed_missing_duplicate_foreign_or_code_injected_wrapper_is_rejected(self):
        good = (REPOSITORY / WRAPPER).read_bytes()
        api = b'#include "task_worker_wake_netbsd.h"\n'
        owner = b'#include "linux_task.c"\n'
        mutations = (good.replace(api + owner, owner + api), good.replace(api, b''),
                     good.replace(owner, owner + owner),
                     good.replace(owner, b'#include "../foreign/linux_task.c"\n'),
                     good + b'static int invented_owner;\n')
        for changed in mutations:
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_wrapper(changed)

    def test_wrong_signature_unlocked_substitute_missing_or_duplicate_declaration_is_rejected(self):
        good = (REPOSITORY / HEADER).read_bytes()
        declaration = b'int linux_kthread_wake_locked(struct task_struct *);'
        mutations = (good.replace(declaration, declaration.replace(b'int ', b'void ')),
                     good.replace(declaration, declaration.replace(b' *', b' **')),
                     good.replace(declaration, declaration.replace(b'wake_locked', b'wake')),
                     good.replace(declaration, b''),
                     good.replace(declaration, declaration + b'\n' + declaration),
                     good.replace(declaration, b'/* ' + declaration + b' */'))
        for changed in mutations:
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_header(changed)

    def test_callee_substitution_unlock_before_call_missing_or_duplicate_lock_is_rejected(self):
        good = (REPOSITORY / ORIGINAL).read_bytes()
        call = b'        woke |= linux_kthread_wake_locked(task);'
        unlock = b'    raw_spin_unlock_irqrestore(&task->lt_lock, flags);'
        acquire = b'    raw_spin_lock_irqsave(&task->lt_lock, flags);'
        # Modify only the real wake_up_process function, retaining surrounding source.
        start = good.index(b'int\nlinux_wake_up_process(')
        end = good.index(b'\nbool\nlinux_signal_pending(', start)
        prefix, function, suffix = good[:start], good[start:end], good[end:]
        changes = (function.replace(b'linux_kthread_wake_locked(task)', b'linux_kthread_wake(task)'),
                   function.replace(unlock, b'').replace(call, unlock + b'\n' + call),
                   function.replace(acquire, b''), function.replace(acquire, acquire + b'\n' + acquire))
        for changed in changes:
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_locked_caller(prefix + changed + suffix)

    def test_worker_lock_contract_mutations_are_rejected(self):
        good = (REPOSITORY / IMPLEMENTATION_OWNER).read_bytes()
        assertion = b'\tKASSERT(mutex_owned(&task->lt_lock.rsl_lock));'
        lock = b'\traw_spin_lock_irqsave(&worker->lock, flags);'
        for changed in (good.replace(assertion, b'', 1), good.replace(lock, b'', 1),
                        good.replace(assertion, assertion +
                                     b'\n\traw_spin_lock_irqsave(&task->lt_lock, flags);', 1)):
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_locked_definition(changed)

    def test_private_worker_include_and_replacement_layout_in_companion_are_rejected(self):
        good = (REPOSITORY / HEADER).read_bytes()
        for changed in (good + b'\n#include "../worker/worker.inc"\n',
                        good.replace(b'struct task_struct;', b'struct task_struct { int invented; };')):
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_header(changed)


if __name__ == '__main__':
    unittest.main()
