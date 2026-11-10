"""F39 exact Task input/composition admission; no native preprocessing or build."""
import copy
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_provider_inputs as admission

FRAGMENTS = {
    'compat/native-entry/task_entry.inc',
    'compat/native-file/task_entry_preallocated.inc',
    'compat/native-file/task_quiesce_retained.inc'}
INPUTS = FRAGMENTS | {
    'compat/native-runtime/task/linux_task.c',
    'compat/native-runtime/task/task_entry_netbsd.h',
    'compat/native-runtime/task/sched.h',
    'compat/native-runtime/task/task_netbsd.h',
    'compat/linux/raw_spinlock.h',
    'compat/native-runtime/include/linux/sched.h',
    'compat/native-runtime/include/linux/task_netbsd.h',
    'compat/native-runtime/include/linux/raw_spinlock.h'}


class TaskProviderInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo, self.source = self.root / 'repo', self.root / 'source'
        self.repo.mkdir()
        self.source.mkdir()
        self.contract = admission.load_contract(admission.REPOSITORY / admission.TASK_CONTRACT_PATH)
        self.core = dict(patched_inputs={'sys/sys/file.h': 'a' * 64,
                                        'sys/sys/filedesc.h': 'b' * 64})

    def policy(self, contract=None, identity=None):
        return admission.provider_header_policy(
            self.core, self.contract if contract is None else contract,
            admission.TASK_CONTRACT_SHA256 if identity is None else identity)

    def fragments(self, contract=None, identity=None):
        return admission.task_fragment_policy(
            self.contract if contract is None else contract,
            admission.TASK_CONTRACT_SHA256 if identity is None else identity)

    def bindings(self):
        return {str(self.repo / name): dict(kind='repository', relative=name, **row)
                for name, row in self.contract['repository_inputs'].items()}

    def test_fourth_contract_has_exact_task_unit_roots_and_three_fragments(self):
        self.assertEqual(admission.TASK_CONTRACT_PATH,
                         'compat/native-runtime/task/provider-inputs-f39-task.json')
        self.assertEqual(self.contract['provider_root'], 'compat/native-runtime/task')
        self.assertEqual(self.contract['units'], ['linux_task.c'])
        self.assertEqual(self.contract['required_patched_headers'], [])
        self.assertEqual(self.contract['repository_include_roots'], ['compat/native-runtime/include'])
        self.assertEqual(self.contract['native_include_roots'],
                         ['sys/external/bsd/common/include', 'sys/external/bsd/drm2/include'])
        self.assertEqual(set(self.contract['repository_inputs']), INPUTS)
        self.assertEqual({name for name, row in self.contract['repository_inputs'].items()
                          if row['role'] == 'task_fragment'}, FRAGMENTS)
        self.assertEqual(self.fragments(), sorted(FRAGMENTS))
        self.assertEqual(self.policy(), [])
        self.assertEqual(self.contract['core_status_sha256'],
                         'd1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794')

    def test_empty_header_policy_requires_exact_reviewed_identity_and_shape(self):
        for identity in ('0' * 64, admission.FILE_CONTRACT_SHA256):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.policy(identity=identity)
        forged = dict(kind='task', required_patched_headers=[])
        with self.assertRaises(ValueError):
            self.policy(forged)
        for key, value in (
                ('provider_root', 'compat/native-file'),
                ('units', ['linux_file.c']),
                ('repository_include_roots', ['compat']),
                ('native_include_roots', list(reversed(self.contract['native_include_roots']))),
                ('required_patched_headers', ['sys/sys/file.h'])):
            bad = copy.deepcopy(self.contract)
            bad[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.policy(bad)

    def test_old_file_policies_keep_both_header_default_and_file_requirement(self):
        self.assertEqual(admission.provider_header_policy(self.core),
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])
        for relative in (admission.CONTRACT_PATH, admission.ANON_CONTRACT_PATH,
                         admission.FILE_CONTRACT_PATH):
            old = admission.load_contract(admission.REPOSITORY / relative)
            expected = (['sys/sys/file.h', 'sys/sys/filedesc.h']
                        if relative == admission.CONTRACT_PATH else ['sys/sys/file.h'])
            self.assertEqual(admission.provider_header_policy(self.core, old), expected)
            old['required_patched_headers'] = []
            with self.subTest(contract=relative), self.assertRaises(ValueError):
                admission.provider_header_policy(self.core, old)
            old['required_patched_headers'] = ['sys/sys/filedesc.h']
            with self.subTest(contract=relative), self.assertRaisesRegex(ValueError, 'FILE'):
                admission.provider_header_policy(self.core, old)

    def test_fragment_policy_cannot_drop_add_relabel_or_alias_an_owner(self):
        for name in FRAGMENTS:
            for operation in ('drop', 'role', 'alias'):
                bad = copy.deepcopy(self.contract)
                row = bad['repository_inputs'][name]
                if operation == 'drop':
                    bad['repository_inputs'].pop(name)
                elif operation == 'role':
                    row['role'] = 'api_definition_owner'
                else:
                    bad['repository_inputs'][name + '.other'] = bad['repository_inputs'].pop(name)
                with self.subTest(name=name, operation=operation), self.assertRaises(ValueError):
                    self.fragments(bad)
        bad = copy.deepcopy(self.contract)
        bad['repository_inputs']['compat/native-entry/extra.inc'] = dict(
            role='task_fragment', blob='a' * 40, sha256='b' * 64)
        with self.assertRaises(ValueError):
            self.fragments(bad)
        with self.assertRaises(ValueError):
            self.fragments(identity=admission.FILE_CONTRACT_SHA256)

    def test_every_fragment_must_be_consumed_by_the_dependency_proof(self):
        proof = self.bindings()
        admission.require_task_fragments(proof, self.repo, self.contract,
                                         admission.TASK_CONTRACT_SHA256)
        for name in FRAGMENTS:
            incomplete = copy.deepcopy(proof)
            incomplete.pop(str(self.repo / name))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'fragment'):
                admission.require_task_fragments(incomplete, self.repo, self.contract,
                                                 admission.TASK_CONTRACT_SHA256)

    def test_fragment_consumption_requires_repository_kind_and_matching_role(self):
        for name in FRAGMENTS:
            for key, value in (('kind', 'archive'), ('role', 'api_definition_owner'),
                               ('relative', 'compat/native-entry/other.inc')):
                proof = self.bindings()
                proof[str(self.repo / name)][key] = value
                with self.subTest(name=name, field=key), self.assertRaises(ValueError):
                    admission.require_task_fragments(proof, self.repo, self.contract,
                                                     admission.TASK_CONTRACT_SHA256)

    def test_task_roots_and_unit_do_not_accept_include_overrides(self):
        for name in self.contract['repository_include_roots']:
            (self.repo / name).mkdir(parents=True)
        for name in self.contract['native_include_roots']:
            (self.source / name).mkdir(parents=True)
        provider = self.repo / self.contract['provider_root']
        provider.mkdir()
        expected = [self.repo / 'compat/native-runtime/include'] + [
            self.source / name for name in self.contract['native_include_roots']]
        self.assertEqual(admission.selected_inputs(self.contract, self.repo, self.source,
                                                  provider, ['linux_task.c'], []), expected)
        for roots in ([self.repo / 'compat'], expected[::-1], expected[:-1]):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                admission.selected_inputs(self.contract, self.repo, self.source,
                                          provider, ['linux_task.c'], roots)
        with self.assertRaises(ValueError):
            admission.selected_inputs(self.contract, self.repo, self.source,
                                      provider, ['linux_file.c'], [])
        root = expected[0]
        target = root.with_name('aliased')
        root.rename(target)
        root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            admission.selected_inputs(self.contract, self.repo, self.source,
                                      provider, ['linux_task.c'], [])

    def test_task_contract_copy_alias_symlink_crossed_bytes_and_tamper_rejected(self):
        actual = admission.REPOSITORY / admission.TASK_CONTRACT_PATH
        path = self.repo / admission.TASK_CONTRACT_PATH
        path.parent.mkdir(parents=True)
        path.write_bytes(actual.read_bytes())
        self.assertEqual(admission.load_contract(path, self.repo), self.contract)
        alias = path.with_name('unreviewed.json')
        alias.write_bytes(actual.read_bytes())
        with self.assertRaises(ValueError):
            admission.load_contract(alias, self.repo)
        for old in (admission.CONTRACT_PATH, admission.ANON_CONTRACT_PATH,
                    admission.FILE_CONTRACT_PATH):
            path.write_bytes((admission.REPOSITORY / old).read_bytes())
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)
        path.write_bytes(actual.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            admission.load_contract(path, self.repo)
        path.unlink()
        path.symlink_to(actual)
        with self.assertRaises(ValueError):
            admission.load_contract(path, self.repo)

    def test_all_task_inputs_require_actual_git_blob_and_raw_byte_identity(self):
        contract = copy.deepcopy(self.contract)
        for name, row in contract['repository_inputs'].items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = ('/* isolated ' + name + ' */\n').encode()
            path.write_bytes(raw)
            row['sha256'] = hashlib.sha256(raw).hexdigest()
            row['blob'] = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for command in (['init', '-q'], ['add', '--', *contract['repository_inputs']],
                        ['commit', '-q', '-m', 'isolated Task provenance']):
            subprocess.run(['git', '-C', str(self.repo)] + command, env=environment,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        contract['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], env=environment).decode().strip()
        self.assertEqual(len(admission.repository_inputs(self.repo, contract)), len(INPUTS))
        for name in FRAGMENTS:
            path = self.repo / name
            original = path.read_bytes()
            path.write_bytes(original + b'changed\n')
            with self.subTest(fragment=name), self.assertRaisesRegex(ValueError, 'working bytes differ'):
                admission.repository_inputs(self.repo, contract)
            path.write_bytes(original)
        bad = copy.deepcopy(contract)
        name = next(iter(FRAGMENTS))
        bad['repository_inputs'][name]['blob'] = '0' * 40
        with self.assertRaises(ValueError):
            admission.repository_inputs(self.repo, bad)


if __name__ == '__main__':
    unittest.main()
