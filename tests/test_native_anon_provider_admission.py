"""F35 anonymous FILE admission; compiler and preprocessor processes remain mocked."""
import importlib.util
import io
import contextlib
from pathlib import Path
import unittest

TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    '_f35_provider_integration_fixture', TESTS / 'test_native_provider_archive_admission.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)
inputs = fixture_module.inputs


class AnonymousProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        # Compose the established private fixture; do not inherit or execute F33 tests.
        self.fixture = fixture_module.ProviderAdmissionTests(
            'test_preflight_only_has_no_compile_or_object_pass')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        old_unit = f.unit
        f.unit = old_unit.with_name('linux_anon.c')
        old_unit.rename(f.unit)
        row = f.bindings.pop(str(old_unit))
        row['relative'] = 'compat/native-file/linux_anon.c'
        f.bindings[str(f.unit)] = row
        self.anon_header = fixture_module.write(
            f.provider / 'include/linux/anon_inodes_netbsd.h', b'/* private anon fixture */\n')
        raw = self.anon_header.read_bytes()
        f.bindings[str(self.anon_header)] = dict(kind='repository',
            relative='compat/native-file/include/linux/anon_inodes_netbsd.h',
            role='anon_header', blob=fixture_module.hashlib.sha1(
                b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
            sha256=fixture_module.digest(self.anon_header))
        f.contract_path = fixture_module.write(f.repo / inputs.ANON_CONTRACT_PATH)
        f.contract['units'] = ['linux_anon.c']
        f.contract['required_patched_headers'] = ['sys/sys/file.h']
        # The real source has no direct filedesc.h include: omission is intentional.
        f.omit_patched_header = True
        original_arguments = f.arguments

        def arguments(archive=True, extra=()):
            result = original_arguments(archive=archive, extra=extra)
            result[result.index('--unit') + 1] = 'linux_anon.c'
            return result

        f.arguments = arguments
        original_compiler = f.fake_compiler

        def compiler(command, **keywords):
            result = original_compiler(command, **keywords)
            dep = Path(command[command.index('-MF') + 1])
            target, body = dep.read_text().split(':', 1)
            paths = body.split()
            paths.append(str(self.anon_header))
            if getattr(self, 'omit_file_header', False):
                paths.remove(str(f.overlay / 'sys/sys/file.h'))
            if getattr(self, 'consume_original_filedesc', False):
                paths.append(str(f.source / 'sys/sys/filedesc.h'))
            dep.write_text(target + ': ' + ' '.join(paths) + '\n')
            return result

        f.fake_compiler = compiler

    def test_anon_preflight_records_selected_hash_and_file_header_policy(self):
        f = self.fixture
        self.assertEqual(f.invoke(['--preflight-only']), 0)
        state = f.status()
        self.assertEqual(state['state'], 'PREFLIGHT_PASS')
        self.assertEqual(state['object_compilation'], 'NOT_RUN')
        self.assertEqual(state['provider_contract_sha256'], inputs.ANON_CONTRACT_SHA256)
        self.assertNotEqual(state['provider_contract_sha256'], inputs.CONTRACT_SHA256)
        self.assertEqual(state['required_patched_headers'], ['sys/sys/file.h'])
        self.assertEqual(state['objects'], {})
        self.assertEqual(list(state['precompile_dependencies']), ['linux_anon'])
        proof = state['precompile_dependencies']['linux_anon']
        self.assertIn(str(f.unit), proof)
        self.assertIn(str(self.anon_header), proof)
        self.assertIn(str(f.overlay / 'sys/sys/file.h'), proof)
        self.assertNotIn(str(f.overlay / 'sys/sys/filedesc.h'), proof)
        self.assertEqual(len(f.commands), 1)
        self.assertIn('-M', f.commands[0][0])
        self.assertNotIn('-c', f.commands[0][0])
        self.assertFalse((f.output / 'linux_anon.o').exists())

    def test_anon_compile_mock_requires_independent_scan_and_equal_actual_proof(self):
        f = self.fixture
        self.assertEqual(f.invoke(), 0)
        state = f.status()
        self.assertEqual(state['state'], 'PASS')
        self.assertEqual(list(state['objects']), ['linux_anon'])
        self.assertEqual(state['objects']['linux_anon']['dependency_proof'],
                         state['precompile_dependencies']['linux_anon'])
        self.assertEqual(len(f.commands), 2)
        self.assertIn('-M', f.commands[0][0])
        self.assertIn('-MD', f.commands[1][0])
        self.assertIn('-c', f.commands[1][0])
        for command, keywords in f.commands:
            self.assertIn(str(f.unit), command)
            self.assertNotIn(str(f.provider / 'linux_fd.c'), command)
            self.assertEqual(keywords['cwd'], f.obj)
        self.assertFalse((f.obj / 'linux_anon.o').exists())

    def test_anon_missing_required_file_header_cannot_compile(self):
        f = self.fixture
        self.omit_file_header = True
        with self.assertRaisesRegex(ValueError, 'patched native FILE headers'):
            f.invoke()
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(len(f.commands), 1)

    def test_original_filedesc_is_rejected_even_when_not_required(self):
        f = self.fixture
        self.consume_original_filedesc = True
        with self.assertRaisesRegex(ValueError, 'original version of patched'):
            f.invoke()
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(len(f.commands), 1)

    def test_absent_policy_retains_original_both_header_requirement(self):
        f = self.fixture
        del f.contract['required_patched_headers']
        with self.assertRaisesRegex(ValueError, 'patched native FILE headers'):
            f.invoke()
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(f.status()['required_patched_headers'],
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])
        self.assertEqual(len(f.commands), 1)

    def test_invalid_explicit_policies_fail_before_output_or_scan(self):
        f = self.fixture
        for value in (None, [], 'sys/sys/file.h', [None],
                      ['sys/sys/file.h', 'sys/sys/file.h'],
                      ['sys/sys/filedesc.h'], ['sys/sys/file.h', 'sys/sys/foreign.h'],
                      ['sys/sys/file.h', '../escape.h'],
                      ['sys/sys/file.h', '/sys/sys/filedesc.h'],
                      ['sys/sys/file.h', 'sys/sys/filedesc.c'],
                      ['sys/sys/file.h', 'sys/sys/./filedesc.h']):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                f.contract['required_patched_headers'] = value
                with self.assertRaises(SystemExit):
                    f.invoke(['--preflight-only'])
                self.assertFalse(f.output.exists())
                self.assertEqual(f.commands, [])

    def test_anon_actual_dependency_set_drift_fails_with_receipt(self):
        f = self.fixture
        f.changed_actual_dependencies = True
        with self.assertRaisesRegex(ValueError, 'independent scan'):
            f.invoke()
        self.assertEqual(f.status()['state'], 'FAIL')
        self.assertEqual(len(f.commands), 2)

    def test_anon_contract_cannot_admit_fd_or_second_unit(self):
        f = self.fixture
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            f.invoke(['--unit', 'linux_fd.c'])
        self.assertFalse(f.output.exists())
        self.assertEqual(f.commands, [])

    def test_third_contract_path_rejected_before_output_despite_fixture_loader(self):
        f = self.fixture
        # Even the mocked loader cannot turn an arbitrary metadata path into a selector.
        f.contract_path = fixture_module.write(f.repo / 'arbitrary.json')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            f.invoke(['--preflight-only'])
        self.assertFalse(f.output.exists())
        self.assertEqual(f.commands, [])


if __name__ == '__main__':
    unittest.main()
