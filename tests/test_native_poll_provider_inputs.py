"""F46 Poll input/provenance tests; private files and Git only, no native tools."""
import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import test_native_wait_provider_inputs as wait_fixture
from test_native_provider_inputs import blob, save, sha

admission = wait_fixture.admission
REPOSITORY = wait_fixture.REPOSITORY
POLL_UNIT = 'compat/native-file/linux_poll_owner.c'
POLL_BODY = 'compat/native-file/linux_poll.c'
API_HEADER = 'compat/native-runtime/task/task_entry_netbsd.h'
API_OWNER = 'compat/native-entry/task_entry.inc'
WAIT_BODY = 'compat/native-runtime/wait-f43/linux_wait.c'
WAIT_HEADER = 'compat/native-runtime/wait-f43/include/linux/wait.h'
COMPILED = (
    POLL_UNIT, POLL_BODY,
    'compat/native-file/include/linux/poll_netbsd.h',
    'compat/native-file/include/linux/file_netbsd.h',
    'compat/native-file/include/linux/file_api_netbsd.h',
    'compat/native-file/include/linux/fs_netbsd.h',
    'compat/native-file/include/linux/file_ref_netbsd.h',
    'compat/native-mm/include/linux/mm_abi_types_netbsd.h',
    'compat/native-uio/include/linux/kiocb_netbsd.h',
    API_HEADER, WAIT_HEADER,
    'compat/native-runtime/include/linux/sched.h',
    'compat/native-runtime/include/linux/task_netbsd.h',
    'compat/native-runtime/include/linux/raw_spinlock.h',
    'compat/native-runtime/task/sched.h',
    'compat/native-runtime/task/task_netbsd.h',
    'compat/linux/raw_spinlock.h')
PROOFS = wait_fixture.PROOFS + (WAIT_BODY, API_OWNER)
OLD_SELECTIONS = wait_fixture.OLD_SELECTIONS + (
    ('WAIT_CONTRACT_PATH', 'WAIT_CONTRACT_SHA256'),)


def private_commit(owner):
    environment = admission.git_environment()
    environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                       GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
    for arguments in (['init', '-q'], ['add', '--', *owner.contract['repository_inputs']],
                      ['commit', '-q', '--allow-empty', '-m', 'private Poll input binding']):
        subprocess.run(['git', '-C', str(owner.repo)] + arguments, env=environment,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    commit = subprocess.check_output(['git', '-C', str(owner.repo), 'rev-parse', 'HEAD'],
                                     env=environment).decode().strip()
    owner.contract['repository_commit'] = commit
    return commit


@contextlib.contextmanager
def referenced_wait(owner, mutate=None):
    """Create real private Git authority and shadow only the fixture's fixed Wait pin."""
    commit = private_commit(owner)
    document = copy.deepcopy(admission.load_contract(REPOSITORY / admission.WAIT_CONTRACT_PATH))
    document['repository_commit'] = commit
    document['generation_provenance_sha256'] = owner.contract['generation_provenance_sha256']
    for name, row in document['repository_inputs'].items():
        row.update(blob=owner.contract['repository_inputs'][name]['blob'],
                   sha256=owner.contract['repository_inputs'][name]['sha256'])
    if mutate:
        mutate(document)
    raw = (json.dumps(document, indent=2) + '\n').encode()
    path = owner.repo / admission.WAIT_CONTRACT_PATH
    original = path.read_bytes() if path.exists() else None
    save(path, raw)
    previous = owner.contract['wait_contract_sha256']
    owner.contract['wait_contract_sha256'] = sha(raw)
    with mock.patch.object(admission, 'WAIT_CONTRACT_SHA256', sha(raw)):
        try:
            yield document
        finally:
            owner.contract['wait_contract_sha256'] = previous
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)


