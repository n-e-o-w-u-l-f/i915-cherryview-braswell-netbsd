"""F44 Wait admission tests: private files/identities only; never run a producer or native tool."""
import contextlib
import copy
import hashlib
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

COMPILED = (
    'compat/native-runtime/wait-f43/linux_wait.c',
    'compat/native-runtime/wait-f43/include/linux/wait.h',
    'compat/native-runtime/include/linux/sched.h',
    'compat/native-runtime/include/linux/task_netbsd.h',
    'compat/native-runtime/include/linux/raw_spinlock.h',
    'compat/native-runtime/task/sched.h',
    'compat/native-runtime/task/task_netbsd.h',
    'compat/linux/raw_spinlock.h')
PROOFS = (
    'compat/native-runtime/wait-inputs-f43/include/linux/wait.h',
    'compat/native-runtime/wait-inputs-f43/kernel/sched/wait.c',
    'compat/native-runtime/wait-inputs-f43/provenance.json',
    'compat/native-runtime/wait-f43/provenance.json',
    'compat/native-runtime/task/generate_wait.py',
    'compat/native-runtime/task/SOURCE_SHA256.json',
    'tools/recover_native_wait.py')
PROVENANCE = 'compat/native-runtime/wait-f43/provenance.json'
INPUT_PROVENANCE = 'compat/native-runtime/wait-inputs-f43/provenance.json'
LEDGER = 'compat/native-runtime/task/SOURCE_SHA256.json'
WAIT_SHA = '5561d9005df2e8018262fb81437ae5abc88e2cb13a6f7306f604a3d4e728309c'
OLD_SELECTIONS = (
    ('CONTRACT_PATH', 'CONTRACT_SHA256'),
    ('ANON_CONTRACT_PATH', 'ANON_CONTRACT_SHA256'),
    ('FILE_CONTRACT_PATH', 'FILE_CONTRACT_SHA256'),
    ('TASK_CONTRACT_PATH', 'TASK_CONTRACT_SHA256'),
    ('TASK_WORKER_CONTRACT_PATH', 'TASK_WORKER_CONTRACT_SHA256'))


class WaitFixture:
    core_fixture = old_fixture.ProviderInputTests.core_fixture
    write_core = old_fixture.ProviderInputTests.write_core
    verify_core = old_fixture.ProviderInputTests.verify_core

    def setUp(self):
        old_fixture.ProviderInputTests.setUp(self)
        self.contract = copy.deepcopy(admission.load_contract(REPOSITORY / admission.WAIT_CONTRACT_PATH))
        for relative in self.contract['repository_inputs']:
            save(self.repo / relative, (REPOSITORY / relative).read_bytes())
        self.bindings = {
            str(self.repo / relative): dict(kind='repository', relative=relative, **row)
            for relative, row in self.contract['repository_inputs'].items()}
        self.unit = self.repo / COMPILED[0]
        self.compiled_paths = {self.repo / name for name in COMPILED}
        self.paths = self.compiled_paths | {self.native, self.opt}
        self.arguments = (self.repo, self.bindings, self.source, self.overlay,
                          self.obj, self.patched, self.declared)

    def generation(self):
        return admission.verify_wait_generation(self.repo, self.contract, self.bindings, WAIT_SHA)

    def read_json(self, relative):
        return json.loads((self.repo / relative).read_bytes())

    def rebind(self, relative, raw):
        save(self.repo / relative, raw)
        row = self.contract['repository_inputs'][relative]
        row.update(sha256=sha(raw), blob=blob(raw))
        self.bindings[str(self.repo / relative)] = dict(kind='repository', relative=relative, **row)

    @contextlib.contextmanager
    def changed_payload(self, relative, raw):
        original = (self.repo / relative).read_bytes()
        row = copy.deepcopy(self.contract['repository_inputs'][relative])
        bound = copy.deepcopy(self.bindings[str(self.repo / relative)])
        self.rebind(relative, raw)
        try:
            yield
        finally:
            (self.repo / relative).write_bytes(original)
            self.contract['repository_inputs'][relative] = row
            self.bindings[str(self.repo / relative)] = bound

    @contextlib.contextmanager
    def changed_provenance(self, document=None, raw=None):
        if raw is None:
            raw = (json.dumps(document, indent=2) + '\n').encode()
        previous = self.contract['generation_provenance_sha256']
        with self.changed_payload(PROVENANCE, raw):
            self.contract['generation_provenance_sha256'] = sha(raw)
            with mock.patch.object(admission, '_WAIT_PROVENANCE_SHA256', sha(raw)):
                try:
                    yield
                finally:
                    self.contract['generation_provenance_sha256'] = previous

    @contextlib.contextmanager
    def changed_ledger(self, raw):
        # Rebind both the ledger itself and the declaration inside the bound
        # output document, so duplicates/cross-links reach their logical guard.
        witnesses = copy.deepcopy(admission._WAIT_WITNESSES)
        witnesses['historical_ledger'].update(sha256=sha(raw), git_blob=blob(raw))
        document = self.read_json(PROVENANCE)
        document['witnesses'] = witnesses
        with self.changed_payload(LEDGER, raw):
            with mock.patch.object(admission, '_WAIT_WITNESSES', witnesses):
                with self.changed_provenance(document):
                    yield

    def git_contract(self):
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for arguments in (['init', '-q'],
                          ['add', '--', *self.contract['repository_inputs']],
                          ['commit', '-q', '-m', 'private Wait generation binding']):
            subprocess.run(['git', '-C', str(self.repo)] + arguments, env=environment,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        document = copy.deepcopy(self.contract)
        document['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'],
            env=environment).decode().strip()
        return document


