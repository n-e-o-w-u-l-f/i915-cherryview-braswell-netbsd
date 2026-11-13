"""F56 public builder regressions with mocked compiler outputs; NOT_HP_ACCEPTANCE."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_native_four_provider_inputs as fixture

_spec = importlib.util.spec_from_file_location(
    '_f56_archive_fixture', Path(__file__).with_name('test_native_provider_archive_admission.py'))
_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_archive)
inputs, builder = _archive.inputs, _archive.builder


class FourProviderAdmissionTests(unittest.TestCase):
    @contextlib.contextmanager
    def prepared(self, profile):
        f = _archive.ProviderAdmissionTests('test_preflight_only_has_no_compile_or_object_pass')
        f.setUp()
        f.stem, f.filename, f.compiled = profile
        f.contract_relative = fixture.constant(f.stem, 'PATH')
        f.contract_digest = fixture.constant(f.stem, 'SHA256')
        f.contract = copy.deepcopy(inputs.load_contract(inputs.REPOSITORY / f.contract_relative))
        f.provider = f.repo / f.contract['provider_root']
        f.unit = f.provider / f.filename
        f.contract_path = _archive.write(f.repo / f.contract_relative,
            (inputs.REPOSITORY / f.contract_relative).read_bytes())
        f.bindings = {}
        for name, row in f.contract['repository_inputs'].items():
            path = _archive.write(f.repo / name, (inputs.REPOSITORY / name).read_bytes())
            f.bindings[str(path)] = dict(kind='repository', relative=name, **row)
        for name in f.contract['repository_include_roots']:
            (f.repo / name).mkdir(parents=True, exist_ok=True)
        prior_arguments = f.arguments
        def arguments(archive=True, extra=()):
            result = prior_arguments(archive=archive, extra=extra)
            result[result.index('--unit') + 1] = f.filename
            return result
        f.arguments = arguments
        f.core_calls = f.ownership_calls = 0
        try:
            yield f
        finally:
            f.doCleanups()

    def compiler(self, f, command, **keywords):
        f.commands.append((command, keywords))
        paths = [f.repo / name for name in sorted(f.compiled)] + [f.native]
        paths += [f.overlay / rel for rel in f.contract['required_patched_headers']]
        phase = 'MD' if '-MD' in command else 'M'
        missing = getattr(f, 'omit_' + phase, None)
        if missing:
            paths.remove(f.repo / missing)
        proof = getattr(f, 'consume_' + phase, None)
        if proof:
            paths.append(f.repo / proof)
        if getattr(f, 'original_FILE', False):
            paths.append(f.source / 'sys/sys/file.h')
        dep = Path(command[command.index('-MF') + 1])
        dep.write_text(f.unit.stem + '.o: ' + ' '.join(map(str, paths)) + '\n')
        if '-c' in command:
            _archive.write(Path(command[command.index('-o') + 1]),
                           b'private mocked F56 object; NOT_HP_ACCEPTANCE\n')
            drift = getattr(f, 'drift_owner', None)
            if drift:
                path = f.repo / drift; path.write_bytes(path.read_bytes() + b' ')
            if getattr(f, 'drift_prior_artifact', False):
                (f.obj / (f.unit.stem + '.d')).write_bytes(b'changed fixture prior dependency artifact\n')
        return mock.Mock(returncode=0, stdout='mocked compiler only; NOT_HP_ACCEPTANCE\n', stderr='')

    def invoke(self, f, extra=()):
        real_ownership = inputs.verify_four_provider_ownership
        def repository(*args, **kwargs):
            # The production function additionally proves each row with Git.
            # Keep its byte recheck here while the separate input suite exercises Git.
            for name, row in f.contract['repository_inputs'].items():
                raw = (f.repo / name).read_bytes()
                if fixture.sha(raw) != row['sha256'] or fixture.blob(raw) != row['blob']:
                    raise ValueError('fixture Git-bound input bytes drift: ' + name)
            return f.bindings
        def core(*args, **kwargs):
            f.core_calls += 1
            if getattr(f, 'fail_final_core', False) and f.core_calls > 1:
                raise ValueError('fixture full F32 core revalidation failed')
            return f.core
        def ownership(*args, **kwargs):
            f.ownership_calls += 1
            return real_ownership(*args, **kwargs)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', f.arguments(extra=extra)))
            stack.enter_context(mock.patch.object(builder, 'require_hp_owner'))
            stack.enter_context(mock.patch.object(builder, 'toolchain_paths', return_value=f.tools))
            stack.enter_context(mock.patch.object(inputs, 'REPOSITORY', f.repo))
            stack.enter_context(mock.patch.object(inputs, 'load_contract', return_value=f.contract))
            stack.enter_context(mock.patch.object(inputs, 'repository_inputs', side_effect=repository))
            stack.enter_context(mock.patch.object(inputs, 'verify_core', side_effect=core))
            stack.enter_context(mock.patch.object(inputs, 'verify_four_provider_ownership', side_effect=ownership))
            stack.enter_context(mock.patch('native_source_archive.ArchiveSource', f.archive_class))
            stack.enter_context(mock.patch.object(builder.subprocess, 'run',
                                                  side_effect=lambda *a, **k: self.compiler(f, *a, **k)))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return builder.main()

    def test_four_public_profiles_record_matching_M_MD_and_source_ownership_without_Wait_composition(self):
        for profile in fixture.PROFILES:
            with self.subTest(profile=profile[0]), self.prepared(profile) as f:
                self.assertEqual(self.invoke(f), 0)
                state = f.status()
                self.assertEqual((state['state'], state['stage']), ('PASS', 'COMPLETE'))
                self.assertEqual(state['provider_contract_sha256'], f.contract_digest)
                self.assertEqual(state['required_four_provider_inputs'], sorted(f.compiled))
                self.assertEqual(state['four_provider_ownership_proof']['state'],
                                 'VERIFIED_SOURCE_OWNERSHIP_ONLY')
                for name in ('required_task_fragments', 'required_task_worker_inputs',
                             'required_wait_inputs', 'required_poll_inputs', 'required_worker_inputs'):
                    self.assertEqual(state[name], [])
                for name in ('wait_generation_proof', 'poll_generation_proof', 'worker_generation_proof'):
                    self.assertEqual(state[name], {})
                before = state['precompile_dependencies'][f.unit.stem]
                self.assertEqual(before, state['objects'][f.unit.stem]['dependency_proof'])
                self.assertEqual({row['relative'] for row in before.values()
                                  if row['kind'] == 'repository'}, set(f.compiled))
                self.assertFalse(any(row.get('role') in ('api_definition_owner', 'generation_proof_owner')
                                     for row in before.values()))
                self.assertEqual(f.core_calls, 2)
                self.assertEqual(f.ownership_calls, 2)
                self.assertEqual(len(f.commands), 2)
                self.assertIn('-M', f.commands[0][0])
                self.assertIn('-MD', f.commands[1][0])
                self.assertIn('-c', f.commands[1][0])
                for flag in ('-Werror', '-D_KERNEL', '-nostdinc', '-fstack-usage'):
                    self.assertIn(flag, f.commands[1][0])
                self.assertTrue((f.output / (f.unit.stem + '.o')).is_file())
                self.assertFalse((f.obj / (f.unit.stem + '.o')).exists())
                self.assertEqual(state['full_kernel'], 'NOT_RUN')
                self.assertEqual(state['runtime'], 'NOT_RUN')
                self.assertIs(state['installed'], False)
                self.assertIs(state['booted'], False)
                self.assertEqual(f.archives[0].verified, state['source_provenance']['verified_source_members'])

    def test_missing_mandatory_M_input_stops_before_object_command_for_every_profile(self):
        for profile in fixture.PROFILES:
            with self.subTest(profile=profile[0]), self.prepared(profile) as f:
                f.omit_M = fixture.TASK_API if f.stem == 'NATIVE_FILEOPS' else next(
                    name for name in sorted(f.compiled) if name != str(f.unit.relative_to(f.repo)))
                with self.assertRaises(ValueError):
                    self.invoke(f)
                self.assertEqual(len(f.commands), 1)
                self.assertNotIn('-c', f.commands[0][0])
                self.assertEqual(f.status()['state'], 'FAIL')
                self.assertEqual(f.status()['objects'], {})

    def test_missing_actual_MD_input_cannot_complete_any_profile(self):
        for profile in fixture.PROFILES:
            with self.subTest(profile=profile[0]), self.prepared(profile) as f:
                f.omit_MD = fixture.RAW_FILEOPS if f.stem == 'NATIVE_FILEOPS' else next(
                    name for name in sorted(f.compiled) if name != str(f.unit.relative_to(f.repo)))
                with self.assertRaisesRegex(ValueError, 'actual provider dependencies'):
                    self.invoke(f)
                self.assertEqual(len(f.commands), 2)
                self.assertEqual(f.status()['state'], 'FAIL')
                self.assertEqual(f.status()['objects'], {})

    def test_consumed_Task_definition_owner_is_rejected_in_both_phases(self):
        for phase, count in (('M', 1), ('MD', 2)):
            with self.subTest(phase=phase), self.prepared(fixture.PROFILES[1]) as f:
                owner = next(name for name, row in f.contract['repository_inputs'].items()
                             if row['role'] == 'api_definition_owner')
                setattr(f, 'consume_' + phase, owner)
                with self.assertRaisesRegex(ValueError, 'owner is not a provider dependency'):
                    self.invoke(f)
                self.assertEqual(len(f.commands), count)
                self.assertEqual(f.status()['state'], 'FAIL')

    def test_ownership_drift_after_compile_overrides_a_mock_object(self):
        with self.prepared(fixture.PROFILES[1]) as f:
            f.drift_owner = next(name for name, row in f.contract['repository_inputs'].items()
                                 if row['role'] == 'api_definition_owner')
            with self.assertRaises(RuntimeError):
                self.invoke(f)
            state = f.status()
            self.assertEqual(state['state'], 'FAIL')
            self.assertIn('integrity_error', state)
            self.assertEqual(list(state['objects']), [f.unit.stem])
            self.assertEqual(len(f.commands), 2)

    def test_invalid_rebound_ownership_stops_before_output_archive_or_command(self):
        with self.prepared(fixture.PROFILES[1]) as f:
            path = f.repo / fixture.TASK_API; raw = path.read_bytes() + b' '
            path.write_bytes(raw)
            row = f.contract['repository_inputs'][fixture.TASK_API]
            row.update(sha256=fixture.sha(raw), blob=fixture.blob(raw))
            f.bindings[str(path)] = dict(kind='repository', relative=fixture.TASK_API, **row)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                self.invoke(f)
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(f.commands, [])
            self.assertEqual(f.archives, [])
            self.assertFalse(f.output.exists())

    def test_full_F32_core_and_prior_artifact_guards_remain_effective(self):
        for fault in ('fail_final_core', 'drift_prior_artifact'):
            with self.subTest(fault=fault), self.prepared(fixture.PROFILES[0]) as f:
                setattr(f, fault, True)
                with self.assertRaises(RuntimeError):
                    self.invoke(f)
                self.assertEqual(f.status()['state'], 'FAIL')
                self.assertIn('integrity_error', f.status())
                self.assertEqual(len(f.commands), 2)

    def test_original_FILE_cannot_be_consumed_even_when_shmem_needs_no_patched_header(self):
        for profile in fixture.PROFILES:
            with self.subTest(profile=profile[0]), self.prepared(profile) as f:
                f.original_FILE = True
                with self.assertRaisesRegex(ValueError, 'original.*patched|patched.*original'):
                    self.invoke(f)
                self.assertEqual(len(f.commands), 1)
                self.assertEqual(f.status()['state'], 'FAIL')

    def test_preflight_preserves_no_object_result_for_every_profile(self):
        for profile in fixture.PROFILES:
            with self.subTest(profile=profile[0]), self.prepared(profile) as f:
                self.assertEqual(self.invoke(f, ['--preflight-only']), 0)
                state = f.status()
                self.assertEqual(state['state'], 'PREFLIGHT_PASS')
                self.assertEqual(state['object_compilation'], 'NOT_RUN')
                self.assertEqual(state['objects'], {})
                self.assertEqual(len(f.commands), 1)
                self.assertNotIn('-c', f.commands[0][0])
                self.assertFalse((f.output / (f.unit.stem + '.o')).exists())

    def test_wrong_unit_include_order_and_weakened_strict_flags_fail_before_effects(self):
        cases = ('unit', 'includes', 'flags')
        for fault in cases:
            with self.subTest(fault=fault), self.prepared(fixture.PROFILES[0]) as f:
                extra = []
                if fault == 'unit':
                    extra = ['--unit', 'linux_page.c']
                elif fault == 'includes':
                    for name in reversed(f.contract['repository_include_roots']):
                        extra += ['--include-root', str(f.repo / name)]
                else:
                    f.core['flags']['CFLAGS'] = '-fstack-usage'
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    self.invoke(f, extra)
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(f.commands, [])
                self.assertEqual(f.archives, [])
                self.assertFalse(f.output.exists())


if __name__ == '__main__':
    unittest.main()