class PollFixture(wait_fixture.WaitFixture):
    def setUp(self):
        wait_fixture.WaitFixture.setUp(self)
        self.contract = copy.deepcopy(admission.load_contract(REPOSITORY / admission.POLL_CONTRACT_PATH))
        for relative in self.contract['repository_inputs']:
            save(self.repo / relative, (REPOSITORY / relative).read_bytes())
        self.bindings = {
            str(self.repo / relative): dict(kind='repository', relative=relative, **row)
            for relative, row in self.contract['repository_inputs'].items()}
        for name in self.contract['repository_include_roots']:
            (self.repo / name).mkdir(parents=True, exist_ok=True)
        self.unit = self.repo / POLL_UNIT
        self.compiled_paths = {self.repo / name for name in COMPILED}
        self.paths = self.compiled_paths | {self.native, self.opt, self.patched_file}
        self.arguments = (self.repo, self.bindings, self.source, self.overlay,
                          self.obj, self.patched, self.declared)

    def generation(self):
        with referenced_wait(self):
            return admission.verify_poll_generation(
                self.repo, self.contract, self.bindings, admission.POLL_CONTRACT_SHA256)


class PollProviderInputTests(unittest.TestCase, PollFixture):
    setUp = PollFixture.setUp

    def test_exact_seventh_profile_has_twenty_six_rows_and_seventeen_consumables(self):
        self.assertEqual(admission.POLL_CONTRACT_PATH,
                         'compat/native-file/provider-inputs-f46-poll.json')
        raw = (REPOSITORY / admission.POLL_CONTRACT_PATH).read_bytes()
        self.assertEqual(sha(raw), admission.POLL_CONTRACT_SHA256)
        self.assertEqual(set(self.contract['repository_inputs']), set(COMPILED) | set(PROOFS))
        self.assertEqual(len(COMPILED), 17)
        self.assertEqual(len(PROOFS), 9)
        self.assertEqual(admission.poll_input_policy(self.contract,
                         admission.POLL_CONTRACT_SHA256), sorted(COMPILED))
        self.assertEqual(self.contract['repository_inputs'][API_OWNER]['role'], 'api_definition_owner')
        self.assertEqual(self.contract['repository_inputs'][WAIT_BODY]['role'], 'generation_proof_owner')
        self.assertEqual(self.contract['required_patched_headers'], ['sys/sys/file.h'])

    def test_wrapper_exposes_existing_declaration_before_unchanged_poll_body(self):
        raw = (REPOSITORY / POLL_UNIT).read_text()
        includes = [line.strip() for line in raw.splitlines() if line.lstrip().startswith('#include')]
        self.assertEqual(includes, ['#include "../native-runtime/task/task_entry_netbsd.h"',
                                    '#include "linux_poll.c"'])
        self.assertNotIn('linux_task_entry_enter(', raw)
        self.assertNotIn('linux_task_entry_leave(', raw)
        self.assertNotIn('task_entry.inc', raw)
        header = (REPOSITORY / API_HEADER).read_text()
        owner = (REPOSITORY / API_OWNER).read_text()
        body = (REPOSITORY / POLL_BODY).read_text()
        self.assertIn('int linux_task_entry_enter(struct task_struct **);', header)
        self.assertIn('void linux_task_entry_leave(struct task_struct **);', header)
        self.assertIn('linux_task_entry_enter(struct task_struct **handle)', owner)
        self.assertIn('linux_task_entry_leave(struct task_struct **handle)', owner)
        self.assertIn('linux_task_entry_enter(&task)', body)
        self.assertIn('linux_task_entry_leave(&task)', body)
        self.assertNotIn('int linux_task_entry_enter(', body)
        self.assertEqual(sha((REPOSITORY / POLL_BODY).read_bytes()),
                         self.contract['repository_inputs'][POLL_BODY]['sha256'])

    def test_exact_narrow_include_roots_and_only_wrapper_unit_are_selected(self):
        roots = ['compat/native-file/include', 'compat/native-mm/include',
                 'compat/native-uio/include', 'compat/native-runtime/wait-f43/include',
                 'compat/native-runtime/include']
        self.assertEqual(self.contract['repository_include_roots'], roots)
        expected = [self.repo / name for name in roots] + [
            self.source / name for name in self.contract['native_include_roots']]
        provider = self.repo / self.contract['provider_root']
        self.assertEqual(admission.selected_inputs(self.contract, self.repo, self.source,
                         provider, ['linux_poll_owner.c'], []), expected)
        for units, includes in ((['linux_poll.c'], []),
                                (['linux_poll_owner.c', 'linux_poll.c'], []),
                                (['linux_poll_owner.c'], expected[::-1]),
                                (['linux_poll_owner.c'], [self.repo / 'compat'])):
            with self.subTest(units=units, includes=includes), self.assertRaises(ValueError):
                admission.selected_inputs(self.contract, self.repo, self.source,
                                          provider, units, includes)

    def test_crossed_digest_roles_units_and_root_shape_are_rejected(self):
        for digest in (None, '0' * 64, admission.WAIT_CONTRACT_SHA256,
                       admission.FILE_CONTRACT_SHA256):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                admission.poll_input_policy(self.contract, digest)
        changes = (
            lambda c: c.update(schema=True),
            lambda c: c.update(provider_root='compat/native-runtime/task'),
            lambda c: c.update(units=['linux_poll.c']),
            lambda c: c.update(required_patched_headers=[]),
            lambda c: c.update(repository_include_roots=c['repository_include_roots'][::-1]),
            lambda c: c.update(native_include_roots=c['native_include_roots'][::-1]),
            lambda c: c.update(linux_pin='0' * 40),
            lambda c: c.update(wait_contract_sha256='0' * 64),
            lambda c: c.update(generation_provenance_sha256='0' * 64),
            lambda c: c['repository_inputs'].pop(API_OWNER),
            lambda c: c['repository_inputs'][WAIT_BODY].update(role='translation_unit'),
            lambda c: c['repository_inputs'][API_OWNER].update(role='task_fragment'))
        for index, mutate in enumerate(changes):
            changed = copy.deepcopy(self.contract)
            mutate(changed)
            with self.subTest(index=index), self.assertRaises(ValueError):
                admission.poll_input_policy(changed, admission.POLL_CONTRACT_SHA256)

    def test_seventh_profile_preserves_all_six_fixed_source_owned_selections(self):
        for path_name, hash_name in OLD_SELECTIONS + (('POLL_CONTRACT_PATH', 'POLL_CONTRACT_SHA256'),):
            relative = getattr(admission, path_name)
            path = save(self.repo / relative, (REPOSITORY / relative).read_bytes())
            with self.subTest(relative=relative):
                self.assertEqual(admission.reviewed_contract_sha256(path, self.repo),
                                 getattr(admission, hash_name))
                self.assertEqual(admission.load_contract(path, self.repo),
                                 admission.load_contract(REPOSITORY / relative))
        core = {'patched_inputs': self.patched}
        self.assertEqual(admission.provider_header_policy(core, self.contract,
                         admission.POLL_CONTRACT_SHA256), ['sys/sys/file.h'])
        expected = [2, 1, 1, 0, 0, 0]
        for (path_name, hash_name), count in zip(OLD_SELECTIONS, expected):
            contract = admission.load_contract(REPOSITORY / getattr(admission, path_name))
            digest = getattr(admission, hash_name)
            with self.subTest(path=path_name):
                self.assertEqual(admission.poll_input_policy(contract, digest), [])
                self.assertEqual(admission.verify_poll_generation(self.repo, contract, {}, digest), {})
                self.assertEqual(len(admission.provider_header_policy(core, contract, digest)), count)

    def test_contract_crossed_bytes_unknown_path_and_symlink_are_rejected(self):
        path = self.repo / admission.POLL_CONTRACT_PATH
        for path_name, unused in OLD_SELECTIONS:
            save(path, (REPOSITORY / getattr(admission, path_name)).read_bytes())
            with self.subTest(path=path_name), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)
        raw = (REPOSITORY / admission.POLL_CONTRACT_PATH).read_bytes()
        target = save(self.repo / 'compat/native-file/unreviewed-poll.json', raw)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(target, self.repo)
        path.unlink()
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.load_contract(path, self.repo)

    def test_each_consumed_input_is_required_in_scan_and_actual_md_proof(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        admission.require_poll_inputs(before, self.repo, self.contract, admission.POLL_CONTRACT_SHA256)
        for name in COMPILED:
            paths = self.paths - {self.repo / name}
            subset = admission.provider_dependencies(paths, *self.arguments)
            with self.subTest(name=name, phase='M'), self.assertRaisesRegex(ValueError, 'required Poll input'):
                admission.require_poll_inputs(subset, self.repo, self.contract,
                                              admission.POLL_CONTRACT_SHA256)
            with self.subTest(name=name, phase='MD'), self.assertRaisesRegex(ValueError, 'actual provider dependencies'):
                admission.recheck_provider_dependencies(paths, before, *self.arguments)

    def test_each_proof_or_api_owner_is_forbidden_in_both_dependency_paths(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        for name in PROOFS:
            paths = self.paths | {self.repo / name}
            for label, check in (('M', lambda: admission.provider_dependencies(paths, *self.arguments)),
                                 ('MD', lambda: admission.recheck_provider_dependencies(paths, before,
                                                                                       *self.arguments))):
                with self.subTest(name=name, phase=label), self.assertRaisesRegex(ValueError,
                        '(generation proof|API definition) owner is not a provider dependency'):
                    check()

    def test_each_required_dependency_must_match_the_entire_bound_row(self):
        before = admission.provider_dependencies(self.paths, *self.arguments)
        for name in COMPILED:
            for field, value in (('sha256', '0' * 64), ('blob', '0' * 40),
                                 ('role', 'fixture'), ('relative', 'foreign')):
                changed = copy.deepcopy(before)
                changed[str(self.repo / name)][field] = value
                with self.subTest(name=name, field=field), self.assertRaisesRegex(ValueError,
                        'required Poll input'):
                    admission.require_poll_inputs(changed, self.repo, self.contract,
                                                  admission.POLL_CONTRACT_SHA256)

    def test_placeholder_wait_header_cannot_replace_recovered_wait(self):
        native = save(self.source / 'sys/external/bsd/drm2/include/linux/wait.h',
                      b'/* native placeholder fixture */\n')
        paths = self.paths - {self.repo / WAIT_HEADER} | {native}
        proof = admission.provider_dependencies(paths, *self.arguments)
        self.assertEqual(proof[str(native)]['kind'], 'archive')
        with self.assertRaisesRegex(ValueError, 'required Poll input'):
            admission.require_poll_inputs(proof, self.repo, self.contract,
                                          admission.POLL_CONTRACT_SHA256)

    def test_all_twenty_six_inputs_are_bound_to_real_private_git_and_dirty_proofs_fail(self):
        private_commit(self)
        self.assertEqual(admission.repository_inputs(self.repo, self.contract), self.bindings)
        for name in PROOFS:
            path = self.repo / name
            raw = path.read_bytes()
            path.write_bytes(raw + b' drift')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'working bytes'):
                admission.repository_inputs(self.repo, self.contract)
            path.write_bytes(raw)

    def test_git_environment_cannot_redirect_poll_identity_reads(self):
        private_commit(self)
        with mock.patch.dict(os.environ, GIT_DIR='/missing', GIT_WORK_TREE='/missing',
                             GIT_INDEX_FILE='/missing', GIT_COMMON_DIR='/missing',
                             GIT_REPLACE_REF_BASE='refs/forbidden'):
            self.assertEqual(admission.repository_inputs(self.repo, self.contract), self.bindings)

    def test_patched_file_header_and_complete_core_guards_are_retained(self):
        core = self.core_fixture()
        before = admission.provider_dependencies(self.paths, *self.arguments)
        admission.require_provider_headers(before, self.repo, core, self.contract,
                                           admission.POLL_CONTRACT_SHA256)
        no_file = admission.provider_dependencies(self.paths - {self.patched_file}, *self.arguments)
        with self.assertRaisesRegex(ValueError, 'patched native FILE headers'):
            admission.require_provider_headers(no_file, self.repo, core, self.contract,
                                               admission.POLL_CONTRACT_SHA256)
        self.assertEqual(self.verify_core(), core)
        for path in (self.lockstat, self.tools['compiler'], self.obj / 'Makefile'):
            raw = path.read_bytes()
            path.write_bytes(raw + b' core drift')
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify_core()
            path.write_bytes(raw)

    def test_alias_and_unreviewed_consumed_source_guards_remain_active(self):
        root = self.repo / self.contract['repository_include_roots'][0]
        moved = root.with_name('actual-include')
        root.rename(moved)
        root.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliased'):
            admission.selected_inputs(self.contract, self.repo, self.source,
                self.repo / self.contract['provider_root'], ['linux_poll_owner.c'], [])
        root.unlink()
        moved.rename(root)
        extra = save(self.repo / 'compat/native-file/include/linux/unreviewed_poll.h', b'fixture')
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            admission.provider_dependencies({extra}, *self.arguments)


if __name__ == '__main__':
    unittest.main()
