"""F37 FILE provider input/owner admission tests; isolated fixtures, no native execution."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_provider_inputs as admission
import test_native_provider_inputs as f33_fixture
from test_native_provider_inputs import blob, save, sha


class FileProviderInputTests(unittest.TestCase):
    core_fixture = f33_fixture.ProviderInputTests.core_fixture
    write_core = f33_fixture.ProviderInputTests.write_core
    verify_core = f33_fixture.ProviderInputTests.verify_core

    def setUp(self):
        f33_fixture.ProviderInputTests.setUp(self)
        old_relative = self.relative
        self.unit.unlink()
        self.relative = 'compat/native-file/linux_file.c'
        self.unit = save(self.repo / self.relative, b'/* isolated reviewed FILE unit */\n')
        self.repo_contract['units'] = ['linux_file.c']
        self.repo_contract['repository_inputs'].pop(old_relative)
        self.repo_contract['repository_inputs'][self.relative] = self.identity(
            self.unit, 'translation_unit')
        self.repo_contract['required_patched_headers'] = ['sys/sys/file.h']
        self.repo_contract['repository_include_roots'].append('compat/native-runtime/include')
        mappings = [
            ('sched.h', '../../task/sched.h', 'compat/native-runtime/task/sched.h'),
            ('task_netbsd.h', '../../task/task_netbsd.h', 'compat/native-runtime/task/task_netbsd.h'),
            ('raw_spinlock.h', '../../../linux/raw_spinlock.h', 'compat/linux/raw_spinlock.h')]
        self.forwarders, self.task_owners = [], []
        for name, target, owner in mappings:
            wrapper = save(self.repo / 'compat/native-runtime/include/linux' / name,
                           ('#include "' + target + '"\n').encode())
            actual = save(self.repo / owner, ('/* isolated reviewed owner ' + name + ' */\n').encode())
            self.forwarders.append(wrapper)
            self.task_owners.append(actual)
            self.repo_contract['repository_inputs'][str(wrapper.relative_to(self.repo))] = self.identity(
                wrapper, 'public_forwarder')
            self.repo_contract['repository_inputs'][owner] = self.identity(actual, 'owner_header')
        self.api_owner = save(self.repo / 'compat/native-entry/task_entry.inc',
                              b'/* isolated API definition owner, not a compiler dependency */\n')
        self.repo_contract['repository_inputs'][str(self.api_owner.relative_to(self.repo))] = self.identity(
            self.api_owner, 'api_definition_owner')
        self.repo_bindings = {
            str(self.repo / name): dict(kind='repository', relative=name, **row)
            for name, row in self.repo_contract['repository_inputs'].items()}
        self.provider_paths = {self.unit, self.repo_header, self.native, self.patched_file,
                               self.opt, *self.forwarders, *self.task_owners}
        self.arguments = (self.repo, self.repo_bindings, self.source, self.overlay,
                          self.obj, self.patched, self.declared)

    def identity(self, path, role):
        raw = path.read_bytes()
        return dict(role=role, blob=blob(raw), sha256=sha(raw))

    def git_fixture(self):
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for arguments in (['init', '-q'],
                          ['add', '--', *self.repo_contract['repository_inputs']],
                          ['commit', '-q', '-m', 'isolated FILE provenance']):
            subprocess.run(['git', '-C', str(self.repo)] + arguments, env=environment,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.repo_contract['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'],
            env=environment).decode().strip()
        return self.repo_contract

    def reviewed(self, relative=None):
        return admission.load_contract(
            admission.REPOSITORY / (relative or admission.FILE_CONTRACT_PATH))

    def test_third_fixed_contract_binds_actual_source_commit_and_eighteen_inputs(self):
        contract = self.reviewed()
        self.assertEqual(admission.FILE_CONTRACT_PATH,
                         'compat/native-file/provider-inputs-f37-file.json')
        self.assertEqual(admission.FILE_CONTRACT_SHA256, 'a79eaf94d6f0c9b0ee0b64ed998f7e158b6ad0cb5b305878c79ef1c49a4f2e09')
        self.assertEqual(contract['repository_commit'],
                         '4858b14bdb6d94fa27ce1e9d5b966dd98c0637bb')
        self.assertEqual(contract['units'], ['linux_file.c'])
        self.assertEqual(contract['required_patched_headers'], ['sys/sys/file.h'])
        expected = {
            'compat/native-file/linux_file.c',
            'compat/native-file/task_entry_preallocated.h',
            'compat/native-file/include/linux/file_api_netbsd.h',
            'compat/native-file/include/linux/file_netbsd.h',
            'compat/native-file/include/linux/fs_netbsd.h',
            'compat/native-file/include/linux/file_ref_netbsd.h',
            'compat/native-file/include/linux/pagemap_netbsd.h',
            'compat/native-mm/include/linux/mm_abi_types_netbsd.h',
            'compat/native-mm/include/linux/vma_netbsd.h',
            'compat/native-mm/include/linux/mm_identity_netbsd.h',
            'compat/native-uio/include/linux/kiocb_netbsd.h',
            'compat/native-runtime/include/linux/sched.h',
            'compat/native-runtime/include/linux/task_netbsd.h',
            'compat/native-runtime/include/linux/raw_spinlock.h',
            'compat/native-runtime/task/sched.h',
            'compat/native-runtime/task/task_netbsd.h',
            'compat/linux/raw_spinlock.h',
            'compat/native-entry/task_entry.inc'}
        self.assertEqual(set(contract['repository_inputs']), expected)
        api = contract['repository_inputs']['compat/native-entry/task_entry.inc']
        self.assertEqual(api, dict(role='api_definition_owner',
                                  blob='d2b65c9c6c2a9c5057e6060f742e2288a45ca97f',
                                  sha256='8ea9c5916936e90ec5957f32c10fda2f0e92ec5a7a891d2d322b33d73f0cc026'))
        self.assertEqual(sum(row['role'] == 'api_definition_owner'
                             for row in contract['repository_inputs'].values()), 1)

    def test_three_fixed_source_owned_contracts_preserve_prior_identity(self):
        selections = [
            (admission.CONTRACT_PATH, 'f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3'),
            (admission.ANON_CONTRACT_PATH, 'c45f3ab9f59602955ec5ebe27974a926316787faa0ff57935e3f1c95ac00214d'),
            (admission.FILE_CONTRACT_PATH, 'a79eaf94d6f0c9b0ee0b64ed998f7e158b6ad0cb5b305878c79ef1c49a4f2e09')]
        for relative, expected in selections:
            actual = admission.REPOSITORY / relative
            copy_path = save(self.repo / relative, actual.read_bytes())
            with self.subTest(relative=relative):
                self.assertEqual(admission.reviewed_contract_sha256(copy_path, self.repo), expected)
                self.assertEqual(admission.load_contract(copy_path, self.repo), self.reviewed(relative))
        self.assertEqual(self.reviewed()['core_status_sha256'],
                         'd1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794')

    def test_crossed_contract_bytes_cannot_select_another_owner(self):
        relatives = [admission.CONTRACT_PATH, admission.ANON_CONTRACT_PATH,
                     admission.FILE_CONTRACT_PATH]
        for destination in relatives:
            for source in relatives:
                if source == destination:
                    continue
                path = save(self.repo / destination,
                            (admission.REPOSITORY / source).read_bytes())
                with self.subTest(destination=destination, source=source):
                    with self.assertRaisesRegex(ValueError, 'bytes differ'):
                        admission.load_contract(path, self.repo)

    def test_new_contract_rejects_alias_foreign_path_symlink_and_tamper(self):
        actual = admission.REPOSITORY / admission.FILE_CONTRACT_PATH
        path = save(self.repo / admission.FILE_CONTRACT_PATH, actual.read_bytes())
        alias = save(self.repo / 'compat/native-file/unreviewed.json', actual.read_bytes())
        for candidate in (alias, actual):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, 'source-owned'):
                admission.load_contract(candidate, self.repo)
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            admission.load_contract(path, self.repo)
        path.unlink()
        path.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(path, self.repo)

    def test_runtime_mapping_has_one_exact_narrow_root_before_native_kpi_roots(self):
        contract = self.reviewed()
        self.assertEqual(contract['repository_include_roots'],
                         ['compat/native-file/include', 'compat/native-mm/include',
                          'compat/native-uio/include', 'compat/native-runtime/include'])
        self.assertEqual(contract['native_include_roots'],
                         ['sys/external/bsd/common/include', 'sys/external/bsd/drm2/include'])
        expected = ([self.repo / name for name in contract['repository_include_roots']] +
                    [self.source / name for name in contract['native_include_roots']])
        provider = self.repo / 'compat/native-file'
        self.assertEqual(admission.selected_inputs(contract, self.repo, self.source,
                                                  provider, ['linux_file.c'], []), expected)
        for includes in ([self.repo / 'compat'], list(reversed(expected)), expected[:-1]):
            with self.subTest(includes=includes), self.assertRaises(ValueError):
                admission.selected_inputs(contract, self.repo, self.source, provider,
                                          ['linux_file.c'], includes)
        for unit in ('linux_fd.c', 'linux_anon.c'):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                admission.selected_inputs(contract, self.repo, self.source, provider, [unit], [])

    def test_narrow_root_symlink_cannot_redirect_runtime_owners(self):
        contract = self.reviewed()
        root = self.repo / 'compat/native-runtime/include'
        original = root.with_name('actual')
        root.rename(original)
        root.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliased'):
            admission.selected_inputs(contract, self.repo, self.source,
                                      self.repo / 'compat/native-file', ['linux_file.c'], [])

    def test_private_repository_checks_api_owner_even_when_not_consumed(self):
        contract = self.git_fixture()
        proof = admission.repository_inputs(self.repo, contract)
        self.assertEqual(proof, self.repo_bindings)
        self.assertEqual(proof[str(self.api_owner)]['role'], 'api_definition_owner')
        compiled = admission.provider_dependencies(self.provider_paths, *self.arguments)
        self.assertNotIn(str(self.api_owner), compiled)
        self.api_owner.write_bytes(self.api_owner.read_bytes() + b' drift after admission')
        with self.assertRaisesRegex(ValueError, 'working bytes'):
            admission.repository_inputs(self.repo, contract)

    def test_api_owner_commit_blob_is_required_without_fake_dependency_consumption(self):
        contract = self.git_fixture()
        changed = copy.deepcopy(contract)
        relative = str(self.api_owner.relative_to(self.repo))
        changed['repository_inputs'][relative]['blob'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'working bytes'):
            admission.repository_inputs(self.repo, changed)
        raw = self.api_owner.read_bytes()
        alias = 'compat/native-entry/uncommitted.inc'
        save(self.repo / alias, raw)
        changed = copy.deepcopy(contract)
        changed['repository_inputs'][alias] = changed['repository_inputs'].pop(relative)
        with self.assertRaisesRegex(ValueError, 'commit/path/blob'):
            admission.repository_inputs(self.repo, changed)

    def test_api_definition_owner_is_forbidden_in_scan_and_post_md_dependencies(self):
        before = admission.provider_dependencies(self.provider_paths, *self.arguments)
        for check in (
                lambda: admission.provider_dependencies(self.provider_paths | {self.api_owner},
                                                        *self.arguments),
                lambda: admission.recheck_provider_dependencies(
                    self.provider_paths | {self.api_owner}, before, *self.arguments)):
            with self.assertRaisesRegex(ValueError, 'API definition owner is not a provider dependency'):
                check()

    def test_forwarder_and_separate_owner_bytes_each_bound_before_and_after_scan(self):
        contract = self.git_fixture()
        before = admission.provider_dependencies(self.provider_paths, *self.arguments)
        for path in [*self.forwarders, *self.task_owners]:
            original = path.read_bytes()
            path.write_bytes(original + b' changed')
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, 'working bytes'):
                    admission.repository_inputs(self.repo, contract)
                with self.assertRaisesRegex(ValueError, 'repository dependency drift'):
                    admission.recheck_provider_dependencies(self.provider_paths, before, *self.arguments)
            path.write_bytes(original)

    def test_directory_membership_never_admits_unreviewed_runtime_wrapper(self):
        extra = save(self.repo / 'compat/native-runtime/include/linux/extra.h', b'not declared')
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            admission.provider_dependencies(self.provider_paths | {extra}, *self.arguments)

    def test_api_owner_and_forwarder_symlinks_do_not_replace_reviewed_regular_files(self):
        contract = self.git_fixture()
        for path in [self.api_owner, self.forwarders[0], self.task_owners[0]]:
            raw = path.read_bytes()
            target = save(self.base / ('external-' + path.name), raw)
            path.unlink()
            path.symlink_to(target)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'aliases'):
                admission.repository_inputs(self.repo, contract)
            path.unlink()
            path.write_bytes(raw)

    def test_old_fd_policy_and_new_anon_file_policies_remain_independent(self):
        core = {'patched_inputs': self.patched}
        self.assertEqual(admission.provider_header_policy(core, self.reviewed(admission.CONTRACT_PATH)),
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])
        for relative in (admission.ANON_CONTRACT_PATH, admission.FILE_CONTRACT_PATH):
            with self.subTest(relative=relative):
                self.assertEqual(admission.provider_header_policy(core, self.reviewed(relative)),
                                 ['sys/sys/file.h'])
        proof = admission.provider_dependencies(self.provider_paths, *self.arguments)
        admission.require_provider_headers(proof, self.repo, core, self.reviewed())
        with self.assertRaisesRegex(ValueError, 'did not consume'):
            admission.require_provider_headers(proof, self.repo, core,
                                               self.reviewed(admission.CONTRACT_PATH))

    def test_original_filedesc_stays_forbidden_despite_file_only_required_subset(self):
        before = admission.provider_dependencies(self.provider_paths, *self.arguments)
        original = save(self.source / 'sys/sys/filedesc.h', b'original native FD header')
        with self.assertRaisesRegex(ValueError, 'original version of patched input'):
            admission.provider_dependencies(self.provider_paths | {original}, *self.arguments)
        with self.assertRaisesRegex(ValueError, 'original version of patched input'):
            admission.recheck_provider_dependencies(self.provider_paths | {original}, before,
                                                    *self.arguments)

    def test_core_lockstat_is_rechecked_without_claiming_provider_consumption(self):
        core = self.core_fixture()
        proof = admission.provider_dependencies(self.provider_paths, *self.arguments)
        admission.require_provider_headers(proof, self.repo, core, self.reviewed())
        self.assertNotIn(str(self.lockstat), proof)
        self.assertEqual(self.verify_core(), core)
        self.lockstat.write_bytes(b'unused provider configuration drift')
        with self.assertRaisesRegex(ValueError, 'configuration bytes differ'):
            self.verify_core()
        with self.assertRaisesRegex(ValueError, 'configuration bytes differ'):
            admission.recheck_provider_dependencies(self.provider_paths, proof, *self.arguments)


if __name__ == '__main__':
    unittest.main()
