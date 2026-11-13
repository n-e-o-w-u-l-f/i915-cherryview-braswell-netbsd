"""F56 source admission regressions; private fixtures only, NOT_HP_ACCEPTANCE.

These tests exercise public admission boundaries.  Compiler dependency sets in
fixtures are synthetic and do not claim that any native preprocessor ran.
"""
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

FILE = 'compat/native-file/'
MM = 'compat/native-mm/include/linux/'
UIO = 'compat/native-uio/include/linux/'
TASK = 'compat/native-runtime/task/'
WRAPPER = FILE + 'linux_native_fileops_owner.c'
RAW_FILEOPS = FILE + 'linux_native_fileops.c'
TASK_API = TASK + 'task_entry_netbsd.h'
COMMON = frozenset([
    FILE + 'include/linux/file_api_netbsd.h',
    FILE + 'include/linux/file_netbsd.h',
    FILE + 'include/linux/file_ref_netbsd.h',
    FILE + 'include/linux/fs_netbsd.h',
    FILE + 'include/linux/pagemap_netbsd.h',
    MM + 'mapping_netbsd.h', MM + 'mm_abi_types_netbsd.h',
    MM + 'mm_identity_netbsd.h', MM + 'vma_netbsd.h',
    UIO + 'kiocb_netbsd.h'])
FILEOPS = COMMON | frozenset([
    RAW_FILEOPS, WRAPPER, TASK_API,
    FILE + 'include/linux/shmem_fs_netbsd.h', MM + 'mm_netbsd.h',
    UIO + 'uio_netbsd.h',
    'compat/native-runtime/include/linux/raw_spinlock.h',
    'compat/native-runtime/include/linux/task_netbsd.h',
    TASK + 'task_netbsd.h', 'compat/linux/raw_spinlock.h'])
PROFILES = (
    ('INODE', 'linux_inode.c', COMMON | {FILE + 'linux_inode.c'}),
    ('NATIVE_FILEOPS', 'linux_native_fileops_owner.c', FILEOPS),
    ('PAGE', 'linux_page.c', COMMON | {FILE + 'linux_page.c'}),
    ('SHMEM_COMMIT', 'linux_shmem_commit.c', frozenset([
        FILE + 'linux_shmem_commit.c', FILE + 'include/linux/file_ref_netbsd.h',
        FILE + 'include/linux/fs_netbsd.h', MM + 'mm_abi_types_netbsd.h',
        UIO + 'kiocb_netbsd.h'])))
OLD_SELECTIONS = (
    ('CONTRACT', 'f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3'),
    ('ANON_CONTRACT', 'c45f3ab9f59602955ec5ebe27974a926316787faa0ff57935e3f1c95ac00214d'),
    ('FILE_CONTRACT', 'a79eaf94d6f0c9b0ee0b64ed998f7e158b6ad0cb5b305878c79ef1c49a4f2e09'),
    ('TASK_CONTRACT', '5709061e886f4334c32b2485b98a38c8854ab3929e27ff41ce23192535c273df'),
    ('TASK_WORKER_CONTRACT', '0741fbe18dfd9600edad6cc490e4f9609fcf706c461e21c067cb1a132adeb0a4'),
    ('WAIT_CONTRACT', '5561d9005df2e8018262fb81437ae5abc88e2cb13a6f7306f604a3d4e728309c'),
    ('POLL_CONTRACT', '9f477521b790e036aaa0dbfddccee1c1ebb06bf62c6034c3d5b4d8b4e5e0db60'),
    ('WORKER_CONTRACT', '996f8a34b35e4345c16814f5d72dbd0bdbb1691bdd9a281b3a0bd9fb18560dc3'))


def constant(stem, suffix):
    return getattr(admission, stem + '_CONTRACT_' + suffix)


