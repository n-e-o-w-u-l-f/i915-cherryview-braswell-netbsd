"""F37 source mapping/API proof; no compiler or preprocessor is invoked."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest

REPOSITORY = Path(__file__).resolve().parents[1]
BASELINE = 'e538a4679cdeab2c8d3756577f634300f1d6213d'
FILE_SOURCE = 'compat/native-file/linux_file.c'
ENTRY_HEADER = 'compat/native-file/task_entry_preallocated.h'
API_OWNER = 'compat/native-entry/task_entry.inc'
API_SHA256 = '8ea9c5916936e90ec5957f32c10fda2f0e92ec5a7a891d2d322b33d73f0cc026'
OLD_INCLUDE = b'#include <linux/task_entry_preallocated.h>\n'
NEW_INCLUDE = b'#include "task_entry_preallocated.h"\n'
DECLARATION = b'void linux_task_entry_leave(struct task_struct **);\n'
HEADER_ANCHOR = b'/* Close admission only after an object subsystem has drained; permit its\n'
HEADER_ADDITION = (b'/* Shared leave API defined by compat/native-entry/task_entry.inc. */\n'
                   + DECLARATION)
MAPPINGS = {
    'sched.h': ('../../task/sched.h', 'compat/native-runtime/task/sched.h',
                '_NB_NATIVE_RUNTIME_FORWARD_SCHED_H_'),
    'task_netbsd.h': ('../../task/task_netbsd.h', 'compat/native-runtime/task/task_netbsd.h',
                     '_NB_NATIVE_RUNTIME_FORWARD_TASK_NETBSD_H_'),
    'raw_spinlock.h': ('../../../linux/raw_spinlock.h', 'compat/linux/raw_spinlock.h',
                      '_NB_NATIVE_RUNTIME_FORWARD_RAW_SPINLOCK_H_')}


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


def expected_file_source():
    original = baseline_bytes(FILE_SOURCE)
    if digest(original) != '6875e7b65c2b61454c46d5cf68d7a706ae6b7b7d8f75763421e02bea6fcd6ac8':
        raise ValueError('original FILE source identity differs')
    if original.count(OLD_INCLUDE) != 1:
        raise ValueError('original local-include anchor differs')
    return original.replace(OLD_INCLUDE, NEW_INCLUDE)


def verify_file_source(raw):
    if raw != expected_file_source():
        raise ValueError('FILE source changed beyond the one local include')


def verify_forwarder_text(text, target, guard, owner_text):
    directives = [line.strip() for line in text.splitlines()
                  if line.lstrip().startswith('#')]
    if directives != ['#ifndef ' + guard, '#define ' + guard,
                      '#include "' + target + '"', '#endif /* ' + guard + ' */']:
        raise ValueError('forwarder target or own guard differs')
    owner_guards = re.findall(r'^#ifndef\s+(\w+)', owner_text, re.MULTILINE)
    if guard in owner_guards:
        raise ValueError('forwarder suppresses the actual owner guard')


class FileProviderMappingTests(unittest.TestCase):
    def test_file_source_preserves_every_other_byte(self):
        raw = (REPOSITORY / FILE_SOURCE).read_bytes()
        verify_file_source(raw)
        self.assertEqual(digest(raw),
                         '52ce11f4c0c5d6d786468c7c8378fbc1d6614cc2b390f418b21b414b195e2e99')
        self.assertEqual(raw.count(NEW_INCLUDE), 1)
        self.assertNotIn(OLD_INCLUDE, raw)

    def test_wrong_include_and_other_body_change_are_rejected(self):
        expected = expected_file_source()
        for raw in (expected.replace(NEW_INCLUDE, OLD_INCLUDE),
                    expected + b'/* unrelated body edit */\n'):
            with self.subTest(sha256=digest(raw)), self.assertRaises(ValueError):
                verify_file_source(raw)

    def test_local_header_adds_only_owner_derived_leave_declaration(self):
        original = baseline_bytes(ENTRY_HEADER)
        self.assertEqual(digest(original),
                         'cbced0095ccad379128037a66bc154659fae78be1180e2d49778abca93f5be1b')
        self.assertEqual(original.count(HEADER_ANCHOR), 1)
        actual = (REPOSITORY / ENTRY_HEADER).read_bytes()
        self.assertEqual(actual, original.replace(HEADER_ANCHOR,
                                                 HEADER_ADDITION + HEADER_ANCHOR))
        self.assertEqual(actual.count(DECLARATION), 1)

    def test_leave_signature_is_derived_from_the_actual_permitted_definition(self):
        owner = (REPOSITORY / API_OWNER).read_bytes()
        self.assertEqual(digest(owner), API_SHA256)
        self.assertEqual(owner, baseline_bytes(API_OWNER))
        self.assertEqual(len(re.findall(
            rb'\bvoid\s+linux_task_entry_leave\(struct task_struct \*\*handle\)\s*\{',
            owner)), 1)
        self.assertIn(DECLARATION, (REPOSITORY / ENTRY_HEADER).read_bytes())
        source = (REPOSITORY / FILE_SOURCE).read_bytes()
        self.assertIn(b'struct task_struct *entry = NULL;', source)
        self.assertIn(b'linux_task_entry_leave(&entry);', source)

    def test_forwarders_are_regular_files_to_exact_separately_owned_headers(self):
        for name, (target, owner, guard) in MAPPINGS.items():
            with self.subTest(name=name):
                path = REPOSITORY / 'compat/native-runtime/include/linux' / name
                expected = REPOSITORY / owner
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.is_file())
                self.assertEqual(path.resolve(strict=True), path)
                self.assertFalse(expected.is_symlink())
                self.assertTrue(expected.is_file())
                self.assertEqual((path.parent / target).resolve(strict=True), expected)
                self.assertEqual(expected.read_bytes(), baseline_bytes(owner))
                verify_forwarder_text(path.read_text(), target, guard, expected.read_text())

    def test_wrong_target_and_actual_owner_guard_are_rejected(self):
        for name, (target, owner, guard) in MAPPINGS.items():
            path = REPOSITORY / 'compat/native-runtime/include/linux' / name
            text = path.read_text()
            actual_owner = (REPOSITORY / owner).read_text()
            with self.subTest(name=name, kind='target'), self.assertRaises(ValueError):
                verify_forwarder_text(text.replace(target, '../../../foreign.h'),
                                      target, guard, actual_owner)
            owner_guard = re.search(r'^#ifndef\s+(\w+)', actual_owner, re.MULTILINE)
            self.assertIsNotNone(owner_guard)
            with self.subTest(name=name, kind='guard'), self.assertRaises(ValueError):
                verify_forwarder_text(text.replace(guard, owner_guard.group(1)),
                                      target, guard, actual_owner)

    def test_task_internal_includes_resolve_through_the_same_narrow_mapping(self):
        scheduler = (REPOSITORY / MAPPINGS['sched.h'][1]).read_bytes()
        task = (REPOSITORY / MAPPINGS['task_netbsd.h'][1]).read_bytes()
        self.assertIn(b'#include <linux/task_netbsd.h>', scheduler)
        self.assertIn(b'#include <linux/raw_spinlock.h>', task)
        root = REPOSITORY / 'compat/native-runtime/include'
        self.assertTrue((root / 'linux/task_netbsd.h').is_file())
        self.assertTrue((root / 'linux/raw_spinlock.h').is_file())
        self.assertEqual(set(path.name for path in (root / 'linux').iterdir()),
                         set(MAPPINGS))

    def test_actual_task_raw_spin_and_api_owners_remain_unmodified(self):
        for relative in [row[1] for row in MAPPINGS.values()] + [API_OWNER]:
            with self.subTest(relative=relative):
                self.assertEqual((REPOSITORY / relative).read_bytes(),
                                 baseline_bytes(relative))


if __name__ == '__main__':
    unittest.main()
