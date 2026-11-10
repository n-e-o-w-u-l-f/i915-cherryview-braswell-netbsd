"""F43 guarded recovery tests using only private fixtures and the new producer.

No old generator, native preprocessor/compiler, network access, or production
recovered output is invoked. The source author runs this with the old 163 tests.
"""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / 'tools'))
import recover_native_wait as recovery

RAW_ROOT = REPOSITORY / 'compat/native-runtime/wait-inputs-f43'
EXPECTED_OUTPUTS = {
    'include/linux/wait.h': '61ef59279676174b3394e88451ff828a83bff7c50d679b4a946d3daee45dfa86',
    'linux_wait.c': '4a933c0bb0cbf5c2483c22d8fb7a36b7166d0b52b2e30bf9223d69d9a8cd0c69',
}
EXPECTED_PAYLOADS = set(EXPECTED_OUTPUTS) | {'provenance.json'}


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class WaitRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='f43-wait-recovery-test-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.inputs = self.base / 'inputs'
        self.repository = self.base / 'witness-repository'
        self.inputs.mkdir()
        self.repository.mkdir()
        self.raw = {}
        for name in recovery.SOURCE_IDENTITIES:
            raw = (RAW_ROOT / name).read_bytes()
            self.raw[name] = raw
            save(self.inputs / name, raw)
        self.write_provenance(copy.deepcopy(recovery.input_provenance()))
        self.recipe = save(self.repository / recovery.RECIPE_PATH,
                           (REPOSITORY / recovery.RECIPE_PATH).read_bytes())
        self.ledger = save(self.repository / recovery.LEDGER_PATH,
                           (REPOSITORY / recovery.LEDGER_PATH).read_bytes())
        self.output = self.base / 'recovered'
        patcher = mock.patch.object(recovery, 'REPOSITORY', self.repository)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_provenance(self, document):
        (self.inputs / 'provenance.json').write_text(json.dumps(document, indent=2) + '\n')

    def source_bytes(self):
        paths = [self.inputs / name for name in recovery.SOURCE_IDENTITIES]
        paths += [self.inputs / 'provenance.json', self.recipe, self.ledger]
        return {str(path): path.read_bytes() for path in paths}

    def payload_files(self, directory):
        return {path.relative_to(directory).as_posix(): path.read_bytes()
                for path in directory.rglob('*') if path.is_file()}

    def test_exact_pinned_raw_blob_sha_size_and_historical_output_identities(self):
        self.assertEqual(recovery.LINUX_PIN, 'fd179f8a05be3ccae366b9b96e176b51fbe54aab')
        self.assertEqual(recovery.NETBSD_PIN, '03d918f6d0e81fa05b8f1160eca0628ad39988a6')
        expected = {
            'include/linux/wait.h': (45202, 'f9f53a02fd25a1a1fefdc41310285975d5c1fdce1a1b62282cc05e737ae96417',
                                     '7e215330199cfea27008f718e0336d0f48bfe17d'),
            'kernel/sched/wait.c': (14840, '05a9c8d9b1b4cb3a63e1dd59744adf24c8912d108307f46d7e3a6b1f26013e5f',
                                    'd033f600f48c6fc3a0a088ea5d9f6ed95ec4c86e')}
        self.assertEqual(set(recovery.SOURCE_IDENTITIES), set(expected))
        for name, (size, digest, blob) in expected.items():
            row = recovery.SOURCE_IDENTITIES[name]
            raw = self.raw[name]
            with self.subTest(name=name):
                self.assertEqual((row['size'], row['sha256'], row['git_blob']), (size, digest, blob))
                self.assertEqual(len(raw), size)
                self.assertEqual(sha(raw), digest)
                self.assertEqual(recovery.git_blob(raw), blob)
                self.assertEqual(row['source_url'],
                    'https://github.com/torvalds/linux/blob/' + recovery.LINUX_PIN + '/' + name)
        self.assertEqual(recovery.OUTPUT_SHA256, EXPECTED_OUTPUTS)

    def test_read_inputs_accepts_only_real_fixture_bytes_and_does_not_use_environment(self):
        with mock.patch.dict(os.environ, NETBSD_RUNTIME_LINUX_TREE='/forbidden-checkout',
                             NETBSD_RUNTIME_WAIT_OUTPUT='/forbidden-output'):
            self.assertEqual(recovery.read_inputs(self.inputs), self.raw)

    def test_input_provenance_returns_independent_metadata_rows(self):
        original = copy.deepcopy(recovery.SOURCE_IDENTITIES)
        with mock.patch.object(recovery, 'SOURCE_IDENTITIES', copy.deepcopy(original)):
            document = recovery.input_provenance()
            name = next(iter(original))
            document['files'][name]['size'] = 0
            document['files'][name]['source_url'] = 'https://example.invalid/changed'
            self.assertEqual(recovery.SOURCE_IDENTITIES, original)
            self.assertEqual(recovery.input_provenance()['files'], original)

    def test_validate_raw_rejects_missing_extra_and_nonbyte_sources(self):
        missing = dict(self.raw)
        missing.pop('include/linux/wait.h')
        extra = dict(self.raw, unrelated=b'not a reviewed source')
        wrong_type = dict(self.raw)
        wrong_type['include/linux/wait.h'] = wrong_type['include/linux/wait.h'].decode()
        for document in (missing, extra, wrong_type):
            with self.subTest(paths=list(document)), self.assertRaises(recovery.RecoveryError):
                recovery.validate_raw(document)

    def test_size_sha_and_git_blob_checks_are_independently_required(self):
        name = 'include/linux/wait.h'
        for field, wrong in (('size', 45203), ('sha256', '0' * 64), ('git_blob', '0' * 40)):
            identities = copy.deepcopy(recovery.SOURCE_IDENTITIES)
            identities[name][field] = wrong
            with self.subTest(field=field), mock.patch.object(recovery, 'SOURCE_IDENTITIES', identities):
                with self.assertRaisesRegex(recovery.RecoveryError, 'size/SHA256/Git blob mismatch'):
                    recovery.validate_raw(self.raw)

    def test_changed_truncated_and_appended_raw_bytes_are_rejected(self):
        path = self.inputs / 'include/linux/wait.h'
        original = path.read_bytes()
        for changed in (b'X' + original[1:], original[:-1], original + b'\n'):
            path.write_bytes(changed)
            with self.subTest(size=len(changed)), self.assertRaisesRegex(
                    recovery.RecoveryError, 'pinned raw size/SHA256/Git blob mismatch'):
                recovery.read_inputs(self.inputs)
        path.write_bytes(original)

    def test_provenance_pin_path_url_size_and_blob_mutations_are_rejected(self):
        original = copy.deepcopy(recovery.input_provenance())
        mutations = (
            lambda d: d.update(linux_pin='0' * 40),
            lambda d: d.update(acquisition='claimed clean checkout'),
            lambda d: d['files']['include/linux/wait.h'].update(source_url='https://example.invalid'),
            lambda d: d['files']['include/linux/wait.h'].update(size=1),
            lambda d: d['files']['include/linux/wait.h'].update(git_blob='0' * 40),
            lambda d: d['files'].update({'../foreign.h': d['files'].pop('include/linux/wait.h')}))
        for index, mutate in enumerate(mutations):
            changed = copy.deepcopy(original)
            mutate(changed)
            self.write_provenance(changed)
            with self.subTest(index=index), self.assertRaisesRegex(
                    recovery.RecoveryError, 'input provenance pin/paths/identity differs'):
                recovery.read_inputs(self.inputs)
        self.write_provenance(original)

    def test_duplicate_provenance_keys_cannot_hide_the_real_pin(self):
        raw = (self.inputs / 'provenance.json').read_text()
        self.assertEqual(raw.count('"schema": 1'), 1)
        (self.inputs / 'provenance.json').write_text(raw.replace('"schema": 1', '"schema": 1, "schema": 1'))
        with self.assertRaisesRegex(recovery.RecoveryError, 'duplicate provenance key'):
            recovery.read_inputs(self.inputs)

    def test_raw_and_provenance_symlinks_are_rejected_even_for_identical_bytes(self):
        for name in ('include/linux/wait.h', 'provenance.json'):
            path = self.inputs / name
            original = path.read_bytes()
            target = save(self.base / ('same-' + path.name), original)
            path.unlink()
            path.symlink_to(target)
            with self.subTest(name=name), self.assertRaisesRegex(recovery.RecoveryError, 'aliased'):
                recovery.read_inputs(self.inputs)
            path.unlink()
            path.write_bytes(original)

    def test_input_directory_and_parent_aliases_are_rejected(self):
        direct = self.base / 'input-alias'
        direct.symlink_to(self.inputs, target_is_directory=True)
        parent = self.base / 'parent-alias'
        parent.symlink_to(self.base, target_is_directory=True)
        for path in (direct, parent / self.inputs.name):
            with self.subTest(path=path), self.assertRaisesRegex(
                    recovery.RecoveryError, 'canonical regular input directory'):
                recovery.read_inputs(path)

    def test_missing_input_does_not_create_output(self):
        (self.inputs / 'kernel/sched/wait.c').unlink()
        with self.assertRaises(OSError):
            recovery.recover(self.inputs, self.output)
        self.assertFalse(self.output.exists())

    def test_regular_read_rejects_same_inode_parent_alias_created_during_read(self):
        parent = self.base / 'stable-parent'
        path = save(parent / 'source', b'actual source bytes')
        inode = path.stat().st_ino
        moved = self.base / 'moved-parent'
        original_fdopen = recovery.os.fdopen
        swapped = []

        @contextlib.contextmanager
        def swapping_fdopen(descriptor, *args, **kwargs):
            with original_fdopen(descriptor, *args, **kwargs) as stream:
                class Reader:
                    def read(inner):
                        raw = stream.read()
                        parent.rename(moved)
                        parent.symlink_to(moved, target_is_directory=True)
                        swapped.append(True)
                        return raw
                yield Reader()

        with mock.patch.object(recovery.os, 'fdopen', side_effect=swapping_fdopen):
            with self.assertRaisesRegex(recovery.RecoveryError, 'input changed during read'):
                recovery.regular_bytes(path)
        self.assertEqual(swapped, [True])
        self.assertEqual(path.stat().st_ino, inode)
        self.assertEqual(path.resolve(), moved / 'source')

    def test_transform_produces_exact_history_and_expected_named_audit(self):
        before = copy.deepcopy(self.raw)
        outputs, audit = recovery.transform_sources(self.raw)
        self.assertEqual({name: sha(raw) for name, raw in outputs.items()}, EXPECTED_OUTPUTS)
        self.assertEqual(self.raw, before)
        operations = {row['operation']: row for row in audit}
        self.assertEqual(len(audit), 49)
        self.assertEqual(len(operations), len(audit))
        for label, count in (('namespace-identifiers', 26), ('shadow-wrapper-set', 23),
                             ('body-export-removals', 23), ('header-timeout-predicate-calls', 15),
                             ('header-timeout-budget-references', 3)):
            self.assertEqual(operations[label]['count'], count)
        shadow = [row for row in audit if row['operation'].startswith('shadow-wrapper:')]
        self.assertEqual(len(shadow), 23)
        self.assertNotIn(b'\nint woken_wake_bit_function(', outputs['linux_wait.c'])
        self.assertIn(b'linux_task_wake_state(entry->private, mode)', outputs['linux_wait.c'])

    def test_comment_decoy_or_original_anchor_replacement_cannot_bypass_raw_identity(self):
        name = 'include/linux/wait.h'
        original = self.raw[name]
        for changed in (original.replace(b'#include <asm/current.h>',
                                         b'/* #include <asm/current.h> */'),
                        original + b'\n/* fd179 source decoy */\n'):
            document = dict(self.raw)
            document[name] = changed
            with self.subTest(sha=sha(changed)), self.assertRaisesRegex(
                    recovery.RecoveryError, 'pinned raw size/SHA256/Git blob mismatch'):
                recovery.transform_sources(document)

    def test_checked_literal_replacement_has_positive_and_missing_duplicate_controls(self):
        audit = []
        self.assertEqual(recovery.checked_replace('a anchor z', 'anchor', 'actual', 1,
                                                  'literal-control', audit), 'a actual z')
        self.assertEqual(audit, [dict(operation='literal-control', kind='literal', count=1)])
        for text, old in (('missing', 'anchor'), ('anchor anchor', 'anchor'), ('any', '')):
            with self.subTest(text=text), self.assertRaisesRegex(
                    recovery.RecoveryError, 'literal-control: expected'):
                recovery.checked_replace(text, old, 'actual', 1, 'literal-control', [])

    def test_checked_regex_counts_cannot_silently_drop_or_add_operations(self):
        audit = []
        self.assertEqual(recovery.checked_regex('a1 a2', r'a\d', 'x', 2,
                                                'regex-control', audit), 'x x')
        for text in ('a1', 'a1 a2 a3'):
            with self.subTest(text=text), self.assertRaisesRegex(
                    recovery.RecoveryError, 'regex-control: expected'):
                recovery.checked_regex(text, r'a\d', 'x', 2, 'regex-control', [])

    def test_checked_region_requires_unique_ordered_real_boundaries(self):
        audit = []
        self.assertEqual(recovery.checked_region('p<B>inside<E>q', '<B>', '<E>', 'new',
                                                'region-control', audit), 'pnew<E>q')
        self.assertEqual(audit[0]['removed_sha256'], sha(b'<B>inside'))
        for text in ('no boundaries', '<B>x<E><E>', '<B><B>x<E>', '<E>x<B>'):
            with self.subTest(text=text), self.assertRaisesRegex(
                    recovery.RecoveryError, 'region-control:'):
                recovery.checked_region(text, '<B>', '<E>', 'new', 'region-control', [])

    def test_named_transform_anchor_count_drift_is_caught_after_the_raw_gate(self):
        real = recovery.checked_replace
        for label, duplicate in (('header-task-namespace', False),
                                 ('header-task-namespace', True),
                                 ('body-native-includes', True)):
            fired = []
            def altered(text, old, new, count, operation, audit):
                if operation == label and not fired:
                    fired.append(operation)
                    text = text + old if duplicate else text.replace(old, '', 1)
                return real(text, old, new, count, operation, audit)
            with self.subTest(label=label, duplicate=duplicate):
                with mock.patch.object(recovery, 'checked_replace', side_effect=altered):
                    with self.assertRaisesRegex(recovery.RecoveryError, re.escape(label) + ': expected'):
                        recovery.transform_sources(self.raw)
                self.assertEqual(fired, [label])

    def test_historical_output_hash_set_and_byte_guards(self):
        outputs, unused = recovery.transform_sources(self.raw)
        recovery.verify_output_hashes(outputs)
        missing = dict(outputs)
        missing.pop('linux_wait.c')
        extra = dict(outputs, foreign=b'not a recovered owner')
        changed = dict(outputs)
        changed['linux_wait.c'] += b'\n'
        wrong_type = dict(outputs)
        wrong_type['linux_wait.c'] = wrong_type['linux_wait.c'].decode()
        for candidate in (missing, extra, changed, wrong_type):
            with self.subTest(paths=list(candidate)), self.assertRaises(recovery.RecoveryError):
                recovery.verify_output_hashes(candidate)

    def test_recipe_and_ledger_byte_drift_fail_before_output_creation(self):
        for path in (self.recipe, self.ledger):
            original = path.read_bytes()
            path.write_bytes(original + b' drift')
            with self.subTest(path=path), self.assertRaisesRegex(
                    recovery.RecoveryError, 'frozen recipe or historical ledger identity differs'):
                recovery.recover(self.inputs, self.output)
            self.assertFalse(self.output.exists())
            path.write_bytes(original)

    def test_matching_ledger_digest_cannot_approve_foreign_historical_outputs(self):
        document = json.loads(self.ledger.read_bytes())
        document['linux_wait.c'] = '0' * 64
        self.ledger.write_text(json.dumps(document))
        with mock.patch.object(recovery, 'LEDGER_SHA256', sha(self.ledger.read_bytes())):
            with self.assertRaisesRegex(recovery.RecoveryError, 'historical ledger output identities differ'):
                recovery.recover(self.inputs, self.output)
        self.assertFalse(self.output.exists())

    def test_recipe_symlink_cannot_substitute_identical_witness(self):
        raw = self.recipe.read_bytes()
        target = save(self.base / 'recipe-copy.py', raw)
        self.recipe.unlink()
        self.recipe.symlink_to(target)
        with self.assertRaisesRegex(recovery.RecoveryError, 'aliased'):
            recovery.recover(self.inputs, self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_transformed_output_is_rejected_before_exclusive_mkdir(self):
        real = recovery.transform_sources
        def changed(raw):
            outputs, audit = real(raw)
            outputs['linux_wait.c'] += b'\n/* output drift */\n'
            return outputs, audit
        with mock.patch.object(recovery, 'transform_sources', side_effect=changed):
            with self.assertRaisesRegex(recovery.RecoveryError, 'historical output SHA256 mismatch'):
                recovery.recover(self.inputs, self.output)
        self.assertFalse(self.output.exists())

    def test_input_and_witness_drift_after_transform_fail_before_mkdir(self):
        real = recovery.transform_sources
        for path in (self.inputs / 'include/linux/wait.h', self.inputs / 'provenance.json',
                     self.recipe, self.ledger):
            original = path.read_bytes()
            def changed(raw):
                result = real(raw)
                path.write_bytes(original + b' after-read drift')
                return result
            with self.subTest(path=path):
                with mock.patch.object(recovery, 'transform_sources', side_effect=changed):
                    with self.assertRaisesRegex(recovery.RecoveryError, 'changed before output creation'):
                        recovery.recover(self.inputs, self.output)
                self.assertFalse(self.output.exists())
                path.write_bytes(original)

    def test_recover_is_deterministic_exactly_three_files_and_sources_remain_unchanged(self):
        before = self.source_bytes()
        first = recovery.recover(self.inputs, self.output)
        second_path = self.base / 'second'
        second = recovery.recover(self.inputs, second_path)
        self.assertEqual(first, second)
        self.assertEqual(self.payload_files(self.output), self.payload_files(second_path))
        self.assertEqual(set(self.payload_files(self.output)), EXPECTED_PAYLOADS)
        self.assertEqual(json.loads((self.output / 'provenance.json').read_bytes()), first)
        self.assertEqual(self.source_bytes(), before)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual({name: sha((self.output / name).read_bytes()) for name in EXPECTED_OUTPUTS},
                         EXPECTED_OUTPUTS)
        self.assertIn('NO CHECKOUT/CLEAN-TREE CLAIM', first['source_mode'])
        self.assertEqual(first['native_preprocessing'], 'NOT_RUN')
        self.assertEqual(first['native_compilation'], 'NOT_RUN')
        self.assertFalse(first['linked'])
        self.assertFalse(first['installed'])
        self.assertEqual(first['runtime'], 'NOT_RUN')

    def test_returned_input_and_open_gate_metadata_cannot_mutate_global_or_later_recovery(self):
        identities = copy.deepcopy(recovery.SOURCE_IDENTITIES)
        gates = list(recovery.OPEN_GATES)
        with mock.patch.object(recovery, 'SOURCE_IDENTITIES', copy.deepcopy(identities)), \
             mock.patch.object(recovery, 'OPEN_GATES', list(gates)):
            first = recovery.recover(self.inputs, self.output)
            name = next(iter(identities))
            first['inputs'][name]['size'] = 0
            first['inputs'][name]['source_url'] = 'https://example.invalid'
            first['open_gates'].append('injected test metadata')
            self.assertEqual(recovery.SOURCE_IDENTITIES, identities)
            self.assertEqual(recovery.OPEN_GATES, gates)
            second = recovery.recover(self.inputs, self.base / 'second')
            self.assertEqual(second['inputs'], identities)
            self.assertEqual(second['open_gates'], gates)

    def test_only_the_exact_isolated_directory_is_allowed_inside_repository(self):
        allowed = self.repository / 'compat/native-runtime/wait-f43'
        recovery.recover(self.inputs, allowed)
        self.assertEqual(set(self.payload_files(allowed)), EXPECTED_PAYLOADS)
        forbidden = self.repository / 'compat/native-runtime/unreviewed'
        with self.assertRaisesRegex(recovery.RecoveryError, 'repository output is restricted'):
            recovery.recover(self.inputs, forbidden)
        self.assertFalse(forbidden.exists())

    def test_existing_file_directory_and_output_symlink_are_not_clobbered(self):
        existing_file = save(self.base / 'existing-file', b'keep exact file')
        existing_directory = self.base / 'existing-directory'
        existing_directory.mkdir()
        sentinel = save(existing_directory / 'sentinel', b'keep exact sentinel')
        alias = self.base / 'output-alias'
        alias.symlink_to(existing_directory, target_is_directory=True)
        for output in (existing_file, existing_directory, alias):
            with self.subTest(output=output), self.assertRaisesRegex(
                    recovery.RecoveryError, 'fresh output required'):
                recovery.recover(self.inputs, output)
        self.assertEqual(existing_file.read_bytes(), b'keep exact file')
        self.assertEqual(sentinel.read_bytes(), b'keep exact sentinel')
        self.assertEqual(list(existing_directory.iterdir()), [sentinel])

    def test_parent_alias_dangling_output_alias_and_input_overlap_are_rejected(self):
        real_parent = self.base / 'real-parent'
        real_parent.mkdir()
        alias_parent = self.base / 'alias-parent'
        alias_parent.symlink_to(real_parent, target_is_directory=True)
        dangling = self.base / 'dangling'
        dangling.symlink_to(self.base / 'does-not-exist')
        for output, message in ((alias_parent / 'result', 'canonical'),
                                (dangling, 'fresh output'),
                                (self.inputs / 'nested-output', 'overlap or alias')):
            with self.subTest(output=output), self.assertRaisesRegex(recovery.RecoveryError, message):
                recovery.recover(self.inputs, output)
        self.assertFalse((real_parent / 'result').exists())
        self.assertFalse((self.inputs / 'nested-output').exists())

    def test_admitted_parent_swapped_during_transform_creates_no_redirected_output(self):
        parent = self.base / 'admitted-parent'
        parent.mkdir()
        moved = self.base / 'held-original-parent'
        redirected = self.base / 'redirected-parent'
        redirected.mkdir()
        output = parent / 'recovered'
        original = recovery.transform_sources
        swapped = []
        def swap(raw):
            result = original(raw)
            parent.rename(moved)
            parent.symlink_to(redirected, target_is_directory=True)
            swapped.append(True)
            return result
        with mock.patch.object(recovery, 'transform_sources', side_effect=swap):
            with self.assertRaisesRegex(recovery.RecoveryError, 'admitted output parent changed'):
                recovery.recover(self.inputs, output)
        self.assertEqual(swapped, [True])
        self.assertFalse((moved / output.name).exists())
        self.assertFalse((redirected / output.name).exists())
        self.assertFalse(output.exists())

    def test_exclusive_creation_preserves_output_that_appears_after_preflight(self):
        real_mkdir = recovery.os.mkdir
        raced = []
        def competing_mkdir(path, *args, **kwargs):
            if str(path) == self.output.name and kwargs.get('dir_fd') is not None and not raced:
                raced.append(True)
                real_mkdir(path, *args, **kwargs)
                save(self.output / 'sentinel', b'competing owner')
            return real_mkdir(path, *args, **kwargs)
        with mock.patch.object(recovery.os, 'mkdir', side_effect=competing_mkdir) as patched:
            # Preserve the real capability control when replacing function identity.
            with mock.patch.object(recovery.os, 'supports_dir_fd',
                                   set(recovery.os.supports_dir_fd) | {patched}):
                with self.assertRaisesRegex(recovery.RecoveryError, 'created after preflight; preserved'):
                    recovery.recover(self.inputs, self.output)
        self.assertEqual(raced, [True])
        self.assertEqual(self.payload_files(self.output), {'sentinel': b'competing owner'})

    def test_postwrite_provenance_corruption_fails_and_preserves_private_evidence(self):
        real_write = recovery._write_file_at
        corrupted = []
        def changing_write(directory_fd, name, raw):
            real_write(directory_fd, name, raw)
            if name == 'provenance.json':
                descriptor = os.open(name, os.O_WRONLY | os.O_TRUNC, dir_fd=directory_fd)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(b'corrupted provenance evidence')
                corrupted.append(True)
        with mock.patch.object(recovery, '_write_file_at', side_effect=changing_write):
            with self.assertRaisesRegex(recovery.RecoveryError, 'output/provenance changed during write; preserved'):
                recovery.recover(self.inputs, self.output)
        self.assertEqual(corrupted, [True])
        self.assertTrue(self.output.is_dir())
        self.assertEqual((self.output / 'provenance.json').read_bytes(),
                         b'corrupted provenance evidence')

    def test_postwrite_code_corruption_is_also_rejected_without_deleting_evidence(self):
        real_write = recovery._write_file_at
        def changing_write(directory_fd, name, raw):
            real_write(directory_fd, name, raw + b' drift' if name == 'linux_wait.c' else raw)
        with mock.patch.object(recovery, '_write_file_at', side_effect=changing_write):
            with self.assertRaisesRegex(recovery.RecoveryError, 'output/provenance changed during write; preserved'):
                recovery.recover(self.inputs, self.output)
        self.assertTrue(self.output.is_dir())
        self.assertTrue((self.output / 'linux_wait.c').read_bytes().endswith(b' drift'))

    def test_postwrite_input_drift_fails_with_output_preserved(self):
        real_write = recovery._write_file_at
        changed = []
        def changing_write(directory_fd, name, raw):
            real_write(directory_fd, name, raw)
            if name == 'provenance.json':
                target = self.inputs / 'kernel/sched/wait.c'
                target.write_bytes(target.read_bytes() + b' post-write drift')
                changed.append(True)
        with mock.patch.object(recovery, '_write_file_at', side_effect=changing_write):
            with self.assertRaisesRegex(recovery.RecoveryError, 'changed during recovery; output preserved'):
                recovery.recover(self.inputs, self.output)
        self.assertEqual(changed, [True])
        self.assertEqual(set(self.payload_files(self.output)), EXPECTED_PAYLOADS)

    def test_unsupported_safe_output_capability_fails_explicitly_before_creation(self):
        with mock.patch.object(recovery.os, 'supports_dir_fd', set()):
            with self.assertRaisesRegex(recovery.RecoveryError, 'safe directory-relative output creation is unavailable'):
                recovery.recover(self.inputs, self.output)
        self.assertFalse(self.output.exists())

    def test_python_optimized_mode_keeps_real_input_identity_guards(self):
        path = self.inputs / 'kernel/sched/wait.c'
        path.write_bytes(path.read_bytes() + b' invalid raw source')
        command = [sys.executable, '-B', '-O', str(REPOSITORY / 'tools/recover_native_wait.py'),
                   '--inputs', str(self.inputs), '--output', str(self.output)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=60,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('pinned raw size/SHA256/Git blob mismatch', result.stderr)
        self.assertFalse(self.output.exists())

    def test_python_optimized_mode_keeps_count_guards_with_a_positive_control(self):
        code = (
            'import sys; sys.path.insert(0, ' + repr(str(REPOSITORY / 'tools')) + '); '
            'import recover_native_wait as r\n'
            'if r.checked_replace("anchor", "anchor", "actual", 1, "positive", []) != "actual":\n'
            ' raise SystemExit(2)\n'
            'try:\n'
            ' r.checked_replace("anchor anchor", "anchor", "actual", 1, "optimized-count", [])\n'
            'except r.RecoveryError as error:\n'
            ' print(str(error))\n'
            'else:\n'
            ' raise SystemExit(3)\n')
        result = subprocess.run([sys.executable, '-B', '-O', '-c', code],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=60,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('optimized-count: expected 1 occurrences, observed 2', result.stdout)


if __name__ == '__main__':
    unittest.main()