class FourFixture:
    def select(self, profile):
        self.stem, self.filename, self.compiled = profile
        self.relative = constant(self.stem, 'PATH')
        self.digest = constant(self.stem, 'SHA256')
        self.contract = copy.deepcopy(admission.load_contract(REPOSITORY / self.relative))
        self.bindings = {}
        for name, row in self.contract['repository_inputs'].items():
            path = save(self.repo / name, (REPOSITORY / name).read_bytes())
            self.bindings[str(path)] = dict(kind='repository', relative=name, **row)
        for name in self.contract['repository_include_roots']:
            (self.repo / name).mkdir(parents=True, exist_ok=True)
        save(self.repo / self.relative, (REPOSITORY / self.relative).read_bytes())
        self.paths = {self.repo / name for name in self.compiled} | {self.native, self.opt}
        if self.contract['required_patched_headers']:
            self.paths.add(self.patched_file)
        self.arguments = (self.repo, self.bindings, self.source, self.overlay,
                          self.obj, self.patched, self.declared)

    def git_contract(self):
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for arguments in (['init', '-q'], ['add', '--', *self.contract['repository_inputs']],
                          ['commit', '-q', '-m', 'private F56 input identities; NOT_HP_ACCEPTANCE']):
            subprocess.run(['git', '-C', str(self.repo)] + arguments, check=True,
                           env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        document = copy.deepcopy(self.contract)
        document['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], env=environment).decode().strip()
        return document


class FourProviderInputTests(unittest.TestCase, FourFixture):
    setUp = old_fixture.ProviderInputTests.setUp

    def test_four_distinct_fixed_contracts_bind_the_reviewed_units_and_source_identity(self):
        commits, digests = set(), set()
        for profile in PROFILES:
            self.select(profile)
            with self.subTest(profile=self.stem):
                self.assertEqual(sha((REPOSITORY / self.relative).read_bytes()), self.digest)
                self.assertEqual(self.contract['provider_root'], 'compat/native-file')
                self.assertEqual(self.contract['units'], [self.filename])
                self.assertEqual(admission.four_provider_input_policy(self.contract, self.digest),
                                 sorted(self.compiled))
                self.assertEqual(self.contract['core_status_sha256'],
                    'd1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794')
                commits.add(self.contract['repository_commit']); digests.add(self.digest)
        self.assertEqual(len(commits), 1)
        self.assertEqual(len(digests), 4)
        self.assertRegex(next(iter(commits)), r'^[0-9a-f]{40}$')

    def test_fileops_translation_implementation_and_real_task_api_have_separate_identities(self):
        self.select(PROFILES[1])
        rows = self.contract['repository_inputs']
        expected = {
            WRAPPER: ('translation_unit', '7c8ae90e12656f532665bc9cf06232950b17ef62ce926d9b727b8493ef3b6b92'),
            RAW_FILEOPS: ('implementation_owner', '7cd66e99bf821b28c2afb9b39beac35d71f35c494e294dbb9641abe597840d53'),
            TASK_API: ('task_entry_header', 'a452e9a552e80972bdf311b34a86f8e7c1a54d0736fdb8e4bf72b06fe8cbb032')}
        for name, (role, digest) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(rows[name]['role'], role)
                self.assertEqual(rows[name]['sha256'], digest)
                self.assertIn(name, self.compiled)
        # Identity headers alone do not supply these declarations.
        identity = (REPOSITORY / (TASK + 'task_netbsd.h')).read_text()
        self.assertNotIn('linux_task_entry_enter(', identity)
        self.assertNotIn('linux_task_entry_leave(', identity)
        api = (REPOSITORY / TASK_API).read_text()
        self.assertIn('linux_task_entry_enter(', api)
        self.assertIn('linux_task_entry_leave(', api)
        self.assertTrue(any(row['role'] == 'api_definition_owner' for row in rows.values()))

    def test_every_mandatory_input_is_required_by_M_and_actual_MD(self):
        for profile in PROFILES:
            self.select(profile)
            before = admission.provider_dependencies(self.paths, *self.arguments)
            admission.require_four_provider_inputs(before, self.repo, self.contract, self.digest)
            for name in self.compiled:
                remaining = self.paths - {self.repo / name}
                with self.subTest(profile=self.stem, name=name, phase='M'):
                    partial = admission.provider_dependencies(remaining, *self.arguments)
                    with self.assertRaises(ValueError):
                        admission.require_four_provider_inputs(partial, self.repo,
                                                               self.contract, self.digest)
                with self.subTest(profile=self.stem, name=name, phase='MD'):
                    with self.assertRaisesRegex(ValueError, 'actual provider dependencies'):
                        admission.recheck_provider_dependencies(remaining, before, *self.arguments)

    def test_API_definition_and_generation_proof_owners_cannot_be_consumed_in_either_phase(self):
        self.select(PROFILES[1])
        before = admission.provider_dependencies(self.paths, *self.arguments)
        proofs = [name for name, row in self.contract['repository_inputs'].items()
                  if row['role'] in ('api_definition_owner', 'generation_proof_owner')]
        self.assertTrue(proofs)
        for name in proofs:
            paths = self.paths | {self.repo / name}
            for phase in ('M', 'MD'):
                with self.subTest(name=name, phase=phase), self.assertRaisesRegex(
                        ValueError, 'owner is not a provider dependency'):
                    if phase == 'M':
                        admission.provider_dependencies(paths, *self.arguments)
                    else:
                        admission.recheck_provider_dependencies(paths, before, *self.arguments)

    def test_ownership_receipt_keeps_source_provenance_separate_from_native_acceptance(self):
        for profile in PROFILES:
            self.select(profile)
            proof = admission.verify_four_provider_ownership(self.repo, self.contract,
                                                             self.bindings, self.digest)
            with self.subTest(profile=self.stem):
                self.assertEqual(proof['state'], 'VERIFIED_SOURCE_OWNERSHIP_ONLY')
                self.assertEqual(proof['repository_commit'], self.contract['repository_commit'])
                self.assertEqual(proof['provider_unit'], self.filename)
                self.assertEqual(proof['required_repository_inputs'], sorted(self.compiled))
                self.assertEqual(proof['native_preprocessing'], 'NOT_RUN')
                self.assertEqual(proof['native_compilation'], 'NOT_RUN')
                self.assertIs(proof['linked'], False)
                self.assertEqual(proof['runtime'], 'NOT_RUN')
                self.assertFalse(set(proof['optional_repository_inputs']) & self.compiled)
                if self.stem == 'NATIVE_FILEOPS':
                    self.assertEqual(set(proof['excluded_definition_owners']), {
                        TASK + 'linux_task.c', 'compat/native-entry/task_entry.inc',
                        FILE + 'task_entry_preallocated.inc', FILE + 'task_quiesce_retained.inc'})
                else:
                    self.assertEqual(proof['excluded_definition_owners'], {})

    def test_definition_owner_binding_is_required_even_when_it_is_not_a_compiler_dependency(self):
        self.select(PROFILES[1])
        owners = [name for name, row in self.contract['repository_inputs'].items()
                  if row['role'] == 'api_definition_owner']
        self.assertEqual(len(owners), 4)
        for name in owners:
            for operation in ('remove', 'rebind'):
                changed = copy.deepcopy(self.bindings)
                if operation == 'remove':
                    changed.pop(str(self.repo / name))
                else:
                    changed[str(self.repo / name)]['blob'] = '0' * 40
                with self.subTest(name=name, operation=operation), self.assertRaises(ValueError):
                    admission.verify_four_provider_ownership(self.repo, self.contract,
                                                             changed, self.digest)

    def test_rebinding_mutated_Task_API_and_owner_cannot_turn_them_into_reviewed_evidence(self):
        self.select(PROFILES[1])
        owner = next(name for name, row in self.contract['repository_inputs'].items()
                     if row['role'] == 'api_definition_owner')
        for name in (TASK_API, owner):
            path = self.repo / name; raw = path.read_bytes()
            changed = copy.deepcopy(self.contract); rebound = copy.deepcopy(self.bindings)
            altered = raw + b' '
            path.write_bytes(altered)
            changed['repository_inputs'][name].update(sha256=sha(altered), blob=blob(altered))
            rebound[str(path)] = dict(kind='repository', relative=name,
                                     **changed['repository_inputs'][name])
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    admission.verify_four_provider_ownership(self.repo, changed, rebound, self.digest)
            finally:
                path.write_bytes(raw)

    def test_required_binding_retains_whole_identity(self):
        for profile in PROFILES:
            self.select(profile)
            before = admission.provider_dependencies(self.paths, *self.arguments)
            for name in self.compiled:
                for key, value in (('kind', 'native'), ('relative', 'foreign'),
                                   ('role', 'foreign'), ('blob', '0' * 40),
                                   ('sha256', '0' * 64)):
                    changed = copy.deepcopy(before); changed[str(self.repo / name)][key] = value
                    with self.subTest(profile=self.stem, name=name, key=key), self.assertRaises(ValueError):
                        admission.require_four_provider_inputs(changed, self.repo,
                                                               self.contract, self.digest)

    def test_reviewed_archive_transitive_Task_headers_are_optional_but_frozen_when_consumed(self):
        for profile in PROFILES:
            self.select(profile)
            proof = admission.verify_four_provider_ownership(self.repo, self.contract,
                                                             self.bindings, self.digest)
            optional = set(proof['optional_repository_inputs'])
            self.assertEqual(len(optional), 2 if self.stem == 'NATIVE_FILEOPS' else 6)
            paths = self.paths | {self.repo / name for name in optional}
            before = admission.provider_dependencies(paths, *self.arguments)
            admission.require_four_provider_inputs(before, self.repo, self.contract, self.digest)
            self.assertEqual(admission.recheck_provider_dependencies(paths, before, *self.arguments), before)
            for name in optional:
                path = self.repo / name; raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                try:
                    with self.subTest(profile=self.stem, name=name), self.assertRaisesRegex(
                            ValueError, 'repository dependency drift'):
                        admission.provider_dependencies(paths, *self.arguments)
                finally:
                    path.write_bytes(raw)

    def test_unreviewed_or_crossed_digest_cannot_admit_any_of_the_four_shapes(self):
        for profile in PROFILES:
            self.select(profile)
            for digest in (None, '0' * 64, admission.CONTRACT_SHA256,
                           constant(PROFILES[(PROFILES.index(profile) + 1) % 4][0], 'SHA256')):
                with self.subTest(profile=self.stem, digest=digest), self.assertRaises(ValueError):
                    admission.four_provider_input_policy(self.contract, digest)

    def test_shape_scope_roles_types_and_root_order_fail_closed(self):
        for profile in PROFILES:
            self.select(profile)
            changes = (
                lambda c: c.update(schema=True),
                lambda c: c.update(provider_root='compat/native-runtime/task'),
                lambda c: c.update(units=['linux_file.c']),
                lambda c: c.update(repository_include_roots=c['repository_include_roots'][::-1]),
                lambda c: c.update(native_include_roots=c['native_include_roots'][::-1]),
                lambda c: c.update(repository_commit='0' * 40),
                lambda c: c['repository_inputs'].pop(next(iter(c['repository_inputs']))),
                lambda c: c['repository_inputs'][FILE + self.filename].update(role='file_header'),
                lambda c: c['repository_inputs'].update({'foreign': dict(role='file_header')}))
            for index, change in enumerate(changes):
                changed = copy.deepcopy(self.contract); change(changed)
                with self.subTest(profile=self.stem, index=index), self.assertRaises(ValueError):
                    admission.four_provider_input_policy(changed, self.digest)
            for document in (None, [], 'foreign', {'repository_inputs': None}):
                with self.subTest(profile=self.stem, document=document), self.assertRaises(ValueError):
                    admission.four_provider_input_policy(document, self.digest)

    def test_only_each_fixed_unit_and_exact_ordered_include_roots_are_selected(self):
        for profile in PROFILES:
            self.select(profile)
            expected = [self.repo / name for name in self.contract['repository_include_roots']] + [
                self.source / name for name in self.contract['native_include_roots']]
            self.assertEqual(admission.selected_inputs(self.contract, self.repo, self.source,
                self.repo / 'compat/native-file', [self.filename], []), expected)
            for units, includes in ((['linux_file.c'], []), ([self.filename], expected[::-1]),
                    ([self.filename], expected + [self.repo / 'compat'])):
                with self.subTest(profile=self.stem, units=units, includes=includes), self.assertRaises(ValueError):
                    admission.selected_inputs(self.contract, self.repo, self.source,
                        self.repo / 'compat/native-file', units, includes)

    def test_only_shmem_exact_profile_may_have_empty_FILE_requirement(self):
        core = {'patched_inputs': self.patched}
        self.assertEqual(admission.provider_header_policy(core), ['sys/sys/file.h', 'sys/sys/filedesc.h'])
        for profile in PROFILES:
            self.select(profile)
            expected = [] if self.stem == 'SHMEM_COMMIT' else ['sys/sys/file.h']
            self.assertEqual(admission.provider_header_policy(core, self.contract, self.digest), expected)
            if expected:
                changed = copy.deepcopy(self.contract); changed['required_patched_headers'] = []
                with self.subTest(profile=self.stem), self.assertRaises(ValueError):
                    admission.provider_header_policy(core, changed, self.digest)
            else:
                for digest in (None, '0' * 64, admission.CONTRACT_SHA256):
                    with self.subTest(digest=digest), self.assertRaises(ValueError):
                        admission.provider_header_policy(core, self.contract, digest)

    def test_original_patched_header_is_forbidden_even_for_shmem_empty_requirement(self):
        for profile in PROFILES:
            self.select(profile)
            with self.subTest(profile=self.stem), self.assertRaisesRegex(ValueError, 'original.*patched|patched.*original'):
                admission.provider_dependencies(self.paths | {self.original}, *self.arguments)

    def test_real_git_binds_every_input_and_rejects_any_dirty_bytes(self):
        for profile in PROFILES:
            self.select(profile)
            contract = self.git_contract()
            self.assertEqual(admission.repository_inputs(self.repo, contract), self.bindings)
            for name in contract['repository_inputs']:
                path = self.repo / name; raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                try:
                    with self.subTest(profile=self.stem, name=name), self.assertRaisesRegex(ValueError, 'working bytes differ'):
                        admission.repository_inputs(self.repo, contract)
                finally:
                    path.write_bytes(raw)

    def test_same_bytes_from_wrong_git_tree_and_symlink_are_rejected(self):
        self.select(PROFILES[1]); contract = self.git_contract()
        changed = copy.deepcopy(contract)
        changed['repository_inputs'][TASK_API]['blob'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'working bytes differ'):
            admission.repository_inputs(self.repo, changed)
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        subprocess.run(['git', '-C', str(self.repo), 'rm', '--cached', '--', TASK_API],
                       check=True, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-q', '-m', 'remove API from tree'],
                       check=True, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        changed = copy.deepcopy(contract)
        changed['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], env=environment).decode().strip()
        with self.assertRaisesRegex(ValueError, 'commit/path/blob differs'):
            admission.repository_inputs(self.repo, changed)
        api = self.repo / TASK_API; raw = api.read_bytes(); api.unlink()
        target = save(self.repo / 'private-api-target.h', raw); api.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'aliases'):
            admission.repository_inputs(self.repo, contract)

    def test_source_owned_contract_bytes_crossed_profiles_and_aliases_are_rejected(self):
        self.select(PROFILES[0]); path = self.repo / self.relative
        for other in PROFILES[1:]:
            save(path, (REPOSITORY / constant(other[0], 'PATH')).read_bytes())
            with self.subTest(other=other[0]), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)
        target = save(self.repo / 'private-contract.json', (REPOSITORY / self.relative).read_bytes())
        path.unlink(); path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(path, self.repo)

    def test_duplicate_JSON_keys_cannot_be_hidden_by_a_fixture_digest_rebind(self):
        self.select(PROFILES[0])
        raw = b'{"schema":1,' + json.dumps(self.contract).encode()[1:]
        path = save(self.repo / self.relative, raw)
        with mock.patch.object(admission, 'INODE_CONTRACT_SHA256', sha(raw)):
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                admission.load_contract(path, self.repo)

    def test_old_eight_fixed_bytes_and_header_policies_remain_independently_reviewed(self):
        core = {'patched_inputs': self.patched}
        for (stem, digest), header_count in zip(OLD_SELECTIONS, (2, 1, 1, 0, 0, 0, 1, 0)):
            path = getattr(admission, stem + '_PATH')
            self.assertEqual(getattr(admission, stem + '_SHA256'), digest)
            contract = admission.load_contract(REPOSITORY / path)
            self.assertEqual(sha((REPOSITORY / path).read_bytes()), digest)
            with self.subTest(profile=stem):
                self.assertEqual(admission.four_provider_input_policy(contract, digest), [])
                self.assertEqual(admission.verify_four_provider_ownership(self.repo, contract, {}, digest), {})
                self.assertEqual(len(admission.provider_header_policy(core, contract, digest)), header_count)


if __name__ == '__main__':
    unittest.main()
