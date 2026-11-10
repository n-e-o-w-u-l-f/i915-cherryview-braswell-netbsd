"""Focused F33 provider-input admission tests; never invoke a compiler or preprocessor."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_provider_inputs as admission
from native_source_archive import (
    ARCHIVE_SHA256, PIN, bind_dependencies, declared_configuration_inputs,
    selected_generated_configuration, snapshot_prior_artifacts)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


class ProviderInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='f33-input-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.repo = self.base / 'repository'
        self.source = self.base / 'native'
        self.obj = self.base / 'obj'
        self.core_path = self.base / 'core' / 'status.json'
        self.overlay = self.core_path.parent / 'source'
        self.tools_root = self.base / 'tools'
        for path in (self.repo, self.source, self.obj, self.overlay, self.tools_root):
            path.mkdir(parents=True)
        self.relative = 'compat/native-file/linux_fd.c'
        self.header = 'compat/native-file/include/linux/file_netbsd.h'
        self.unit = save(self.repo / self.relative, b'/* reviewed provider */\n')
        self.repo_header = save(self.repo / self.header, b'/* reviewed header */\n')
        self.repo_contract = {
            'provider_root': 'compat/native-file',
            'units': ['linux_fd.c'],
            'repository_include_roots': ['compat/native-file/include',
                                         'compat/native-mm/include',
                                         'compat/native-uio/include'],
            'native_include_roots': ['sys/external/bsd/common/include',
                                     'sys/external/bsd/drm2/include'],
            'repository_inputs': {
                self.relative: dict(role='translation_unit',
                                    blob=blob(self.unit.read_bytes()),
                                    sha256=sha(self.unit.read_bytes())),
                self.header: dict(role='file_header',
                                  blob=blob(self.repo_header.read_bytes()),
                                  sha256=sha(self.repo_header.read_bytes()))}}
        for name in self.repo_contract['repository_include_roots']:
            (self.repo / name).mkdir(parents=True, exist_ok=True)
        for name in self.repo_contract['native_include_roots']:
            (self.source / name).mkdir(parents=True, exist_ok=True)
        self.repo_bindings = {
            str(self.repo / name): dict(kind='repository', relative=name, **row)
            for name, row in self.repo_contract['repository_inputs'].items()}
        self.native = save(self.source / 'sys/sys/types.h', b'/* native baseline */\n')
        self.original = save(self.source / 'sys/sys/file.h', b'/* original FILE */\n')
        self.patched_file = save(self.overlay / 'sys/sys/file.h', b'/* patched FILE */\n')
        self.patched_desc = save(self.overlay / 'sys/sys/filedesc.h', b'/* patched FD */\n')
        self.patched = {str(p.relative_to(self.overlay)): sha(p.read_bytes())
                        for p in (self.patched_file, self.patched_desc)}
        self.opt = save(self.obj / 'opt_compat_netbsd32.h', b'#define COMPAT_NETBSD32 1\n')
        self.lockstat = save(self.obj / 'lockstat.h', b'#define NLOCKSTAT 1\n')
        self.declared = {'lockstat.h': sha(self.lockstat.read_bytes())}
        self.provider_paths = {self.unit, self.repo_header, self.native,
                               self.patched_file, self.patched_desc, self.opt}
        self.arguments = (self.repo, self.repo_bindings, self.source, self.overlay,
                          self.obj, self.patched, self.declared)

    def git_fixture(self):
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for arguments in (['init', '-q'], ['add', '--', self.relative, self.header],
                          ['commit', '-q', '-m', 'isolated selected inputs']):
            subprocess.run(['git', '-C', str(self.repo)] + arguments, env=environment,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.repo_contract['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'],
            env=environment).decode().strip()
        return self.repo_contract

    def core_fixture(self):
        make = save(self.tools_root / 'bin/make', b'fixture make\n')
        compiler = save(self.tools_root / 'bin/compiler', b'fixture compiler\n')
        self.tools = dict(root=self.tools_root, make=make, compiler=compiler)
        self.patch = save(self.base / 'selected.patch', b'fixture patch\n')
        self.selected_contract = save(
            self.base / 'selected.json',
            json.dumps({'generated_configuration': self.declared}, sort_keys=True).encode())
        chain = [dict(patch=str(self.patch), patch_sha256=sha(self.patch.read_bytes()),
                      contract=str(self.selected_contract),
                      contract_sha256=sha(self.selected_contract.read_bytes()))]
        declared, origins = selected_generated_configuration(chain, True)
        dependencies = bind_dependencies(
            {self.native, self.patched_file, self.patched_desc, self.opt, self.lockstat},
            self.source, self.overlay, self.obj, self.patched, declared)
        objects = {}
        for unit in ('sys_generic', 'kern_descrip', 'netbsd32_ioctl'):
            output = save(self.core_path.parent / (unit + '.o'), ('fixture ' + unit).encode())
            save(self.obj / (unit + '.o'), ('prior ' + unit).encode())
            objects[unit] = dict(sha256=sha(output.read_bytes()),
                                headers_sha256={str(self.patched_file): self.patched['sys/sys/file.h']},
                                dependency_proof=copy.deepcopy(dependencies))
        makefile = save(self.obj / 'Makefile', b'fixture configured Makefile\n')
        kernel = save(self.obj / 'netbsd', b'fixture prior kernel\n')
        core = dict(
            state='PASS', stage='COMPLETE', netbsd_pin=PIN, toolchain=str(self.tools_root),
            native_tool_sha256={str(p): sha(p.read_bytes()) for p in (make, compiler)},
            patched_inputs=self.patched, patch_chain=chain,
            declared_generated_configuration=declared,
            generated_configuration_contracts=origins,
            declared_generated_configuration_inputs=declared_configuration_inputs(self.obj, declared),
            generated_configuration_sha256={str(self.opt): sha(self.opt.read_bytes())},
            source_provenance=dict(mode='ARCHIVE_USED_SUBSET', netbsd_pin=PIN,
                                   archive_sha256=ARCHIVE_SHA256,
                                   verified_source_members={'sys/sys/types.h': sha(self.native.read_bytes())}),
            objects=objects,
            precompile_dependencies={name: copy.deepcopy(dependencies) for name in objects},
            prior_artifacts=snapshot_prior_artifacts(self.obj, objects),
            configured_makefile_sha256=sha(makefile.read_bytes()),
            prior_kernel_sha256=sha(kernel.read_bytes()))
        self.core_contract = {}
        self.write_core(core)
        return core

    def write_core(self, core):
        raw = json.dumps(core, sort_keys=True).encode()
        save(self.core_path, raw)
        self.core_contract['core_status_sha256'] = sha(raw)

    def verify_core(self, before=None):
        return admission.verify_core(self.core_path, self.core_contract, self.source,
                                     self.obj, self.tools, core=before)

    def test_reviewed_real_contract_has_fixed_seven_identities_and_roles(self):
        contract = admission.load_contract(admission.REPOSITORY / admission.CONTRACT_PATH)
        self.assertEqual(admission.CONTRACT_SHA256,
                         'f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3')
        self.assertEqual(contract['repository_commit'], '493c85d5ba0e3aabc32a61792f980736a6c1693f')
        expected = [
            ('compat/native-file/linux_fd.c', 'translation_unit', '2dc8720c9a33355e930e280cc98d4e8016002cb0', '4a112f9f174b41851be56db6ea9b974c40dd9c3564f5a830cc362e8725d15591'),
            ('compat/native-file/include/linux/file_api_netbsd.h', 'file_header', '271684bd9e980ab9e5bfb9847ff5ecc13a65357b', '69ff9305b30b31a94658dd6d13b171c402feef1431f0ab2d7675b4b0eaa41850'),
            ('compat/native-file/include/linux/file_netbsd.h', 'file_header', 'e919f2f6a03bd58b85a40cea89ded14242983d2b', 'c18fde8fff1b499d751cd3dd2b5bad10070ac67c4b0a680bcbe99976537d2c1c'),
            ('compat/native-file/include/linux/fs_netbsd.h', 'file_header', '2f304f344fdaf92fb0c412a140c27837fc1d3163', 'd416cd53ad84e1195173ff0361a65a7b624ddb0a0f14d1f1cd6741642514f229'),
            ('compat/native-file/include/linux/file_ref_netbsd.h', 'file_header', '3b6c5b499380b6374ca9e7540e89d8cc55362678', '165ebc64c91141db3215eb9d13dced5c8902100e92760be6301b34d9a8a3cba8'),
            ('compat/native-mm/include/linux/mm_abi_types_netbsd.h', 'mm_abi_header', '034e1034ba925299a14bf85f6defd37998023bf3', 'c7d01e8f97fa6f38eb4c4663346087f87b34a4e0731cff4ddd417d5b6ad19054'),
            ('compat/native-uio/include/linux/kiocb_netbsd.h', 'uio_header', 'e54e8be249a3975c91fd5710ea024da817571df9', '4a84beb2739ef38ab0911c94511c541c6995384111724caae5a92b88d4c8659a')]
        self.assertEqual(contract['repository_inputs'],
                         {name: dict(role=role, blob=identity, sha256=digest)
                          for name, role, identity, digest in expected})
        self.assertEqual(contract['core_status_sha256'],
                         'd1dbd25236da2d7825a432734ff8807467bd2f135348b436d1b86251c0562794')

    def fixture_contract(self, raw=None):
        if raw is None:
            raw = json.dumps(dict(netbsd_pin=PIN, archive_sha256=ARCHIVE_SHA256)).encode()
        path = save(self.repo / admission.CONTRACT_PATH, raw)
        return path, raw

    def test_contract_rejects_modified_bytes_and_wrong_location(self):
        path, raw = self.fixture_contract()
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            admission.load_contract(path, self.repo)
        with mock.patch.object(admission, 'CONTRACT_SHA256', sha(raw)):
            other = save(self.repo / 'other.json', raw)
            with self.assertRaisesRegex(ValueError, 'source-owned'):
                admission.load_contract(other, self.repo)

    def test_contract_rejects_symlink_even_with_identical_target(self):
        path, raw = self.fixture_contract()
        target = save(self.base / 'target.json', raw)
        path.unlink()
        path.symlink_to(target)
        with mock.patch.object(admission, 'CONTRACT_SHA256', sha(raw)):
            with self.assertRaisesRegex(ValueError, 'source-owned'):
                admission.load_contract(path, self.repo)

    def test_contract_rejects_duplicate_json_keys_and_foreign_pin(self):
        for raw, message in (
                (('{"netbsd_pin":"' + PIN + '","netbsd_pin":"' + PIN +
                  '","archive_sha256":"' + ARCHIVE_SHA256 + '"}').encode(), 'duplicate'),
                (json.dumps(dict(netbsd_pin='0' * 40, archive_sha256=ARCHIVE_SHA256)).encode(), 'archive identity')):
            with self.subTest(message=message):
                path, raw = self.fixture_contract(raw)
                with mock.patch.object(admission, 'CONTRACT_SHA256', sha(raw)):
                    with self.assertRaisesRegex(ValueError, message):
                        admission.load_contract(path, self.repo)

    def test_repository_commit_blob_and_working_bytes_agree(self):
        contract = self.git_fixture()
        self.assertEqual(admission.repository_inputs(self.repo, contract), self.repo_bindings)

    def test_dirty_selected_input_rejected_but_unselected_file_not_trusted(self):
        contract = self.git_fixture()
        save(self.repo / 'unselected', b'unrelated')
        self.assertEqual(admission.repository_inputs(self.repo, contract), self.repo_bindings)
        self.unit.write_bytes(self.unit.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'working bytes'):
            admission.repository_inputs(self.repo, contract)

    def test_selected_blob_sha_and_commit_path_each_required(self):
        contract = self.git_fixture()
        for key, value, message in (
                ('sha256', '0' * 64, 'working bytes'),
                ('blob', '0' * 40, 'working bytes')):
            changed = copy.deepcopy(contract)
            changed['repository_inputs'][self.relative][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                admission.repository_inputs(self.repo, changed)
        moved = copy.deepcopy(contract)
        alias = 'compat/native-file/moved.c'
        save(self.repo / alias, self.unit.read_bytes())
        moved['repository_inputs'] = {alias: contract['repository_inputs'][self.relative]}
        with self.assertRaisesRegex(ValueError, 'commit/path/blob'):
            admission.repository_inputs(self.repo, moved)

    def test_wrong_repository_cannot_supply_commit(self):
        contract = self.git_fixture()
        foreign = self.base / 'foreign'
        foreign.mkdir()
        for relative in contract['repository_inputs']:
            save(foreign / relative, (self.repo / relative).read_bytes())
        subprocess.run(['git', '-C', str(foreign), 'init', '-q'], check=True)
        with self.assertRaises(subprocess.CalledProcessError):
            admission.repository_inputs(foreign, contract)

    def test_repository_escape_and_selected_symlink_rejected(self):
        contract = self.git_fixture()
        changed = copy.deepcopy(contract)
        changed['repository_inputs'] = {'../escape.c': contract['repository_inputs'][self.relative]}
        with self.assertRaises(ValueError):
            admission.repository_inputs(self.repo, changed)
        original = save(self.base / 'real.c', self.unit.read_bytes())
        self.unit.unlink()
        self.unit.symlink_to(original)
        with self.assertRaisesRegex(ValueError, 'aliases'):
            admission.repository_inputs(self.repo, contract)

    def test_repository_parent_symlink_rejected(self):
        contract = self.git_fixture()
        directory = self.repo_header.parent
        moved = directory.with_name('actual')
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliases'):
            admission.repository_inputs(self.repo, contract)

    def test_inherited_git_selectors_cannot_redirect_identity_reads(self):
        contract = self.git_fixture()
        poison = dict(GIT_DIR='/nonexistent', GIT_WORK_TREE='/nonexistent',
                      GIT_INDEX_FILE='/nonexistent', GIT_COMMON_DIR='/nonexistent',
                      GIT_REPLACE_REF_BASE='refs/poison', GIT_CONFIG_COUNT='1',
                      GIT_CONFIG_KEY_0='core.bare', GIT_CONFIG_VALUE_0='true')
        with mock.patch.dict(os.environ, poison):
            self.assertEqual(admission.repository_inputs(self.repo, contract), self.repo_bindings)
            environment = admission.git_environment()
        self.assertEqual({name for name in environment if name.startswith('GIT_')},
                         {'GIT_NO_REPLACE_OBJECTS', 'GIT_NO_LAZY_FETCH',
                          'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL'})

    def test_include_roles_exact_order_and_unit_selection(self):
        expected = ([self.repo / name for name in self.repo_contract['repository_include_roots']] +
                    [self.source / name for name in self.repo_contract['native_include_roots']])
        provider = self.repo / 'compat/native-file'
        self.assertEqual(admission.selected_inputs(self.repo_contract, self.repo, self.source,
                                                  provider, ['linux_fd.c'], []), expected)
        for root, units, includes in (
                (self.repo, ['linux_fd.c'], []),
                (provider, ['linux_file.c'], []),
                (provider, ['linux_fd.c', 'other.c'], []),
                (provider, ['linux_fd.c'], list(reversed(expected)))):
            with self.subTest(root=root, units=units, includes=includes):
                with self.assertRaises(ValueError):
                    admission.selected_inputs(self.repo_contract, self.repo, self.source,
                                              root, units, includes)

    def test_include_root_symlink_rejected(self):
        root = self.source / self.repo_contract['native_include_roots'][0]
        actual = root.with_name('actual')
        root.rename(actual)
        root.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliased'):
            admission.selected_inputs(self.repo_contract, self.repo, self.source,
                                      self.repo / 'compat/native-file', ['linux_fd.c'], [])

    def test_core_positive_revalidates_three_owners_and_unused_lockstat(self):
        core = self.core_fixture()
        self.assertEqual(self.verify_core(), core)
        proof = admission.provider_dependencies(self.provider_paths, *self.arguments)
        admission.require_provider_headers(proof, self.repo, core)
        self.assertNotIn(str(self.lockstat), proof)
        self.assertIn(str(self.lockstat), core['objects']['sys_generic']['dependency_proof'])
        expectations = admission.native_archive_expectations(core, proof)
        self.assertEqual(expectations, {'sys/sys/types.h': sha(self.native.read_bytes())})

    def test_exact_core_receipt_bytes_required(self):
        self.core_fixture()
        self.core_path.write_bytes(self.core_path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'full F32 core receipt'):
            self.verify_core()

    def test_core_state_owner_set_and_provenance_required(self):
        original = self.core_fixture()
        mutations = (
            lambda c: c.update(state='RUNNING'),
            lambda c: c.update(stage='ADMITTED'),
            lambda c: c['objects'].pop('netbsd32_ioctl'),
            lambda c: c['source_provenance'].update(mode='GIT_CLEAN'),
            lambda c: c['source_provenance'].update(archive_sha256='0' * 64))
        for mutate in mutations:
            changed = copy.deepcopy(original)
            mutate(changed)
            self.write_core(changed)
            with self.subTest(core=changed), self.assertRaises(ValueError):
                self.verify_core()

    def test_core_reparsed_document_must_equal_frozen_document(self):
        core = self.core_fixture()
        altered = copy.deepcopy(core)
        altered['untrusted_note'] = 'changed'
        self.write_core(altered)
        with self.assertRaisesRegex(ValueError, 'receipt changed'):
            self.verify_core(core)

    def test_core_rejects_overlay_patch_contract_and_source_drift(self):
        self.core_fixture()
        for path in (self.patched_file, self.patch, self.selected_contract, self.native):
            original = path.read_bytes()
            path.write_bytes(original + b' drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            path.write_bytes(original)

    def test_core_rejects_opt_declared_and_tool_drift(self):
        self.core_fixture()
        for path in (self.opt, self.lockstat, self.tools['make'], self.tools['compiler']):
            original = path.read_bytes()
            path.write_bytes(original + b' drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            path.write_bytes(original)

    def test_core_rejects_object_makefile_and_prior_kernel_drift(self):
        self.core_fixture()
        for path in (self.core_path.parent / 'netbsd32_ioctl.o', self.obj / 'Makefile',
                     self.obj / 'netbsd'):
            original = path.read_bytes()
            path.write_bytes(original + b' drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            path.write_bytes(original)

    def test_core_freezes_old_artifact_bytes_and_absence(self):
        self.core_fixture()
        for path in (self.obj / 'sys_generic.o', self.obj / 'kern_descrip.d',
                     self.obj / 'netbsd32_ioctl.su'):
            existed = path.exists()
            original = path.read_bytes() if existed else None
            path.write_bytes(b'drift or unexpected creation')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            if existed:
                path.write_bytes(original)
            else:
                path.unlink()

    def test_core_rejects_dependency_proof_set_or_hash_drift(self):
        original = self.core_fixture()
        for change_scan in (False, True):
            changed = copy.deepcopy(original)
            proof = changed['objects']['sys_generic']['dependency_proof']
            proof[str(self.native)]['sha256'] = '0' * 64
            if change_scan:
                changed['precompile_dependencies']['sys_generic'] = copy.deepcopy(proof)
            self.write_core(changed)
            with self.subTest(change_scan=change_scan), self.assertRaises(ValueError):
                self.verify_core()

    def test_provider_dependency_kinds_are_separate_and_exact(self):
        proof = admission.provider_dependencies(self.provider_paths, *self.arguments)
        self.assertEqual({row['kind'] for row in proof.values()},
                         {'repository', 'archive', 'patched', 'generated_configuration'})
        self.assertEqual(proof[str(self.unit)]['blob'], blob(self.unit.read_bytes()))

    def test_directory_membership_does_not_admit_unreviewed_repository_header(self):
        unreviewed = save(self.repo / 'compat/native-file/include/linux/extra.h', b'extra')
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            admission.provider_dependencies(self.provider_paths | {unreviewed}, *self.arguments)

    def test_original_patched_header_and_foreign_native_dependency_rejected(self):
        foreign = save(self.base / 'foreign.h', b'foreign')
        for path in (self.original, foreign):
            with self.subTest(path=path), self.assertRaises(ValueError):
                admission.provider_dependencies(self.provider_paths | {path}, *self.arguments)

    def test_repository_dependency_drift_after_scan_rejected(self):
        before = admission.provider_dependencies(self.provider_paths, *self.arguments)
        self.repo_header.write_bytes(b'changed after -M')
        with self.assertRaisesRegex(ValueError, 'repository dependency drift'):
            admission.recheck_provider_dependencies(self.provider_paths, before, *self.arguments)

    def test_post_md_set_native_and_config_drift_rejected(self):
        before = admission.provider_dependencies(self.provider_paths, *self.arguments)
        extra = save(self.source / 'sys/sys/extra.h', b'new dependency')
        with self.assertRaisesRegex(ValueError, 'differ from independent scan'):
            admission.recheck_provider_dependencies(self.provider_paths | {extra}, before, *self.arguments)
        with self.assertRaisesRegex(ValueError, 'differ from independent scan'):
            admission.recheck_provider_dependencies(self.provider_paths - {self.opt}, before, *self.arguments)
        for path in (self.native, self.opt, self.patched_desc):
            original = path.read_bytes()
            path.write_bytes(original + b' drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                admission.recheck_provider_dependencies(self.provider_paths, before, *self.arguments)
            path.write_bytes(original)

    def test_declared_lockstat_revalidated_without_requiring_provider_consumption(self):
        before = admission.provider_dependencies(self.provider_paths, *self.arguments)
        self.lockstat.write_bytes(b'changed unused core configuration')
        with self.assertRaisesRegex(ValueError, 'configuration bytes differ'):
            admission.recheck_provider_dependencies(self.provider_paths, before, *self.arguments)

    def test_missing_patched_native_header_cannot_pass_provider_admission(self):
        proof = admission.provider_dependencies(self.provider_paths - {self.patched_desc},
                                               *self.arguments)
        with self.assertRaisesRegex(ValueError, 'patched native FILE headers'):
            admission.require_provider_headers(proof, self.repo, {'patched_inputs': self.patched})

    def test_archive_expectations_exclude_repository_and_detect_native_conflict(self):
        proof = admission.provider_dependencies(self.provider_paths, *self.arguments)
        core = {'source_provenance': {'verified_source_members':
                                     {'sys/sys/types.h': sha(self.native.read_bytes())}}}
        self.assertEqual(admission.native_archive_expectations(core, proof),
                         core['source_provenance']['verified_source_members'])
        core['source_provenance']['verified_source_members']['sys/sys/types.h'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'changed across owners'):
            admission.native_archive_expectations(core, proof)

    def test_empty_dependency_set_rejected(self):
        with self.assertRaisesRegex(ValueError, 'empty provider'):
            admission.provider_dependencies(set(), *self.arguments)


if __name__ == '__main__':
    unittest.main()