class WaitProviderInputTests(unittest.TestCase, WaitFixture):
    setUp = WaitFixture.setUp

    def test_fixed_sixth_manifest_has_exact_real_commit_fifteen_rows_and_eight_consumables(self):
        self.assertEqual(admission.WAIT_CONTRACT_PATH,
                         'compat/native-runtime/wait-contracts/provider-inputs-f44-wait.json')
        self.assertEqual(admission.WAIT_CONTRACT_SHA256, WAIT_SHA)
        self.assertEqual(self.contract['repository_commit'],
                         '610c66b412672ca96b0048179d07035929443402')
        self.assertEqual(self.contract['linux_pin'], 'fd179f8a05be3ccae366b9b96e176b51fbe54aab')
        self.assertEqual(set(self.contract['repository_inputs']), set(COMPILED) | set(PROOFS))
        self.assertEqual({name for name, row in self.contract['repository_inputs'].items()
                          if row['role'] == 'generation_proof_owner'}, set(PROOFS))
        self.assertEqual(admission.wait_input_policy(self.contract, WAIT_SHA), sorted(COMPILED))

    def test_empty_file_requirement_belongs_only_to_exact_wait_digest_and_shape(self):
        core = {'patched_inputs': self.patched}
        self.assertEqual(admission.provider_header_policy(core, self.contract, WAIT_SHA), [])
        for digest in (None, '0' * 64, admission.TASK_CONTRACT_SHA256):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                admission.provider_header_policy(core, self.contract, digest)
        self.assertEqual(admission.provider_header_policy(core),
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])

    def test_all_old_five_profiles_keep_their_policies_and_skip_wait_generation(self):
        core = {'patched_inputs': self.patched}
        expected = [2, 1, 1, 0, 0]
        for (path_name, hash_name), count in zip(OLD_SELECTIONS, expected):
            contract = admission.load_contract(REPOSITORY / getattr(admission, path_name))
            digest = getattr(admission, hash_name)
            with self.subTest(path=path_name):
                self.assertEqual(admission.wait_input_policy(contract, digest), [])
                self.assertEqual(admission.verify_wait_generation(self.repo, contract, {}, digest), {})
                self.assertEqual(len(admission.provider_header_policy(core, contract, digest)), count)

    def test_wait_profile_shape_role_set_order_and_invalid_types_are_rejected(self):
        mutations = (
            lambda c: c.update(provider_root='compat/native-runtime/task'),
            lambda c: c.update(units=['linux_task.c']),
            lambda c: c.update(repository_include_roots=list(reversed(c['repository_include_roots']))),
            lambda c: c.update(native_include_roots=list(reversed(c['native_include_roots']))),
            lambda c: c.update(required_patched_headers=['sys/sys/file.h']),
            lambda c: c.update(linux_pin='0' * 40),
            lambda c: c.update(generation_provenance_sha256='0' * 64),
            lambda c: c['repository_inputs'].pop(COMPILED[0]),
            lambda c: c['repository_inputs'].update({'foreign': dict(role='wait_header')}),
            lambda c: c['repository_inputs'][PROOFS[0]].update(role='wait_header'))
        for index, mutate in enumerate(mutations):
            changed = copy.deepcopy(self.contract)
            mutate(changed)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Wait provider identity/shape'):
                admission.wait_input_policy(changed, WAIT_SHA)
        for contract in (None, [], [1], 'invalid', {'repository_inputs': None}):
            with self.subTest(contract=contract), self.assertRaises(ValueError):
                admission.wait_input_policy(contract, WAIT_SHA)

    def test_selected_root_order_uses_recovered_header_then_task_then_native(self):
        expected = ([self.repo / name for name in self.contract['repository_include_roots']] +
                    [self.source / name for name in self.contract['native_include_roots']])
        self.assertEqual(self.contract['repository_include_roots'],
                         ['compat/native-runtime/wait-f43/include', 'compat/native-runtime/include'])
        self.assertEqual(admission.selected_inputs(self.contract, self.repo, self.source,
                          self.repo / self.contract['provider_root'], ['linux_wait.c'], []), expected)
        for includes in (list(reversed(expected)), [self.repo / 'compat'], expected[1:]):
            with self.subTest(includes=includes), self.assertRaises(ValueError):
                admission.selected_inputs(self.contract, self.repo, self.source,
                    self.repo / self.contract['provider_root'], ['linux_wait.c'], includes)

    def test_selected_include_root_alias_cannot_redirect_the_wait_header(self):
        root = self.repo / self.contract['repository_include_roots'][0]
        moved = root.with_name('actual-include')
        root.rename(moved)
        root.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliased'):
            admission.selected_inputs(self.contract, self.repo, self.source,
                self.repo / self.contract['provider_root'], ['linux_wait.c'], [])

    def test_all_six_source_owned_contracts_select_their_fixed_bytes(self):
        selections = list(OLD_SELECTIONS) + [('WAIT_CONTRACT_PATH', 'WAIT_CONTRACT_SHA256')]
        for path_name, hash_name in selections:
            relative = getattr(admission, path_name)
            raw = (REPOSITORY / relative).read_bytes()
            target = save(self.repo / relative, raw)
            with self.subTest(relative=relative):
                self.assertEqual(admission.reviewed_contract_sha256(target, self.repo),
                                 getattr(admission, hash_name))
                self.assertEqual(admission.load_contract(target, self.repo),
                                 admission.load_contract(REPOSITORY / relative))

    def test_crossed_contract_bytes_alias_and_direct_symlink_are_rejected(self):
        target = self.repo / admission.WAIT_CONTRACT_PATH
        for path_name, unused in OLD_SELECTIONS:
            save(target, (REPOSITORY / getattr(admission, path_name)).read_bytes())
            with self.subTest(path=path_name), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(target, self.repo)
        raw = (REPOSITORY / admission.WAIT_CONTRACT_PATH).read_bytes()
        alias = save(self.repo / 'compat/native-runtime/wait-contracts/unreviewed.json', raw)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(alias, self.repo)
        target.unlink()
        target.symlink_to(REPOSITORY / admission.WAIT_CONTRACT_PATH)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(target, self.repo)

    def test_private_git_binding_verifies_all_fifteen_including_nonconsumed_proofs(self):
        contract = self.git_contract()
        self.assertEqual(admission.repository_inputs(self.repo, contract), self.bindings)
        compiled = admission.provider_dependencies(self.paths, *self.arguments)
        self.assertEqual({row['relative'] for row in compiled.values()
                          if row['kind'] == 'repository'}, set(COMPILED))

    def test_inherited_git_selectors_cannot_redirect_wait_identity_reads(self):
        contract = self.git_contract()
        with mock.patch.dict(os.environ, GIT_DIR='/missing', GIT_WORK_TREE='/missing',
                             GIT_INDEX_FILE='/missing', GIT_COMMON_DIR='/missing',
                             GIT_REPLACE_REF_BASE='refs/forbidden'):
            self.assertEqual(admission.repository_inputs(self.repo, contract), self.bindings)

    def test_each_proof_dirty_byte_is_rejected_even_though_it_is_not_compiled(self):
        contract = self.git_contract()
        for name in PROOFS:
            path = self.repo / name
            original = path.read_bytes()
            path.write_bytes(original + b' changed proof')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'working bytes'):
                admission.repository_inputs(self.repo, contract)
            path.write_bytes(original)

    def test_git_path_blob_escape_and_selected_symlink_guards_still_apply(self):
        contract = self.git_contract()
        changed = copy.deepcopy(contract)
        changed['repository_inputs'][COMPILED[0]]['blob'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'working bytes'):
            admission.repository_inputs(self.repo, changed)
        changed = copy.deepcopy(contract)
        changed['repository_inputs'] = {'../escaped.c': changed['repository_inputs'][COMPILED[0]]}
        with self.assertRaises(ValueError):
            admission.repository_inputs(self.repo, changed)
        original = self.unit.read_bytes()
        target = save(self.base / 'external.c', original)
        self.unit.unlink()
        self.unit.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'aliases'):
            admission.repository_inputs(self.repo, contract)

    def test_each_of_eight_inputs_is_required_for_scan_and_post_md_proof(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        admission.require_wait_inputs(before, self.repo, self.contract, WAIT_SHA)
        for name in COMPILED:
            paths = self.paths - {self.repo / name}
            subset = admission.provider_dependencies(paths, *self.arguments)
            with self.subTest(name=name, phase='scan'), self.assertRaisesRegex(ValueError, 'required Wait input'):
                admission.require_wait_inputs(subset, self.repo, self.contract, WAIT_SHA)
            with self.subTest(name=name, phase='MD'), self.assertRaisesRegex(
                    ValueError, 'actual provider dependencies differ'):
                admission.recheck_provider_dependencies(paths, before, *self.arguments)

    def test_each_required_row_must_match_its_whole_bound_identity(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        for name in COMPILED:
            changed = copy.deepcopy(before)
            changed[str(self.repo / name)]['sha256'] = '0' * 64
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'required Wait input'):
                admission.require_wait_inputs(changed, self.repo, self.contract, WAIT_SHA)

    def test_each_of_seven_proof_owners_is_forbidden_in_scan_and_post_md(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        for name in PROOFS:
            paths = self.paths | {self.repo / name}
            with self.subTest(name=name, phase='scan'), self.assertRaisesRegex(
                    ValueError, 'generation proof owner is not a provider dependency'):
                admission.provider_dependencies(paths, *self.arguments)
            with self.subTest(name=name, phase='MD'), self.assertRaisesRegex(
                    ValueError, 'generation proof owner is not a provider dependency'):
                admission.recheck_provider_dependencies(paths, before, *self.arguments)

    def test_native_placeholder_cannot_replace_the_required_recovered_wait_header(self):
        native = save(self.source / 'sys/external/bsd/drm2/include/linux/wait.h',
                      b'/* private fixture: native placeholder has no generic API */\n')
        paths = self.paths - {self.repo / COMPILED[1]} | {native}
        proof = admission.provider_dependencies(paths, *self.arguments)
        self.assertEqual(proof[str(native)]['kind'], 'archive')
        with self.assertRaisesRegex(ValueError, 'required Wait input'):
            admission.require_wait_inputs(proof, self.repo, self.contract, WAIT_SHA)

    def test_consumed_header_drift_and_unreviewed_repo_dependency_are_rejected(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        path = self.repo / COMPILED[1]
        path.write_bytes(path.read_bytes() + b' changed after scan')
        with self.assertRaisesRegex(ValueError, 'repository dependency drift'):
            admission.recheck_provider_dependencies(self.paths, before, *self.arguments)
        extra = save(self.repo / 'compat/native-runtime/wait-f43/include/linux/extra.h', b'unreviewed')
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            admission.provider_dependencies({extra}, *self.arguments)

    def test_wait_empty_file_policy_keeps_full_core_tool_and_configuration_guards(self):
        core = self.core_fixture()
        self.assertEqual(self.verify_core(), core)
        proof = admission.provider_dependencies(self.paths, *self.arguments)
        admission.require_wait_inputs(proof, self.repo, self.contract, WAIT_SHA)
        admission.require_provider_headers(proof, self.repo, core, self.contract, WAIT_SHA)
        self.assertNotIn(str(self.lockstat), proof)
        for path in (self.lockstat, self.tools['compiler'], self.obj / 'Makefile'):
            original = path.read_bytes()
            path.write_bytes(original + b' core drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
