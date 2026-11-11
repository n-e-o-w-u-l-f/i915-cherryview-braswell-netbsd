"""F50 exact Worker input admission; private files only, no native tool execution."""
import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / 'tools'))
import native_provider_inputs as admission
import test_native_provider_inputs as old_fixture
from test_native_provider_inputs import blob, save, sha

UNIT = 'compat/native-runtime/worker-f49/linux_kthread.c'
HEADER = 'compat/native-runtime/worker-f49/include/linux/kthread.h'
PROVENANCE = 'compat/native-runtime/worker-f49/provenance.json'
PRODUCER = 'tools/recover_native_worker.py'
ORIGINS = (
    'compat/native-runtime/worker/base/linux_kthread.c',
    'compat/native-runtime/worker/base/kthread.h',
    'patches/0032-netbsd-linux-task-wait-worker.patch',
    'compat/native-runtime/worker/worker.inc',
    'compat/native-runtime/worker/worker_header.inc',
    'compat/native-runtime/worker/generate.py',
    'compat/native-runtime/worker/INTEGRATION.txt')
COMPILED = (
    UNIT, HEADER,
    'compat/native-runtime/include/linux/sched.h',
    'compat/native-runtime/include/linux/task_netbsd.h',
    'compat/native-runtime/include/linux/raw_spinlock.h',
    'compat/native-runtime/task/sched.h',
    'compat/native-runtime/task/task_netbsd.h',
    'compat/linux/raw_spinlock.h')
PROOFS = (PROVENANCE, PRODUCER) + ORIGINS
OLD_SELECTIONS = (
    ('CONTRACT_PATH', 'CONTRACT_SHA256'),
    ('ANON_CONTRACT_PATH', 'ANON_CONTRACT_SHA256'),
    ('FILE_CONTRACT_PATH', 'FILE_CONTRACT_SHA256'),
    ('TASK_CONTRACT_PATH', 'TASK_CONTRACT_SHA256'),
    ('TASK_WORKER_CONTRACT_PATH', 'TASK_WORKER_CONTRACT_SHA256'),
    ('WAIT_CONTRACT_PATH', 'WAIT_CONTRACT_SHA256'),
    ('POLL_CONTRACT_PATH', 'POLL_CONTRACT_SHA256'))


