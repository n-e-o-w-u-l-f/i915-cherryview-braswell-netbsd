"""F41 exact wrapper/API/proof-owner admission; no native tools are invoked."""
import copy
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_provider_inputs as admission
import test_native_task_provider_inputs as task_fixture

IMPLEMENTATION = 'compat/native-runtime/task/linux_task.c'
WRAPPER = 'compat/native-runtime/task/linux_task_worker_owner.c'
API_HEADER = 'compat/native-runtime/task/task_worker_wake_netbsd.h'
PROOF_OWNERS = {'compat/native-runtime/worker/worker_header.inc',
                'compat/native-runtime/worker/worker.inc'}
INPUTS = task_fixture.INPUTS | {WRAPPER, API_HEADER} | PROOF_OWNERS


class TaskWorkerProviderInputTests(unittest.TestCase):
    def setUp(self):
        task_fixture.TaskProviderInputTests.setUp(self)
        self.old_task = self.contract
        self.contract = admission.load_contract(
            admission.REPOSITORY / admission.TASK_WORKER_CONTRACT_PATH)

    def policy(self, contract=None, identity=None):
        return admission.task_worker_input_policy(
            self.contract if contract is None else contract,
            admission.TASK_WORKER_CONTRACT_SHA256 if identity is None else identity)

    def proof(self):
        return {str(self.repo / name): dict(kind='repository', relative=name, **row)
                for name, row in self.contract['repository_inputs'].items()
                if row['role'] != 'api_definition_owner'}

    def test_fifth_contract_selects_only_wrapper_and_pins_fifteen_real_inputs(self):
        self.assertEqual(admission.TASK_WORKER_CONTRACT_PATH,
                         'compat/native-runtime/task/provider-inputs-f41-task-worker.json')
        self.assertEqual(self.contract['provider_root'], 'compat/native-runtime/task')
        self.assertEqual(self.contract['units'], ['linux_task_worker_owner.c'])
        self.assertEqual(self.contract['repository_include_roots'], ['compat/native-runtime/include'])
        self.assertEqual(self.contract['native_include_roots'], self.old_task['native_include_roots'])
        self.assertEqual(self.contract['required_patched_headers'], [])
        self.assertEqual(set(self.contract['repository_inputs']), INPUTS)
        rows = self.contract['repository_inputs']
        self.assertEqual(rows[WRAPPER]['role'], 'translation_unit')
        self.assertEqual(rows[IMPLEMENTATION]['role'], 'task_implementation_owner')
        self.assertEqual(rows[API_HEADER]['role'], 'task_worker_api_header')
        self.assertEqual({name for name, row in rows.items()
                          if row['role'] == 'api_definition_owner'}, PROOF_OWNERS)
        self.assertEqual(self.policy(), sorted([IMPLEMENTATION, API_HEADER]))
        self.assertEqual(admission.task_fragment_policy(
            self.contract, admission.TASK_WORKER_CONTRACT_SHA256), sorted(task_fixture.FRAGMENTS))

    def test_f39_guard_and_all_previous_manifest_identities_stay_exact(self):
        self.assertEqual(admission.TASK_CONTRACT_SHA256,
                         '5709061e886f4334c32b2485b98a38c8854ab3929e27ff41ce23192535c273df')
        self.assertEqual(self.old_task['units'], ['linux_task.c'])
        self.assertEqual(set(self.old_task['repository_inputs']), task_fixture.INPUTS)
        self.assertEqual(admission.task_fragment_policy(self.old_task, admission.TASK_CONTRACT_SHA256),
                         sorted(task_fixture.FRAGMENTS))
        for contract, identity in ((self.contract, admission.TASK_CONTRACT_SHA256),
                                   (self.old_task, admission.TASK_WORKER_CONTRACT_SHA256)):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                admission.provider_header_policy(self.core, contract, identity)
        self.assertEqual(self.policy(self.old_task, admission.TASK_CONTRACT_SHA256), [])
        for name, row in self.old_task['repository_inputs'].items():
            self.assertEqual(self.contract['repository_inputs'][name]['blob'], row['blob'])
            self.assertEqual(self.contract['repository_inputs'][name]['sha256'], row['sha256'])
        for name, expected in (
                (admission.CONTRACT_PATH, admission.CONTRACT_SHA256),
                (admission.ANON_CONTRACT_PATH, admission.ANON_CONTRACT_SHA256),
                (admission.FILE_CONTRACT_PATH, admission.FILE_CONTRACT_SHA256),
                (admission.TASK_CONTRACT_PATH, admission.TASK_CONTRACT_SHA256)):
            self.assertEqual(hashlib.sha256((admission.REPOSITORY / name).read_bytes()).hexdigest(),
                             expected)

    def test_empty_headers_require_fixed_f41_digest_and_exact_selection_shape(self):
        self.assertEqual(admission.provider_header_policy(
            self.core, self.contract, admission.TASK_WORKER_CONTRACT_SHA256), [])
        for identity in ('0' * 64, admission.FILE_CONTRACT_SHA256):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                admission.provider_header_policy(self.core, self.contract, identity)
        for field, value in (
                ('provider_root', 'compat'),
                ('units', ['linux_task.c', 'linux_task_worker_owner.c']),
                ('repository_include_roots', ['compat/native-runtime']),
                ('native_include_roots', self.contract['native_include_roots'][::-1]),
                ('required_patched_headers', ['sys/sys/file.h'])):
            changed = copy.deepcopy(self.contract)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.policy(changed)

    def test_role_shape_cannot_drop_add_or_relabel_any_selected_owner(self):
        for name in (IMPLEMENTATION, API_HEADER, *sorted(PROOF_OWNERS)):
            for operation in ('drop', 'relabel'):
                changed = copy.deepcopy(self.contract)
                if operation == 'drop':
                    changed['repository_inputs'].pop(name)
                else:
                    changed['repository_inputs'][name]['role'] = 'file_header'
                with self.subTest(name=name, operation=operation), self.assertRaises(ValueError):
                    self.policy(changed)
        changed = copy.deepcopy(self.contract)
        changed['repository_inputs']['compat/native-runtime/task/extra.c'] = dict(
            role='task_implementation_owner', blob='a' * 40, sha256='b' * 64)
        with self.assertRaises(ValueError):
            self.policy(changed)

    def test_header_and_original_implementation_require_exact_consumed_rows(self):
        proof = self.proof()
        admission.require_task_worker_inputs(
            proof, self.repo, self.contract, admission.TASK_WORKER_CONTRACT_SHA256)
        for name in (IMPLEMENTATION, API_HEADER):
            for field, value in ((None, None), ('kind', 'archive'),
                                 ('role', 'api_definition_owner'), ('sha256', '0' * 64),
                                 ('relative', 'compat/foreign.h')):
                changed = copy.deepcopy(proof)
                if field is None:
                    changed.pop(str(self.repo / name))
                else:
                    changed[str(self.repo / name)][field] = value
                with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                    admission.require_task_worker_inputs(
                        changed, self.repo, self.contract, admission.TASK_WORKER_CONTRACT_SHA256)

    def test_all_three_original_fragments_are_still_required(self):
        proof = self.proof()
        for name in task_fixture.FRAGMENTS:
            changed = copy.deepcopy(proof)
            changed.pop(str(self.repo / name))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'fragment'):
                admission.require_task_fragments(
                    changed, self.repo, self.contract, admission.TASK_WORKER_CONTRACT_SHA256)

    def test_fifth_selector_rejects_alias_tamper_symlink_and_crossed_contract_bytes(self):
        real = admission.REPOSITORY / admission.TASK_WORKER_CONTRACT_PATH
        path = self.repo / admission.TASK_WORKER_CONTRACT_PATH
        path.parent.mkdir(parents=True)
        path.write_bytes(real.read_bytes())
        self.assertEqual(admission.load_contract(path, self.repo), self.contract)
        alias = path.with_name('unreviewed.json')
        alias.write_bytes(real.read_bytes())
        with self.assertRaises(ValueError):
            admission.load_contract(alias, self.repo)
        for previous in (admission.CONTRACT_PATH, admission.ANON_CONTRACT_PATH,
                         admission.FILE_CONTRACT_PATH, admission.TASK_CONTRACT_PATH):
            path.write_bytes((admission.REPOSITORY / previous).read_bytes())
            with self.subTest(previous=previous), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)
        path.write_bytes(real.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            admission.load_contract(path, self.repo)
        path.unlink()
        path.symlink_to(real)
        with self.assertRaises(ValueError):
            admission.load_contract(path, self.repo)

    def test_unconsumed_worker_proofs_remain_real_git_and_byte_identity_inputs(self):
        contract = copy.deepcopy(self.contract)
        for name, row in contract['repository_inputs'].items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = ('/* isolated ' + name + ' */\n').encode()
            path.write_bytes(raw)
            row.update(sha256=hashlib.sha256(raw).hexdigest(),
                       blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())
        environment = admission.git_environment()
        environment.update(GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for arguments in (['init', '-q'], ['add', '--', *contract['repository_inputs']],
                          ['commit', '-q', '-m', 'isolated wrapper provenance']):
            subprocess.run(['git', '-C', str(self.repo)] + arguments, env=environment,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        contract['repository_commit'] = subprocess.check_output(
            ['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], env=environment).decode().strip()
        self.assertEqual(len(admission.repository_inputs(self.repo, contract)), 15)
        for name in PROOF_OWNERS:
            path = self.repo / name
            original = path.read_bytes()
            path.write_bytes(original + b'changed\n')
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, 'working bytes differ'):
                admission.repository_inputs(self.repo, contract)
            path.write_bytes(original)
            changed = copy.deepcopy(contract)
            changed['repository_inputs'][name]['blob'] = '0' * 40
            with self.assertRaises(ValueError):
                admission.repository_inputs(self.repo, changed)

    def test_only_wrapper_unit_and_exact_old_include_order_can_be_selected(self):
        for name in self.contract['repository_include_roots']:
            (self.repo / name).mkdir(parents=True)
        for name in self.contract['native_include_roots']:
            (self.source / name).mkdir(parents=True)
        provider = self.repo / self.contract['provider_root']
        provider.mkdir()
        expected = [self.repo / name for name in self.contract['repository_include_roots']] + [
            self.source / name for name in self.contract['native_include_roots']]
        self.assertEqual(admission.selected_inputs(
            self.contract, self.repo, self.source, provider, ['linux_task_worker_owner.c'], []),
            expected)
        for units in (['linux_task.c'], ['linux_task.c', 'linux_task_worker_owner.c']):
            with self.subTest(units=units), self.assertRaises(ValueError):
                admission.selected_inputs(self.contract, self.repo, self.source, provider, units, [])
        with self.assertRaises(ValueError):
            admission.selected_inputs(self.contract, self.repo, self.source, provider,
                                      ['linux_task_worker_owner.c'], expected[::-1])


if __name__ == '__main__':
    unittest.main()
