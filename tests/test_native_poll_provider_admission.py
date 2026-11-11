"""F46 public Poll admission integration; all compiler outputs are private mocks."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_native_poll_provider_inputs as fixture

_spec = importlib.util.spec_from_file_location(
    '_f46_public_archive_fixture', Path(__file__).with_name('test_native_provider_archive_admission.py'))
_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_archive)
inputs, builder = _archive.inputs, _archive.builder


class PollProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        f = self.fixture = _archive.ProviderAdmissionTests(
            'test_preflight_only_has_no_compile_or_object_pass')
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.real_repository = inputs.REPOSITORY
        f.contract = copy.deepcopy(inputs.load_contract(
            self.real_repository / inputs.POLL_CONTRACT_PATH))
        f.provider = f.repo / f.contract['provider_root']
        f.unit = f.provider / 'linux_poll_owner.c'
        f.contract_path = _archive.write(f.repo / inputs.POLL_CONTRACT_PATH,
            (self.real_repository / inputs.POLL_CONTRACT_PATH).read_bytes())
        f.bindings = {}
        for relative, row in f.contract['repository_inputs'].items():
            path = _archive.write(f.repo / relative,
                                  (self.real_repository / relative).read_bytes())
            f.bindings[str(path)] = dict(kind='repository', relative=relative, **row)
        for relative in f.contract['repository_include_roots']:
            (f.repo / relative).mkdir(parents=True, exist_ok=True)
        prior_arguments = f.arguments

        def arguments(archive=True, extra=()):
            result = prior_arguments(archive=archive, extra=extra)
            result[result.index('--unit') + 1] = 'linux_poll_owner.c'
            return result
        f.arguments = arguments
        self.real_run = inputs.subprocess.run
        self.core_calls = 0
        self.generation_calls = 0

    def compiler(self, command, **keywords):
        f = self.fixture
        if command[0] == 'git':
            return self.real_run(command, **keywords)
        f.commands.append((command, keywords))
        paths = [f.repo / name for name in fixture.COMPILED] + [
            f.native, f.overlay / 'sys/sys/file.h']
        phase = 'MD' if '-MD' in command else 'M'
        omit = getattr(self, 'omit_' + phase, None)
        if omit:
            paths.remove(f.repo / omit)
        proof = getattr(self, 'consume_' + phase, None)
        if proof:
            paths.append(f.repo / proof)
        if getattr(self, 'omit_file_header', False):
            paths.remove(f.overlay / 'sys/sys/file.h')
        dep = Path(command[command.index('-MF') + 1])
        dep.write_text('linux_poll_owner.o: ' + ' '.join(map(str, paths)) + '\n')
        if '-c' in command:
            _archive.write(Path(command[command.index('-o') + 1]), b'private mocked Poll object\n')
            self.compilation_finished = True
            if getattr(self, 'dirty_final_proof', False):
                path = f.repo / fixture.wait_fixture.INPUT_PROVENANCE
                path.write_bytes(path.read_bytes() + b' ')
        return mock.Mock(returncode=0, stdout='private Poll compiler fixture only\n', stderr='')

    def invoke(self, extra=()):
        f = self.fixture
        real_load = inputs.load_contract
        real_generation = inputs.verify_poll_generation

        def load(path, repository=None):
            if Path(path).resolve() == f.contract_path.resolve():
                return f.contract
            return real_load(path, f.repo if repository is None else repository)

        def core(*args, **kwargs):
            self.core_calls += 1
            if getattr(self, 'fail_final_core', False) and self.core_calls > 1:
                raise ValueError('fixture complete core final drift')
            return f.core

        def generation(*args, **kwargs):
            self.generation_calls += 1
            if getattr(self, 'fail_final_generation', False) and self.generation_calls > 1:
                raise ValueError('fixture final referenced Wait generation drift')
            return real_generation(*args, **kwargs)

        with fixture.referenced_wait(f), contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', f.arguments(extra=extra)))
            stack.enter_context(mock.patch.object(builder, 'require_hp_owner'))
            stack.enter_context(mock.patch.object(builder, 'toolchain_paths', return_value=f.tools))
            stack.enter_context(mock.patch.object(inputs, 'REPOSITORY', f.repo))
            stack.enter_context(mock.patch.object(inputs, 'load_contract', side_effect=load))
            stack.enter_context(mock.patch.object(inputs, 'verify_core', side_effect=core))
            stack.enter_context(mock.patch.object(inputs, 'verify_poll_generation', side_effect=generation))
            stack.enter_context(mock.patch('native_source_archive.ArchiveSource', f.archive_class))
            stack.enter_context(mock.patch.object(builder.subprocess, 'run', side_effect=self.compiler))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return builder.main()

    def test_public_poll_receipt_has_exact_inputs_real_reference_and_both_complete_proofs(self):
        f = self.fixture
        self.assertEqual(self.invoke(), 0)
        state = f.status()
        self.assertEqual((state['state'], state['stage']), ('PASS', 'COMPLETE'))
        self.assertEqual(state['provider_contract_sha256'], inputs.POLL_CONTRACT_SHA256)
        self.assertEqual(state['required_patched_headers'], ['sys/sys/file.h'])
        self.assertEqual(state['required_poll_inputs'], sorted(fixture.COMPILED))
        self.assertEqual(state['required_wait_inputs'], [])
        self.assertEqual(state['wait_generation_proof'], {})
        self.assertEqual(state['poll_generation_proof']['state'],
                         'VERIFIED_REFERENCED_WAIT_GENERATION_ONLY')
        self.assertEqual(state['poll_generation_proof']['wait_generation']['operation_count'], 49)
        self.assertEqual(list(state['objects']), ['linux_poll_owner'])
        before = state['precompile_dependencies']['linux_poll_owner']
        after = state['objects']['linux_poll_owner']['dependency_proof']
        self.assertEqual(before, after)
        self.assertEqual({row['relative'] for row in before.values()
                          if row['kind'] == 'repository'}, set(fixture.COMPILED))
        self.assertTrue(all(row.get('role') not in ('generation_proof_owner', 'api_definition_owner')
                            for row in before.values()))
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-M', f.commands[0][0])
        self.assertIn('-MD', f.commands[1][0])
        self.assertIn('-c', f.commands[1][0])
        for flag in ('-Werror', '-D_KERNEL', '-nostdinc'):
            self.assertIn(flag, f.commands[1][0])
        self.assertEqual(self.generation_calls, 2)
        self.assertEqual(self.core_calls, 2)
        self.assertTrue((f.output / 'linux_poll_owner.o').is_file())
        self.assertFalse((f.obj / 'linux_poll_owner.o').exists())

    def test_public_preflight_records_admission_without_an_object_pass(self):
        f = self.fixture
        self.assertEqual(self.invoke(['--preflight-only']), 0)
        state = f.status()
        self.assertEqual(state['state'], 'PREFLIGHT_PASS')
        self.assertEqual(state['object_compilation'], 'NOT_RUN')
        self.assertEqual(state['objects'], {})
        self.assertEqual(len(f.commands), 1)
        self.assertNotIn('-c', f.commands[0][0])
        self.assertFalse((f.output / 'linux_poll_owner.o').exists())

    def test_invalid_rebound_wait_proof_stops_before_output_archive_and_compiler(self):
        f = self.fixture
        name = fixture.wait_fixture.PROVENANCE
        path = f.repo / name
        document = json.loads(path.read_bytes())
        document['native_compilation'] = 'PASS'
        raw = (json.dumps(document, indent=2) + '\n').encode()
        path.write_bytes(raw)
        row = f.contract['repository_inputs'][name]
        row.update(sha256=fixture.sha(raw), blob=fixture.blob(raw))
        f.bindings[str(path)] = dict(kind='repository', relative=name, **row)
        f.contract['generation_provenance_sha256'] = row['sha256']
        errors = io.StringIO()
        with mock.patch.object(inputs, '_WAIT_PROVENANCE_SHA256', row['sha256']):
            with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                self.invoke()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('Wait generation: generation scope/pins/flags differ', errors.getvalue())
        self.assertEqual(f.commands, [])
        self.assertEqual(f.archives, [])
        self.assertFalse(f.output.exists())

    def test_missing_task_declaration_header_stops_scan_before_compile(self):
        f = self.fixture
        self.omit_M = fixture.API_HEADER
        with self.assertRaisesRegex(ValueError, 'required Poll input'):
            self.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertNotIn('-c', f.commands[0][0])
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(f.status()['objects'], {})

    def test_missing_recovered_wait_header_in_actual_md_cannot_pass(self):
        f = self.fixture
        self.omit_MD = fixture.WAIT_HEADER
        with self.assertRaisesRegex(ValueError, 'actual provider dependencies differ'):
            self.invoke()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(f.status()['objects'], {})

    def test_api_definition_owner_cannot_enter_independent_scan(self):
        f = self.fixture
        self.consume_M = fixture.API_OWNER
        with self.assertRaisesRegex(ValueError, 'API definition owner is not a provider dependency'):
            self.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertEqual(f.status()['state'], 'FAIL')

    def test_generation_owner_cannot_enter_actual_md_dependencies(self):
        f = self.fixture
        self.consume_MD = fixture.WAIT_BODY
        with self.assertRaisesRegex(ValueError, 'generation proof owner is not a provider dependency'):
            self.invoke()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(f.status()['state'], 'FAIL')

    def test_patched_file_header_is_still_required_by_public_poll_builder(self):
        f = self.fixture
        self.omit_file_header = True
        with self.assertRaisesRegex(ValueError, 'patched native FILE headers'):
            self.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertEqual(f.status()['state'], 'FAIL')

    def test_final_generation_failure_overrides_an_otherwise_successful_mock_object(self):
        f = self.fixture
        self.fail_final_generation = True
        with self.assertRaisesRegex(RuntimeError, 'fixture final referenced Wait generation drift'):
            self.invoke()
        state = f.status()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(state['state'], 'FAIL')
        self.assertIn('fixture final referenced Wait generation drift', state['integrity_error'])
        self.assertEqual(list(state['objects']), ['linux_poll_owner'])
        self.assertTrue((f.output / 'linux_poll_owner.o').exists())

    def test_final_core_failure_overrides_an_otherwise_successful_mock_object(self):
        f = self.fixture
        self.fail_final_core = True
        with self.assertRaisesRegex(RuntimeError, 'fixture complete core final drift'):
            self.invoke()
        state = f.status()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(state['state'], 'FAIL')
        self.assertIn('fixture complete core final drift', state['integrity_error'])
        self.assertEqual(list(state['objects']), ['linux_poll_owner'])
        self.assertTrue((f.output / 'linux_poll_owner.o').exists())

    def test_real_proof_byte_drift_is_rejected_by_final_repository_identity_read(self):
        f = self.fixture
        self.dirty_final_proof = True
        with self.assertRaisesRegex(RuntimeError, 'provider working bytes differ'):
            self.invoke()
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertIn('provider working bytes differ', f.status()['integrity_error'])
        self.assertEqual(list(f.status()['objects']), ['linux_poll_owner'])


if __name__ == '__main__':
    unittest.main()
