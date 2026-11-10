"""F41 wrapper admission fixtures exercise the public builder without native execution."""
import copy
import hashlib
import importlib.util
import io
import contextlib
from pathlib import Path
import unittest
from unittest import mock

_spec = importlib.util.spec_from_file_location(
    '_f41_task_admission_fixture', Path(__file__).with_name('test_native_task_provider_admission.py'))
_task = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_task)
inputs, builder = _task.inputs, _task.builder
from test_native_task_worker_provider_inputs import API_HEADER, IMPLEMENTATION, PROOF_OWNERS

_support = _task._fixture


class TaskWorkerProviderAdmissionTests(unittest.TestCase):
    verify_core = _task.TaskProviderAdmissionTests.verify_core
    invoke = _task.TaskProviderAdmissionTests.invoke

    def setUp(self):
        _task.TaskProviderAdmissionTests.setUp(self)
        f = self.f
        f.contract = copy.deepcopy(inputs.load_contract(
            inputs.REPOSITORY / inputs.TASK_WORKER_CONTRACT_PATH))
        f.unit = f.provider / 'linux_task_worker_owner.c'
        f.contract_path = _support.write(f.repo / inputs.TASK_WORKER_CONTRACT_PATH)
        f.bindings = {}
        self.paths = []
        for name, row in f.contract['repository_inputs'].items():
            path = _support.write(f.repo / name, ('/* isolated ' + name + ' */\n').encode())
            raw = path.read_bytes()
            row.update(blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                       sha256=hashlib.sha256(raw).hexdigest())
            f.bindings[str(path)] = dict(kind='repository', relative=name, **row)
            if row['role'] != 'api_definition_owner':
                self.paths.append(path)

    def arguments(self, extra=(), archive=True):
        result = _task.TaskProviderAdmissionTests.arguments(self, extra, archive)
        result[result.index('--unit') + 1] = 'linux_task_worker_owner.c'
        return result

    def compiler(self, command, **keywords):
        result = _task.TaskProviderAdmissionTests.compiler(self, command, **keywords)
        name = (getattr(self, 'consume_worker_scan', None) if '-M' in command
                else getattr(self, 'consume_worker_actual', None))
        if name is not None:
            path = Path(command[command.index('-MF') + 1])
            path.write_text(path.read_text().rstrip() + ' ' + str(self.f.repo / name) + '\n')
        return result

    def test_wrapper_preflight_requires_original_implementation_and_new_api_header(self):
        f = self.f
        self.assertEqual(self.invoke(['--preflight-only']), 0)
        state = f.status()
        self.assertEqual((state['state'], state['stage'], state['object_compilation']),
                         ('PREFLIGHT_PASS', 'ADMITTED_NO_OBJECTS', 'NOT_RUN'))
        self.assertEqual(state['provider_contract_sha256'], inputs.TASK_WORKER_CONTRACT_SHA256)
        self.assertEqual(state['required_patched_headers'], [])
        self.assertEqual(state['required_task_worker_inputs'], sorted([IMPLEMENTATION, API_HEADER]))
        self.assertEqual(state['objects'], {})
        proof = state['precompile_dependencies']['linux_task_worker_owner']
        self.assertEqual(len(proof), 14)  # thirteen exact repository inputs plus one native fixture
        for name in (IMPLEMENTATION, API_HEADER):
            self.assertEqual(proof[str(f.repo / name)]['kind'], 'repository')
        for name in PROOF_OWNERS:
            self.assertNotIn(str(f.repo / name), proof)
            self.assertEqual(state['repository_inputs'][str(f.repo / name)]['role'],
                             'api_definition_owner')
        self.assertEqual(len(self.core_calls), 2)
        self.assertIs(self.core_calls[-1][1]['core'], f.core)
        self.assertNotIn('-c', f.commands[0][0])
        self.assertFalse((f.output / 'linux_task_worker_owner.o').exists())

    def test_wrapper_compile_fixture_has_two_equal_complete_dependency_proofs(self):
        f = self.f
        self.assertEqual(self.invoke(), 0)
        state = f.status()
        self.assertEqual(state['state'], 'PASS')
        self.assertEqual(list(state['objects']), ['linux_task_worker_owner'])
        self.assertEqual(state['objects']['linux_task_worker_owner']['dependency_proof'],
                         state['precompile_dependencies']['linux_task_worker_owner'])
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-M', f.commands[0][0])
        self.assertIn('-MD', f.commands[1][0])
        self.assertIn('-c', f.commands[1][0])
        self.assertFalse((f.output / 'linux_task.o').exists())
        self.assertFalse((f.obj / 'linux_task_worker_owner.o').exists())

    def assert_scan_omission(self, relative):
        self.omit_scan = relative
        with self.assertRaisesRegex(ValueError, 'Task worker'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 1)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertFalse((self.f.output / 'linux_task_worker_owner.o').exists())

    def test_scan_cannot_omit_actual_worker_api_header(self):
        self.assert_scan_omission(API_HEADER)

    def test_scan_cannot_omit_original_task_implementation_owner(self):
        self.assert_scan_omission(IMPLEMENTATION)

    def assert_actual_omission(self, relative):
        self.omit_actual = relative
        with self.assertRaisesRegex(ValueError, 'independent scan'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 2)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertEqual(self.f.status()['objects'], {})

    def test_actual_dependency_proof_cannot_omit_worker_api_header(self):
        self.assert_actual_omission(API_HEADER)

    def test_actual_dependency_proof_cannot_omit_original_task_owner(self):
        self.assert_actual_omission(IMPLEMENTATION)

    def assert_proof_owner_forbidden(self, relative, actual=False):
        if actual:
            self.consume_worker_actual = relative
        else:
            self.consume_worker_scan = relative
        with self.assertRaisesRegex(ValueError, 'API definition owner'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 2 if actual else 1)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertEqual(self.f.status()['objects'], {})

    def test_worker_declaration_fragment_cannot_be_consumed_in_scan(self):
        self.assert_proof_owner_forbidden('compat/native-runtime/worker/worker_header.inc')

    def test_worker_implementation_fragment_cannot_be_consumed_in_scan(self):
        self.assert_proof_owner_forbidden('compat/native-runtime/worker/worker.inc')

    def test_worker_declaration_fragment_cannot_be_consumed_in_actual_compile(self):
        self.assert_proof_owner_forbidden('compat/native-runtime/worker/worker_header.inc', actual=True)

    def test_worker_implementation_fragment_cannot_be_consumed_in_actual_compile(self):
        self.assert_proof_owner_forbidden('compat/native-runtime/worker/worker.inc', actual=True)

    def test_wrapper_still_requires_actual_entry_fragment_before_compile(self):
        self.omit_scan = 'compat/native-entry/task_entry.inc'
        with self.assertRaisesRegex(ValueError, 'fragment'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 1)
        self.assertEqual(self.f.status()['state'], 'FAIL')

    def test_f39_digest_cannot_admit_f41_empty_header_policy_before_output(self):
        with mock.patch.object(inputs, 'reviewed_contract_sha256',
                               return_value=inputs.TASK_CONTRACT_SHA256):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.invoke()
        self.assertFalse(self.f.output.exists())
        self.assertEqual(self.f.commands, [])

    def test_full_core_recheck_remains_required_after_wrapper_object_success(self):
        self.fail_core_recheck = True
        with self.assertRaisesRegex(RuntimeError, 'full frozen core drift'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 2)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertEqual(self.f.status()['integrity_error'], 'full frozen core drift')


if __name__ == '__main__':
    unittest.main()
