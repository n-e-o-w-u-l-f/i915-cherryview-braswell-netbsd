"""F39 same-owner source composition proof; no native compiler/preprocessor is invoked."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest

REPOSITORY = Path(__file__).resolve().parents[1]
BASELINE = 'e2c48bfa52b5fcfd1dbeab52dbb9ca749b94b2dc'
TASK = 'compat/native-runtime/task/linux_task.c'
HEADER = 'compat/native-runtime/task/task_entry_netbsd.h'
ORIGINAL_SHA256 = 'd434fcaa9dea2e01d52b44605c3b2eedf9045550b1ff9c572c19e85eb0600ee4'
HEADER_INCLUDE = b'#include "task_entry_netbsd.h"\n'
ANCHOR = b'struct task_struct *\nlinux_task_enter_current(void)\n'
FRAGMENTS = (
    ('../../native-entry/task_entry.inc', 'compat/native-entry/task_entry.inc',
     '8ea9c5916936e90ec5957f32c10fda2f0e92ec5a7a891d2d322b33d73f0cc026'),
    ('../../native-file/task_entry_preallocated.inc', 'compat/native-file/task_entry_preallocated.inc',
     '41f1a9451d7f299f0a3aa124f070718ee9ece3ef80cf34671c33f708a5475fd6'),
    ('../../native-file/task_quiesce_retained.inc', 'compat/native-file/task_quiesce_retained.inc',
     '7f7b60dd20794d5999888a702f9faa2a7a725337f3da1ab54fa0ecc81037ae90'))
ADDITION = (b'/* Entry/lifecycle fragments share this actual Task owner and its static resources. */\n'
            + b''.join(('#include "' + relative + '"\n').encode()
                       for relative, _, _ in FRAGMENTS) + b'\n')
APIS = ('linux_task_entry_enter', 'linux_task_entry_leave',
        'linux_task_entry_enter_preallocated', 'linux_task_system_quiesce_retained')


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


def expected_source():
    original = baseline_bytes(TASK)
    if digest(original) != ORIGINAL_SHA256 or original.count(ANCHOR) != 1:
        raise ValueError('original Task source identity/anchor differs')
    scheduler = b'#include <linux/sched.h>\n'
    if original.count(scheduler) != 1:
        raise ValueError('original scheduler include differs')
    return original.replace(scheduler, scheduler + HEADER_INCLUDE).replace(
        ANCHOR, ADDITION + ANCHOR)


def verify_source_preservation(raw):
    if raw != expected_source():
        raise ValueError('original Task bodies changed beyond the two reviewed additions')


def code_only(text):
    tokens = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(tokens, lambda match: ' ' * len(match.group()), text, flags=re.DOTALL)


def function_bounds(clean, name):
    match = re.search(r'\b' + name + r'\([^)]*\)\s*\{', clean)
    if match is None:
        raise ValueError('real helper definition missing: ' + name)
    start = clean.index('{', match.start())
    depth = 1
    for position in range(start + 1, len(clean)):
        depth += (clean[position] == '{') - (clean[position] == '}')
        if depth == 0:
            return match.start(), position + 1
    raise ValueError('unterminated helper: ' + name)


def verify_composition(raw):
    text = raw.decode()
    if raw.count(HEADER_INCLUDE) != 1:
        raise ValueError('exact quote-local entry header required')
    included = re.findall(r'^#include "([^"]+\.inc)"$', text, re.MULTILINE)
    if included != [row[0] for row in FRAGMENTS]:
        raise ValueError('fragment paths/order/count differ')
    clean = code_only(text)
    end = max(function_bounds(clean, name)[1] for name in (
        'linux_task_reserve', 'linux_task_unreserve', 'linux_task_alloc_reserved',
        'linux_task_alloc', 'linux_task_attach_current'))
    boundary = function_bounds(clean, 'linux_task_enter_current')[0]
    for relative, _, _ in FRAGMENTS:
        position = text.index('#include "' + relative + '"')
        if not end < position < boundary:
            raise ValueError('fragment precedes required primitives or follows next owner')
        prefix = clean[:position]
        if prefix.count('{') != prefix.count('}'):
            raise ValueError('fragment is inside a function instead of the same owner scope')
    if len(re.findall(r'\bstatic\s+specificdata_key_t\s+task_key\b', clean)) != 1:
        raise ValueError('task key owner duplicated')
    if re.search(r'\bstruct\s+task_struct\s*\{', clean):
        raise ValueError('replacement task layout is forbidden')


def parameters(text):
    result = []
    for parameter in text.split(','):
        value = parameter.strip()
        value = re.sub(r'(?<=\*)[A-Za-z_]\w*$', '', value)
        result.append(re.sub(r'\s+', '', value))
    return tuple(result)


def owned_signatures():
    result = {}
    for _, relative, expected in FRAGMENTS:
        raw = (REPOSITORY / relative).read_bytes()
        if digest(raw) != expected:
            raise ValueError('actual fragment body changed: ' + relative)
        text = raw.decode()
        for returned, name, arguments in re.findall(
                r'^(int|void)\s+(' + '|'.join(APIS) + r')\(([^)]*)\)\s*\{',
                text, re.MULTILINE):
            if name in result:
                raise ValueError('duplicate actual API definition')
            result[name] = (returned, parameters(arguments))
    if set(result) != set(APIS):
        raise ValueError('actual four-API owner set differs')
    return result


def verify_header(raw):
    text = raw.decode()
    if text.count('struct task_struct;') != 1 or '{' in code_only(text):
        raise ValueError('entry header must forward-declare the actual task type only')
    found = {}
    for returned, name, arguments in re.findall(
            r'\b(int|void)\s+(' + '|'.join(APIS) + r')\(([^)]*)\)\s*;', text):
        if name in found:
            raise ValueError('duplicate public API declaration')
        found[name] = (returned, parameters(arguments))
    if found != owned_signatures():
        raise ValueError('public declarations differ from the actual fragment definitions')


class TaskOwnerCompositionTests(unittest.TestCase):
    def test_actual_task_source_has_only_the_two_reviewed_additions(self):
        actual = (REPOSITORY / TASK).read_bytes()
        verify_source_preservation(actual)
        self.assertEqual(actual, expected_source())
        self.assertEqual(digest(actual),
                         '43c9aded415ce9794704c7bababc6475012365e0876fa7f3a8f493b93eff685d')

    def test_three_fragments_share_the_existing_top_level_owner_after_all_primitives(self):
        verify_composition((REPOSITORY / TASK).read_bytes())

    def test_all_fragment_paths_are_regular_exact_and_bodies_remain_byte_identical(self):
        parent = (REPOSITORY / TASK).parent
        for included, relative, expected in FRAGMENTS:
            path = REPOSITORY / relative
            with self.subTest(path=relative):
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.is_file())
                self.assertEqual((parent / included).resolve(strict=True), path)
                self.assertEqual(digest(path.read_bytes()), expected)
                self.assertEqual(path.read_bytes(), baseline_bytes(relative))

    def test_companion_header_declares_exact_four_real_owner_signatures(self):
        path = REPOSITORY / HEADER
        self.assertFalse(path.is_symlink())
        self.assertEqual(path.resolve(strict=True), path)
        self.assertEqual((REPOSITORY / TASK).parent / 'task_entry_netbsd.h', path)
        verify_header(path.read_bytes())

    def test_companion_is_compatible_with_existing_file_entry_declarations(self):
        actual = (REPOSITORY / HEADER).read_text()
        file_header = (REPOSITORY / 'compat/native-file/task_entry_preallocated.h').read_text()
        for signature in (
                'void linux_task_entry_leave(struct task_struct **);',
                'int linux_task_system_quiesce_retained(struct task_struct *);'):
            self.assertIn(signature, actual)
            self.assertIn(signature, file_header)
        self.assertEqual((REPOSITORY / 'compat/native-runtime/task/task_netbsd.h').read_bytes(),
                         baseline_bytes('compat/native-runtime/task/task_netbsd.h'))

    def test_duplicate_wrong_target_and_missing_fragment_mutations_are_rejected(self):
        actual = expected_source()
        first = ('#include "' + FRAGMENTS[0][0] + '"\n').encode()
        for changed in (actual.replace(first, first + first),
                        actual.replace(first, b'#include "../../foreign/entry.inc"\n'),
                        actual.replace(first, b'')):
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_composition(changed)

    def test_premature_and_inside_function_fragment_placement_are_rejected(self):
        actual = expected_source()
        stripped = actual.replace(ADDITION, b'')
        before = stripped.replace(b'static specificdata_key_t task_key',
                                  ADDITION + b'static specificdata_key_t task_key')
        attach = b'linux_task_attach_current(struct task_struct *task)\n{\n'
        inside = stripped.replace(attach, attach + ADDITION)
        for changed in (before, inside):
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_composition(changed)

    def test_wrong_return_pointer_depth_duplicate_and_missing_api_are_rejected(self):
        header = (REPOSITORY / HEADER).read_bytes()
        leave = b'void linux_task_entry_leave(struct task_struct **);'
        for changed in (header.replace(leave, leave.replace(b'void', b'int')),
                        header.replace(leave, leave.replace(b'**', b'*')),
                        header.replace(leave, leave + b'\n' + leave),
                        header.replace(leave, b'')):
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_header(changed)

    def test_second_task_key_and_replacement_task_layout_are_rejected(self):
        actual = expected_source()
        for changed in (actual + b'\nstatic specificdata_key_t task_key;\n',
                        actual + b'\nstruct task_struct { int invented; };\n'):
            with self.subTest(sha=digest(changed)), self.assertRaises(ValueError):
                verify_composition(changed)

    def test_original_function_body_mutation_is_detected_by_result_bytes(self):
        actual = expected_source()
        changed = actual.replace(b'task_system_state = TASK_SYSTEM_OPEN;',
                                 b'task_system_state = TASK_SYSTEM_QUIESCED;')
        self.assertNotEqual(changed, actual)
        with self.assertRaisesRegex(ValueError, 'original Task bodies changed'):
            verify_source_preservation(changed)


if __name__ == '__main__':
    unittest.main()