class WorkerFixture:
    core_fixture = old_fixture.ProviderInputTests.core_fixture
    write_core = old_fixture.ProviderInputTests.write_core
    verify_core = old_fixture.ProviderInputTests.verify_core

    def setUp(self):
        old_fixture.ProviderInputTests.setUp(self)
        self.contract = copy.deepcopy(admission.load_contract(
            REPOSITORY / admission.WORKER_CONTRACT_PATH))
        for name in self.contract['repository_inputs']:
            save(self.repo / name, (REPOSITORY / name).read_bytes())
        self.bindings = {str(self.repo / name): dict(kind='repository', relative=name, **row)
                         for name, row in self.contract['repository_inputs'].items()}
        for name in self.contract['repository_include_roots']:
            (self.repo / name).mkdir(parents=True, exist_ok=True)
        self.unit = self.repo / UNIT
        self.paths = {self.repo / name for name in COMPILED} | {self.native, self.opt}
        self.arguments = (self.repo, self.bindings, self.source, self.overlay,
                          self.obj, self.patched, self.declared)

    def generation(self):
        return admission.verify_worker_generation(self.repo, self.contract,
            self.bindings, admission.WORKER_CONTRACT_SHA256)

    def json(self, name=PROVENANCE):
        return json.loads((self.repo / name).read_bytes())

    @contextlib.contextmanager
    def changed_payload(self, name, raw):
        path = self.repo / name
        original = path.read_bytes()
        row = copy.deepcopy(self.contract['repository_inputs'][name])
        bound = copy.deepcopy(self.bindings[str(path)])
        path.write_bytes(raw)
        self.contract['repository_inputs'][name].update(sha256=sha(raw), blob=blob(raw))
        self.bindings[str(path)] = dict(kind='repository', relative=name,
                                      **self.contract['repository_inputs'][name])
        try:
            yield
        finally:
            path.write_bytes(original)
            self.contract['repository_inputs'][name] = row
            self.bindings[str(path)] = bound

    @contextlib.contextmanager
    def changed_provenance(self, document=None, raw=None):
        raw = raw if raw is not None else (json.dumps(document, indent=2) + '\n').encode()
        original = self.contract['generation_provenance_sha256']
        with self.changed_payload(PROVENANCE, raw):
            self.contract['generation_provenance_sha256'] = sha(raw)
            with mock.patch.object(admission, '_WORKER_PROVENANCE_SHA256', sha(raw)):
                try:
                    yield
                finally:
                    self.contract['generation_provenance_sha256'] = original

    def git_contract(self):
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for arguments in (['init', '-q'], ['add', '--', *self.contract['repository_inputs']],
                          ['commit', '-q', '-m', 'private Worker admission identities']):
            subprocess.run(['git', '-C', str(self.repo)] + arguments,
                check=True, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        document = copy.deepcopy(self.contract)
        document['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], env=environment).decode().strip()
        return document


class WorkerProviderInputTests(unittest.TestCase, WorkerFixture):
    setUp = WorkerFixture.setUp

    def test_eighth_fixed_profile_binds_published_worker_with_exact_seventeen_roles(self):
        self.assertEqual(admission.WORKER_CONTRACT_PATH,
                         'compat/native-runtime/worker-contracts/provider-inputs-f50-worker.json')
        self.assertEqual(sha((REPOSITORY / admission.WORKER_CONTRACT_PATH).read_bytes()),
                         admission.WORKER_CONTRACT_SHA256)
        self.assertEqual(self.contract['repository_commit'],
                         '7d9592e01f2efb41bbdd58e15346ffe6d7521136')
        self.assertEqual(self.contract['generation_provenance_sha256'],
                         '91f22a4fda6bdb0c9e61020acf31ac698c7ee009d65b07d58c7fa55c22a07fa1')
        self.assertEqual(set(self.contract['repository_inputs']), set(COMPILED) | set(PROOFS))
        self.assertEqual(len(COMPILED), 8)
        self.assertEqual(len(PROOFS), 9)
        self.assertTrue(all(self.contract['repository_inputs'][name]['role'] ==
                            'generation_proof_owner' for name in PROOFS))
        self.assertEqual(admission.worker_input_policy(self.contract,
                         admission.WORKER_CONTRACT_SHA256), sorted(COMPILED))

    def test_eight_consumed_rows_are_required_for_independent_M_and_actual_MD(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        admission.require_worker_inputs(before, self.repo, self.contract, admission.WORKER_CONTRACT_SHA256)
        for name in COMPILED:
            paths = self.paths - {self.repo / name}
            subset = admission.provider_dependencies(paths, *self.arguments)
            with self.subTest(name=name, phase='M'), self.assertRaisesRegex(ValueError, 'required Worker input'):
                admission.require_worker_inputs(subset, self.repo, self.contract,
                                                admission.WORKER_CONTRACT_SHA256)
            with self.subTest(name=name, phase='MD'), self.assertRaisesRegex(ValueError, 'actual provider dependencies'):
                admission.recheck_provider_dependencies(paths, before, *self.arguments)

    def test_nine_generation_witnesses_are_forbidden_in_both_dependency_paths(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        for name in PROOFS:
            paths = self.paths | {self.repo / name}
            with self.subTest(name=name, phase='M'), self.assertRaisesRegex(ValueError,
                    'generation proof owner is not a provider dependency'):
                admission.provider_dependencies(paths, *self.arguments)
            with self.subTest(name=name, phase='MD'), self.assertRaisesRegex(ValueError,
                    'generation proof owner is not a provider dependency'):
                admission.recheck_provider_dependencies(paths, before, *self.arguments)

    def test_every_required_binding_must_retain_its_whole_identity(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        for name in COMPILED:
            for key, value in (('sha256', '0' * 64), ('blob', '0' * 40),
                               ('role', 'foreign'), ('relative', 'foreign')):
                changed = copy.deepcopy(before)
                changed[str(self.repo / name)][key] = value
                with self.subTest(name=name, key=key), self.assertRaisesRegex(ValueError, 'required Worker input'):
                    admission.require_worker_inputs(changed, self.repo, self.contract,
                                                    admission.WORKER_CONTRACT_SHA256)

    def test_only_worker_then_task_and_two_native_roots_are_selected(self):
        self.assertEqual(self.contract['repository_include_roots'],
            ['compat/native-runtime/worker-f49/include', 'compat/native-runtime/include'])
        expected = [self.repo / name for name in self.contract['repository_include_roots']] + [
            self.source / name for name in self.contract['native_include_roots']]
        self.assertEqual(admission.selected_inputs(self.contract, self.repo, self.source,
            self.repo / self.contract['provider_root'], ['linux_kthread.c'], []), expected)
        for units, includes in ((['linux_task_worker_owner.c'], []),
                                (['linux_kthread.c'], expected[::-1]),
                                (['linux_kthread.c'], expected + [self.repo / 'compat']),
                                (['linux_kthread.c'], expected + [self.repo / 'compat/native-runtime/wait-f43/include'])):
            with self.subTest(units=units, includes=includes), self.assertRaises(ValueError):
                admission.selected_inputs(self.contract, self.repo, self.source,
                    self.repo / self.contract['provider_root'], units, includes)

    def test_worker_empty_file_policy_is_exact_and_default_core_policy_is_preserved(self):
        core = {'patched_inputs': self.patched}
        self.assertEqual(admission.provider_header_policy(core, self.contract,
                         admission.WORKER_CONTRACT_SHA256), [])
        self.assertEqual(admission.provider_header_policy(core),
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])
        for digest in (None, '0' * 64, admission.WAIT_CONTRACT_SHA256, admission.POLL_CONTRACT_SHA256):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                admission.provider_header_policy(core, self.contract, digest)

    def test_all_eight_source_owned_contract_paths_keep_fixed_bytes_and_old_seven_policies(self):
        core = {'patched_inputs': self.patched}
        for path_name, hash_name in OLD_SELECTIONS + (('WORKER_CONTRACT_PATH', 'WORKER_CONTRACT_SHA256'),):
            relative = getattr(admission, path_name)
            path = save(self.repo / relative, (REPOSITORY / relative).read_bytes())
            self.assertEqual(admission.reviewed_contract_sha256(path, self.repo), getattr(admission, hash_name))
            self.assertEqual(admission.load_contract(path, self.repo),
                             admission.load_contract(REPOSITORY / relative))
        for (path_name, hash_name), expected_headers in zip(OLD_SELECTIONS, [2, 1, 1, 0, 0, 0, 1]):
            contract = admission.load_contract(REPOSITORY / getattr(admission, path_name))
            digest = getattr(admission, hash_name)
            with self.subTest(path=path_name):
                self.assertEqual(admission.worker_input_policy(contract, digest), [])
                self.assertEqual(admission.verify_worker_generation(self.repo, contract, {}, digest), {})
                self.assertEqual(len(admission.provider_header_policy(core, contract, digest)), expected_headers)

    def test_worker_shape_scope_role_set_and_type_mutations_are_rejected(self):
        changes = (
            lambda c: c.update(schema=True),
            lambda c: c.update(provider_root='compat/native-runtime/task'),
            lambda c: c.update(units=['linux_task.c']),
            lambda c: c.update(required_patched_headers=['sys/sys/file.h']),
            lambda c: c.update(repository_include_roots=c['repository_include_roots'][::-1]),
            lambda c: c.update(native_include_roots=c['native_include_roots'][::-1]),
            lambda c: c.update(generation_provenance_sha256='0' * 64),
            lambda c: c['repository_inputs'].pop(PROVENANCE),
            lambda c: c['repository_inputs'][PROVENANCE].update(role='worker_header'),
            lambda c: c['repository_inputs'].update({'foreign': dict(role='worker_header')}))
        for index, change in enumerate(changes):
            changed = copy.deepcopy(self.contract); change(changed)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Worker provider identity/shape'):
                admission.worker_input_policy(changed, admission.WORKER_CONTRACT_SHA256)
        for document in (None, [], 'foreign', {'repository_inputs': None}):
            with self.subTest(document=document), self.assertRaises(ValueError):
                admission.worker_input_policy(document, admission.WORKER_CONTRACT_SHA256)

    def test_crossed_contract_bytes_unreviewed_path_and_alias_are_rejected(self):
        path = self.repo / admission.WORKER_CONTRACT_PATH
        for path_name, unused in OLD_SELECTIONS:
            save(path, (REPOSITORY / getattr(admission, path_name)).read_bytes())
            with self.subTest(path=path_name), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)
        unreviewed = save(self.repo / 'compat/native-runtime/worker-contracts/unreviewed.json',
                         (REPOSITORY / admission.WORKER_CONTRACT_PATH).read_bytes())
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(unreviewed, self.repo)
        path.unlink(); path.symlink_to(unreviewed)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(path, self.repo)

    def test_duplicate_contract_keys_are_rejected_after_rebinding_fixture_digest(self):
        document = copy.deepcopy(self.contract)
        raw = b'{"schema":1,' + json.dumps(document).encode()[1:]
        path = save(self.repo / admission.WORKER_CONTRACT_PATH, raw)
        with mock.patch.object(admission, 'WORKER_CONTRACT_SHA256', sha(raw)):
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                admission.load_contract(path, self.repo)

    def test_real_git_binds_all_seventeen_and_each_dirty_proof_is_rejected(self):
        contract = self.git_contract()
        self.assertEqual(admission.repository_inputs(self.repo, contract), self.bindings)
        for name in PROOFS:
            path = self.repo / name; original = path.read_bytes()
            path.write_bytes(original + b' drift')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'working bytes'):
                admission.repository_inputs(self.repo, contract)
            path.write_bytes(original)

    def test_git_environment_and_path_alias_guards_still_apply(self):
        contract = self.git_contract()
        with mock.patch.dict(os.environ, GIT_DIR='/missing', GIT_INDEX_FILE='/missing',
                             GIT_WORK_TREE='/missing', GIT_COMMON_DIR='/missing',
                             GIT_REPLACE_REF_BASE='refs/forbidden'):
            self.assertEqual(admission.repository_inputs(self.repo, contract), self.bindings)
        original = self.unit.read_bytes()
        target = save(self.base / 'external-worker.c', original)
        self.unit.unlink(); self.unit.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'aliases'):
            admission.repository_inputs(self.repo, contract)

    def test_unreviewed_wait_header_cannot_join_worker_dependencies(self):
        header = save(self.repo / 'compat/native-runtime/wait-f43/include/linux/wait.h', b'foreign Wait')
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            admission.provider_dependencies(self.paths | {header}, *self.arguments)

    def test_full_core_guards_remain_mandatory_despite_no_consumed_FILE_header(self):
        core = self.core_fixture()
        self.assertEqual(self.verify_core(), core)
        proof = admission.provider_dependencies(self.paths, *self.arguments)
        admission.require_worker_inputs(proof, self.repo, self.contract, admission.WORKER_CONTRACT_SHA256)
        admission.require_provider_headers(proof, self.repo, core, self.contract, admission.WORKER_CONTRACT_SHA256)
        for path in (self.patched_desc, self.lockstat, self.tools['compiler'],
                     self.obj / 'Makefile', self.obj / 'netbsd'):
            original = path.read_bytes(); path.write_bytes(original + b' core drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
