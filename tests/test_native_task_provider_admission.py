"""F39 public provider admission with isolated dependency fixtures; no native tools."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

_spec = importlib.util.spec_from_file_location(
    '_f39_archive_admission_fixture', Path(__file__).with_name('test_native_provider_archive_admission.py'))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
inputs, builder = _fixture.inputs, _fixture.builder
from test_native_task_provider_inputs import FRAGMENTS, INPUTS


class TaskProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = _fixture.ProviderAdmissionTests(
            'test_preflight_only_has_no_compile_or_object_pass')
        f = self.f
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.contract = copy.deepcopy(inputs.load_contract(inputs.REPOSITORY / inputs.TASK_CONTRACT_PATH))
        f.provider = f.repo / f.contract['provider_root']
        f.provider.mkdir(parents=True)
        f.unit = f.provider / 'linux_task.c'
        f.contract_path = _fixture.write(f.repo / inputs.TASK_CONTRACT_PATH)
        f.bindings = {}
        self.paths = []
        for name, row in f.contract['repository_inputs'].items():
            path = _fixture.write(f.repo / name, ('/* isolated ' + name + ' */\n').encode())
            raw = path.read_bytes()
            row.update(blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                       sha256=hashlib.sha256(raw).hexdigest())
            f.bindings[str(path)] = dict(kind='repository', relative=name, **row)
            self.paths.append(path)
        f.repo_header = f.provider / 'task_entry_netbsd.h'
        for root in f.contract['repository_include_roots']:
            (f.repo / root).mkdir(parents=True, exist_ok=True)
        self.core_calls = []

    def arguments(self, extra=(), archive=True):
        result = self.f.arguments(archive=archive, extra=extra)
        result[result.index('--unit') + 1] = 'linux_task.c'
        return result

    def compiler(self, command, **keywords):
        f = self.f
        f.commands.append((command, keywords))
        paths = list(self.paths) + [f.native]
        if getattr(self, 'omit_scan', None) and '-M' in command:
            paths.remove(f.repo / self.omit_scan)
        if getattr(self, 'omit_actual', None) and '-MD' in command:
            paths.remove(f.repo / self.omit_actual)
        if getattr(self, 'foreign_inc', False):
            paths.append(_fixture.write(f.repo / 'compat/native-entry/unreviewed.inc'))
        if (getattr(self, 'consume_api_scan', False) or
                ('-MD' in command and getattr(self, 'consume_api_actual', False))):
            owner = _fixture.write(f.repo / 'compat/native-entry/proof_only.inc')
            raw = owner.read_bytes()
            f.bindings[str(owner)] = dict(kind='repository',
                relative=str(owner.relative_to(f.repo)), role='api_definition_owner',
                blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                sha256=hashlib.sha256(raw).hexdigest())
            paths.append(owner)
        dep = Path(command[command.index('-MF') + 1])
        dep.write_text('linux_task.o: ' + ' '.join(map(str, paths)) + '\n')
        if '-c' in command:
            _fixture.write(Path(command[command.index('-o') + 1]), b'isolated object\n')
        return mock.Mock(returncode=0, stdout='fixture only\n', stderr='')

    def verify_core(self, *arguments, **keywords):
        self.core_calls.append((arguments, keywords))
        if getattr(self, 'fail_core_recheck', False) and len(self.core_calls) > 1:
            raise ValueError('full frozen core drift')
        return self.f.core

    def invoke(self, extra=()):
        f = self.f
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', self.arguments(extra)))
            stack.enter_context(mock.patch.object(builder, 'require_hp_owner'))
            stack.enter_context(mock.patch.object(builder, 'toolchain_paths', return_value=f.tools))
            stack.enter_context(mock.patch.object(inputs, 'REPOSITORY', f.repo))
            stack.enter_context(mock.patch.object(inputs, 'load_contract', return_value=f.contract))
            stack.enter_context(mock.patch.object(inputs, 'repository_inputs', return_value=f.bindings))
            stack.enter_context(mock.patch.object(inputs, 'verify_core', side_effect=self.verify_core))
            stack.enter_context(mock.patch('native_source_archive.ArchiveSource', f.archive_class))
            stack.enter_context(mock.patch.object(builder.subprocess, 'run', side_effect=self.compiler))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return builder.main()

    def test_task_preflight_records_fixed_identity_and_no_file_header_requirement(self):
        f = self.f
        self.assertEqual(self.invoke(['--preflight-only']), 0)
        state = f.status()
        self.assertEqual((state['state'], state['stage'], state['object_compilation']),
                         ('PREFLIGHT_PASS', 'ADMITTED_NO_OBJECTS', 'NOT_RUN'))
        self.assertEqual(state['objects'], {})
        self.assertEqual(state['provider_contract_sha256'], inputs.TASK_CONTRACT_SHA256)
        self.assertEqual(state['required_patched_headers'], [])
        self.assertEqual(state['required_task_fragments'], sorted(FRAGMENTS))
        proof = state['precompile_dependencies']['linux_task']
        self.assertEqual(set(proof), {str(path) for path in self.paths + [f.native]})
        self.assertFalse(any(row['kind'] == 'patched' for row in proof.values()))
        command = f.commands[0][0]
        roots = [f.overlay / 'sys', f.repo / 'compat/native-runtime/include'] + [
            f.source / path for path in f.contract['native_include_roots']]
        self.assertEqual(command[1:5], ['-I' + str(path) for path in roots])
        self.assertNotIn('-c', command)
        self.assertFalse((f.output / 'linux_task.o').exists())
        self.assertEqual(len(self.core_calls), 2)
        self.assertIs(self.core_calls[1][1]['core'], f.core)

    def test_task_compile_fixture_requires_equal_scan_and_actual_composition(self):
        f = self.f
        self.assertEqual(self.invoke(), 0)
        state = f.status()
        self.assertEqual(state['state'], 'PASS')
        self.assertEqual(list(state['objects']), ['linux_task'])
        self.assertEqual(state['objects']['linux_task']['dependency_proof'],
                         state['precompile_dependencies']['linux_task'])
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-M', f.commands[0][0])
        self.assertIn('-MD', f.commands[1][0])
        self.assertIn('-c', f.commands[1][0])
        for name in FRAGMENTS:
            self.assertEqual(state['objects']['linux_task']['dependency_proof'][
                str(f.repo / name)]['role'], 'task_fragment')
        self.assertFalse((f.obj / 'linux_task.o').exists())

    def assert_scan_omission_fails(self, name):
        self.omit_scan = name
        with self.assertRaisesRegex(ValueError, 'fragment'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 1)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertFalse((self.f.output / 'linux_task.o').exists())

    def test_scan_cannot_omit_entry_fragment(self):
        self.assert_scan_omission_fails('compat/native-entry/task_entry.inc')

    def test_scan_cannot_omit_preallocated_fragment(self):
        self.assert_scan_omission_fails('compat/native-file/task_entry_preallocated.inc')

    def test_scan_cannot_omit_retained_quiesce_fragment(self):
        self.assert_scan_omission_fails('compat/native-file/task_quiesce_retained.inc')

    def test_actual_compile_cannot_omit_a_previously_admitted_fragment(self):
        self.omit_actual = 'compat/native-entry/task_entry.inc'
        with self.assertRaisesRegex(ValueError, 'independent scan'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 2)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertEqual(self.f.status()['objects'], {})

    def test_unreviewed_inc_is_rejected_before_compile(self):
        self.foreign_inc = True
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 1)
        self.assertEqual(self.f.status()['state'], 'FAIL')

    def test_proof_only_api_owner_stays_forbidden_in_scan(self):
        self.consume_api_scan = True
        with self.assertRaisesRegex(ValueError, 'API definition owner'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 1)

    def test_proof_only_api_owner_stays_forbidden_in_actual_compile(self):
        self.consume_api_actual = True
        with self.assertRaisesRegex(ValueError, 'API definition owner'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 2)
        self.assertEqual(self.f.status()['objects'], {})

    def test_wrong_identity_cannot_enable_empty_header_policy_before_output(self):
        with mock.patch.object(inputs, 'reviewed_contract_sha256', return_value=inputs.FILE_CONTRACT_SHA256):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.invoke()
        self.assertFalse(self.f.output.exists())
        self.assertEqual(self.f.commands, [])

    def test_full_core_recheck_still_overrides_a_task_object_success(self):
        self.fail_core_recheck = True
        with self.assertRaisesRegex(RuntimeError, 'full frozen core drift'):
            self.invoke()
        self.assertEqual(len(self.f.commands), 2)
        self.assertEqual(self.f.status()['state'], 'FAIL')
        self.assertEqual(self.f.status()['integrity_error'], 'full frozen core drift')

    def test_unpaired_task_contract_is_rejected_without_output_or_host_probe(self):
        with mock.patch.object(sys, 'argv', self.arguments(
                archive=False, extra=['--provider-contract', str(self.f.contract_path)])):
            with mock.patch.object(builder, 'require_hp_owner') as host:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    builder.main()
                host.assert_not_called()
        self.assertFalse(self.f.output.exists())


if __name__ == '__main__':
    unittest.main()
