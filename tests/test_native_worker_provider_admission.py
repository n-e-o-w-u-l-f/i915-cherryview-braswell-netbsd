"""F50 public Worker builder integration with private mocked compiler outputs only."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_native_worker_provider_inputs as fixture

_spec = importlib.util.spec_from_file_location(
    '_f50_archive_fixture', Path(__file__).with_name('test_native_provider_archive_admission.py'))
_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_archive)
inputs, builder = _archive.inputs, _archive.builder


class WorkerProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        f = self.fixture = _archive.ProviderAdmissionTests(
            'test_preflight_only_has_no_compile_or_object_pass')
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.contract = copy.deepcopy(inputs.load_contract(
            inputs.REPOSITORY / inputs.WORKER_CONTRACT_PATH))
        f.provider = f.repo / f.contract['provider_root']
        f.unit = f.provider / 'linux_kthread.c'
        f.contract_path = _archive.write(f.repo / inputs.WORKER_CONTRACT_PATH,
            (inputs.REPOSITORY / inputs.WORKER_CONTRACT_PATH).read_bytes())
        f.bindings = {}
        for name, row in f.contract['repository_inputs'].items():
            path = _archive.write(f.repo / name, (inputs.REPOSITORY / name).read_bytes())
            f.bindings[str(path)] = dict(kind='repository', relative=name, **row)
        for name in f.contract['repository_include_roots']:
            (f.repo / name).mkdir(parents=True, exist_ok=True)
        prior_arguments = f.arguments
        def arguments(archive=True, extra=()):
            result = prior_arguments(archive=archive, extra=extra)
            result[result.index('--unit') + 1] = 'linux_kthread.c'
            return result
        f.arguments = arguments
        self.core_calls = 0
        self.generation_calls = 0

    def compiler(self, command, **keywords):
        f = self.fixture
        f.commands.append((command, keywords))
        paths = [f.repo / name for name in fixture.COMPILED] + [f.native]
        phase = 'MD' if '-MD' in command else 'M'
        missing = getattr(self, 'omit_' + phase, None)
        if missing:
            paths.remove(f.repo / missing)
        proof = getattr(self, 'consume_' + phase, None)
        if proof:
            paths.append(f.repo / proof)
        if getattr(self, 'consume_original_FILE', False):
            paths.append(f.source / 'sys/sys/file.h')
        dep = Path(command[command.index('-MF') + 1])
        dep.write_text('linux_kthread.o: ' + ' '.join(map(str, paths)) + '\n')
        if '-c' in command:
            _archive.write(Path(command[command.index('-o') + 1]), b'private mocked Worker object\n')
            if getattr(self, 'drift_final_provenance', False):
                path = f.repo / fixture.PROVENANCE
                path.write_bytes(path.read_bytes() + b' ')
        return mock.Mock(returncode=0, stdout='private mocked compiler only\n', stderr='')

    def invoke(self, extra=()):
        f = self.fixture
        real_generation = inputs.verify_worker_generation
        def core(*args, **kwargs):
            self.core_calls += 1
            if getattr(self, 'fail_final_core', False) and self.core_calls > 1:
                raise ValueError('fixture complete Worker core final drift')
            return f.core
        def generation(*args, **kwargs):
            self.generation_calls += 1
            return real_generation(*args, **kwargs)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', f.arguments(extra=extra)))
            stack.enter_context(mock.patch.object(builder, 'require_hp_owner'))
            stack.enter_context(mock.patch.object(builder, 'toolchain_paths', return_value=f.tools))
            stack.enter_context(mock.patch.object(inputs, 'REPOSITORY', f.repo))
            stack.enter_context(mock.patch.object(inputs, 'load_contract', return_value=f.contract))
            stack.enter_context(mock.patch.object(inputs, 'repository_inputs', return_value=f.bindings))
            stack.enter_context(mock.patch.object(inputs, 'verify_core', side_effect=core))
            stack.enter_context(mock.patch.object(inputs, 'verify_worker_generation', side_effect=generation))
            stack.enter_context(mock.patch('native_source_archive.ArchiveSource', f.archive_class))
            stack.enter_context(mock.patch.object(builder.subprocess, 'run', side_effect=self.compiler))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return builder.main()

    def test_public_worker_records_eight_required_inputs_and_separate_source_proof(self):
        f = self.fixture
        self.assertEqual(self.invoke(), 0)
        state = f.status()
        self.assertEqual((state['state'], state['stage']), ('PASS', 'COMPLETE'))
        self.assertEqual(state['provider_contract_sha256'], inputs.WORKER_CONTRACT_SHA256)
        self.assertEqual(state['required_worker_inputs'], sorted(fixture.COMPILED))
        self.assertEqual(state['required_patched_headers'], [])
        self.assertEqual(state['required_task_worker_inputs'], [])
        self.assertEqual(state['required_wait_inputs'], [])
        self.assertEqual(state['required_poll_inputs'], [])
        self.assertEqual(state['wait_generation_proof'], {})
        self.assertEqual(state['poll_generation_proof'], {})
        self.assertEqual(state['worker_generation_proof']['state'],
                         'VERIFIED_WORKER_SOURCE_GENERATION_ONLY')
        self.assertEqual(state['worker_generation_proof']['operation_count'], 27)
        before = state['precompile_dependencies']['linux_kthread']
        after = state['objects']['linux_kthread']['dependency_proof']
        self.assertEqual(before, after)
        self.assertEqual({row['relative'] for row in before.values()
                          if row['kind'] == 'repository'}, set(fixture.COMPILED))
        self.assertFalse(any(row.get('role') == 'generation_proof_owner' for row in before.values()))
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-M', f.commands[0][0])
        self.assertIn('-MD', f.commands[1][0])
        self.assertIn('-c', f.commands[1][0])
        for flag in ('-Werror', '-D_KERNEL', '-nostdinc'):
            self.assertIn(flag, f.commands[1][0])
        self.assertEqual(self.generation_calls, 2)
        self.assertEqual(self.core_calls, 2)
        self.assertTrue((f.output / 'linux_kthread.o').is_file())
        self.assertFalse((f.obj / 'linux_kthread.o').exists())

    def test_invalid_rebound_typed_provenance_stops_before_output_or_mocked_native_command(self):
        f = self.fixture
        path = f.repo / fixture.PROVENANCE
        document = fixture.json.loads(path.read_bytes())
        document['native_compilation'] = 'PASS'
        raw = (fixture.json.dumps(document, indent=2) + '\n').encode()
        path.write_bytes(raw)
        row = f.contract['repository_inputs'][fixture.PROVENANCE]
        row.update(sha256=fixture.sha(raw), blob=fixture.blob(raw))
        f.bindings[str(path)] = dict(kind='repository', relative=fixture.PROVENANCE, **row)
        f.contract['generation_provenance_sha256'] = fixture.sha(raw)
        errors = io.StringIO()
        with mock.patch.object(inputs, '_WORKER_PROVENANCE_SHA256', fixture.sha(raw)):
            with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                self.invoke()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('Worker generation:', errors.getvalue())
        self.assertEqual(f.commands, [])
        self.assertEqual(f.archives, [])
        self.assertFalse(f.output.exists())

    def test_missing_recovered_header_stops_independent_scan_before_mock_compile(self):
        f = self.fixture
        self.omit_M = fixture.HEADER
        with self.assertRaisesRegex(ValueError, 'required Worker input'):
            self.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertNotIn('-c', f.commands[0][0])
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(f.status()['objects'], {})

    def test_missing_task_header_in_actual_MD_cannot_complete(self):
        f = self.fixture
        self.omit_MD = 'compat/native-runtime/task/task_netbsd.h'
        with self.assertRaisesRegex(ValueError, 'actual provider dependencies'):
            self.invoke()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(f.status()['objects'], {})

    def test_raw_origin_cannot_be_compiler_consumed_in_the_independent_scan(self):
        f = self.fixture
        self.consume_M = fixture.ORIGINS[0]
        with self.assertRaisesRegex(ValueError, 'generation proof owner is not a provider dependency'):
            self.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertEqual(f.status()['state'], 'FAIL')

    def test_source_producer_cannot_be_consumed_by_actual_MD(self):
        f = self.fixture
        self.consume_MD = fixture.PRODUCER
        with self.assertRaisesRegex(ValueError, 'generation proof owner is not a provider dependency'):
            self.invoke()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(f.status()['state'], 'FAIL')

    def test_final_generation_drift_overrides_an_otherwise_successful_mock_object(self):
        f = self.fixture
        self.drift_final_provenance = True
        with self.assertRaisesRegex(RuntimeError, 'Worker generation:'):
            self.invoke()
        state = f.status()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(state['state'], 'FAIL')
        self.assertIn('Worker generation:', state['integrity_error'])
        self.assertEqual(list(state['objects']), ['linux_kthread'])
        self.assertTrue((f.output / 'linux_kthread.o').exists())

    def test_final_full_core_failure_overrides_an_otherwise_successful_mock_object(self):
        f = self.fixture
        self.fail_final_core = True
        with self.assertRaisesRegex(RuntimeError, 'fixture complete Worker core final drift'):
            self.invoke()
        state = f.status()
        self.assertEqual(len(f.commands), 2)
        self.assertEqual(state['state'], 'FAIL')
        self.assertIn('complete Worker core final drift', state['integrity_error'])
        self.assertEqual(list(state['objects']), ['linux_kthread'])

    def test_mocked_preflight_has_no_object_pass_and_no_wait_composition(self):
        # This invokes only the fixture's mocked compiler; no public native CLI process runs.
        f = self.fixture
        self.assertEqual(self.invoke(['--preflight-only']), 0)
        state = f.status()
        self.assertEqual(state['state'], 'PREFLIGHT_PASS')
        self.assertEqual(state['object_compilation'], 'NOT_RUN')
        self.assertEqual(state['objects'], {})
        self.assertEqual(state['required_worker_inputs'], sorted(fixture.COMPILED))
        self.assertEqual(state['wait_generation_proof'], {})
        self.assertEqual(len(f.commands), 1)
        self.assertNotIn('-c', f.commands[0][0])
        self.assertFalse((f.output / 'linux_kthread.o').exists())

    def test_empty_FILE_requirement_does_not_admit_an_original_patched_header(self):
        f = self.fixture
        self.consume_original_FILE = True
        with self.assertRaisesRegex(ValueError, 'original.*patched|patched.*original'):
            self.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertEqual(f.status()['state'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
