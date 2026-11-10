"""F44 public Wait builder integration with private files and a mocked compiler only."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

_spec = importlib.util.spec_from_file_location(
    '_f44_public_archive_fixture', Path(__file__).with_name('test_native_provider_archive_admission.py'))
_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_archive)
import test_native_wait_provider_inputs as wait_fixture

inputs, builder = _archive.inputs, _archive.builder
COMPILED, PROVENANCE = wait_fixture.COMPILED, wait_fixture.PROVENANCE


class WaitProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        f = self.fixture = _archive.ProviderAdmissionTests(
            'test_preflight_only_has_no_compile_or_object_pass')
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.real_repository = inputs.REPOSITORY
        f.contract = copy.deepcopy(inputs.load_contract(
            self.real_repository / inputs.WAIT_CONTRACT_PATH))
        f.provider = f.repo / f.contract['provider_root']
        f.unit = f.provider / 'linux_wait.c'
        f.contract_path = _archive.write(f.repo / inputs.WAIT_CONTRACT_PATH,
            (self.real_repository / inputs.WAIT_CONTRACT_PATH).read_bytes())
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
            result[result.index('--unit') + 1] = 'linux_wait.c'
            return result

        f.arguments = arguments
        f.fake_compiler = self.compiler

    def compiler(self, command, **keywords):
        f = self.fixture
        f.commands.append((command, keywords))
        paths = [f.repo / name for name in COMPILED] + [f.native]
        if '-M' in command and getattr(self, 'omit_recovered_header', False):
            paths.remove(f.repo / 'compat/native-runtime/wait-f43/include/linux/wait.h')
        dep = Path(command[command.index('-MF') + 1])
        dep.write_text('linux_wait.o: ' + ' '.join(map(str, paths)) + '\n')
        if '-c' in command:
            _archive.write(Path(command[command.index('-o') + 1]), b'private mocked Wait object\n')
        if '-MD' in command and getattr(self, 'drift_final_generation', False):
            proof = f.repo / PROVENANCE
            proof.write_bytes(proof.read_bytes() + b'\n')
            self.drift_fired = True
        return mock.Mock(returncode=0, stdout='private compiler fixture only\n', stderr='')

    def test_public_wait_receipt_records_generation_and_both_complete_input_proofs(self):
        f = self.fixture
        self.assertEqual(f.invoke(), 0)
        state = f.status()
        self.assertEqual((state['state'], state['stage']), ('PASS', 'COMPLETE'))
        self.assertEqual(state['provider_contract_sha256'], inputs.WAIT_CONTRACT_SHA256)
        self.assertEqual(state['required_patched_headers'], [])
        self.assertEqual(state['required_wait_inputs'], sorted(COMPILED))
        generation = state['wait_generation_proof']
        self.assertEqual(generation['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')
        self.assertEqual(generation['operation_count'], 49)
        self.assertEqual(generation['provenance_sha256'], f.contract['generation_provenance_sha256'])
        self.assertEqual(generation['native_compilation'], 'NOT_RUN')
        self.assertEqual(list(state['objects']), ['linux_wait'])
        before = state['precompile_dependencies']['linux_wait']
        after = state['objects']['linux_wait']['dependency_proof']
        self.assertEqual(before, after)
        self.assertEqual({row['relative'] for row in before.values()
                          if row['kind'] == 'repository'}, set(COMPILED))
        self.assertTrue(all(row.get('role') != 'generation_proof_owner'
                            for row in before.values()))
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-M', f.commands[0][0])
        self.assertNotIn('-c', f.commands[0][0])
        self.assertIn('-MD', f.commands[1][0])
        self.assertIn('-c', f.commands[1][0])
        for flag in ('-Werror', '-D_KERNEL', '-nostdinc'):
            self.assertIn(flag, f.commands[1][0])
        self.assertTrue((f.output / 'linux_wait.o').is_file())
        self.assertFalse((f.obj / 'linux_wait.o').exists())

    def test_invalid_generation_is_rejected_before_output_or_compiler_commands(self):
        f = self.fixture
        path = f.repo / PROVENANCE
        document = json.loads(path.read_bytes())
        document['state'] = 'COMPILED'
        raw = (json.dumps(document, indent=2) + '\n').encode()
        path.write_bytes(raw)
        row = f.contract['repository_inputs'][PROVENANCE]
        row.update(sha256=hashlib.sha256(raw).hexdigest(),
                   blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())
        f.bindings[str(path)] = dict(kind='repository', relative=PROVENANCE, **row)
        f.contract['generation_provenance_sha256'] = row['sha256']
        errors = io.StringIO()
        with mock.patch.object(inputs, '_WAIT_PROVENANCE_SHA256', row['sha256']):
            with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
                f.invoke()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('Wait generation: generation scope/pins/flags differ', errors.getvalue())
        self.assertEqual(f.commands, [])
        self.assertEqual(f.archives, [])
        self.assertFalse(f.output.exists())

    def test_missing_recovered_header_stops_public_builder_before_compile(self):
        f = self.fixture
        self.omit_recovered_header = True
        with self.assertRaisesRegex(ValueError, 'required Wait input.*include/linux/wait.h'):
            f.invoke()
        self.assertEqual(len(f.commands), 1)
        self.assertIn('-M', f.commands[0][0])
        self.assertNotIn('-c', f.commands[0][0])
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(f.status()['objects'], {})
        self.assertFalse((f.output / 'linux_wait.o').exists())

    def test_final_generation_drift_overrides_an_otherwise_successful_public_object(self):
        f = self.fixture
        self.drift_final_generation = True
        self.drift_fired = False
        with self.assertRaisesRegex(RuntimeError, 'Wait generation.*same-read generation SHA256/blob differs'):
            f.invoke()
        self.assertTrue(self.drift_fired)
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-c', f.commands[1][0])
        state = f.status()
        self.assertEqual(state['state'], 'FAIL')
        self.assertIn('Wait generation', state['integrity_error'])
        self.assertEqual(list(state['objects']), ['linux_wait'])
        self.assertEqual(state['objects']['linux_wait']['dependency_proof'],
                         state['precompile_dependencies']['linux_wait'])
        self.assertTrue((f.output / 'linux_wait.o').exists())
        self.assertFalse((f.obj / 'linux_wait.o').exists())


if __name__ == '__main__':
    unittest.main()
