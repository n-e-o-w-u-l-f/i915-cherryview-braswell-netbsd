"""F33 provider CLI/admission integration, without invoking a real compiler."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import native_provider_inputs as inputs
from native_source_archive import digest, PIN
spec = importlib.util.spec_from_file_location('f33_provider_builder',
                                             TOOLS / 'build_hp_native_provider.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def write(path, content=b'fixture\n'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class ProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'repo'
        self.provider = self.repo / 'compat/native-file'
        self.unit = write(self.provider / 'linux_fd.c', b'int selected_provider;\n')
        self.repo_header = write(self.provider / 'include/linux/file.h')
        self.source = self.root / 'source'
        self.native = write(self.source / 'sys/native.h')
        self.obj = self.root / 'obj'
        write(self.obj / 'Makefile')
        write(self.obj / 'netbsd')
        self.core_path = write(self.root / 'core/status.json', b'{}\n')
        self.overlay = self.core_path.parent / 'source'
        self.patched = {}
        for name in ('file.h', 'filedesc.h'):
            rel = 'sys/sys/' + name
            write(self.source / rel, b'old\n')
            self.patched[rel] = digest(write(self.overlay / rel, b'new ' + name.encode()))
        configured = self.root / 'configured/sys'
        configured.mkdir(parents=True)
        self.toolroot = self.root / 'tools'
        compiler = write(self.toolroot / 'bin/x86_64--netbsd-gcc')
        make = write(self.toolroot / 'bin/nbmake-amd64')
        compiler.chmod(0o700)
        make.chmod(0o700)
        self.tools = dict(root=self.toolroot, compiler=compiler, make=make)
        self.archive_path = write(self.root / 'pinned.tar.gz')
        self.contract_path = write(self.repo / inputs.CONTRACT_PATH)
        self.contract = dict(provider_root='compat/native-file', units=['linux_fd.c'],
            repository_include_roots=['compat/native-file/include',
                                      'compat/native-mm/include', 'compat/native-uio/include'],
            native_include_roots=['sys/external/bsd/common/include',
                                  'sys/external/bsd/drm2/include'],
            repository_commit='a' * 40, core_status_sha256='b' * 64)
        for rel in self.contract['repository_include_roots']:
            (self.repo / rel).mkdir(parents=True, exist_ok=True)
        for rel in self.contract['native_include_roots']:
            (self.source / rel).mkdir(parents=True)
        self.bindings = {}
        for path in (self.unit, self.repo_header):
            raw = path.read_bytes()
            self.bindings[str(path)] = dict(kind='repository',
                relative=str(path.relative_to(self.repo)), role='fixture',
                blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                sha256=digest(path))
        self.core = dict(state='PASS', netbsd_pin=PIN, patch_chain=[], objects={},
            patched_inputs=self.patched, declared_generated_configuration={},
            source_provenance=dict(verified_source_members={'sys/native.h': digest(self.native)}),
            flags=dict(CC=str(compiler), CFLAGS='-Werror -fstack-usage',
                       CPPFLAGS='-D_KERNEL -nostdinc -I' + str(configured),
                       S=str(configured)), native_tool_sha256={},
            configured_makefile_sha256=digest(self.obj / 'Makefile'),
            prior_kernel_sha256=digest(self.obj / 'netbsd'))
        self.core_path.write_text(json.dumps(self.core))
        self.output = self.root / 'probe'
        self.commands = []
        self.archives = []
        owner = self

        class ArchiveFixture:
            def __init__(self, path):
                self.path = path
                self.verified = None
                owner.archives.append(self)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def verify_source_members(self, expected):
                self.verified = expected
                for rel, value in expected.items():
                    if digest(owner.source / rel) != value:
                        raise ValueError('fixture archive mismatch')
            def receipt(self):
                return dict(mode='ARCHIVE_USED_SUBSET', verified_source_members=self.verified)
            def check_identity(self):
                return None

        self.archive_class = ArchiveFixture

    def arguments(self, archive=True, extra=()):
        argv = ['provider', '--source', str(self.source), '--kernel-obj', str(self.obj),
            '--core-status', str(self.core_path), '--provider-root', str(self.provider),
            '--output', str(self.output), '--toolchain', str(self.toolroot),
            '--unit', 'linux_fd.c']
        if archive:
            argv += ['--source-archive', str(self.archive_path),
                     '--provider-contract', str(self.contract_path)]
        return argv + list(extra)

    def fake_compiler(self, command, **kwargs):
        self.commands.append((command, kwargs))
        dependencies = [self.unit, self.repo_header, self.native] + [
            self.overlay / rel for rel in self.patched]
        if getattr(self, 'omit_patched_header', False):
            dependencies.pop()
        if getattr(self, 'foreign_dependency', False):
            dependencies.append(write(self.provider / 'include/linux/unreviewed.h'))
        if '-MD' in command and getattr(self, 'changed_actual_dependencies', False):
            dependencies.remove(self.repo_header)
        dep = Path(command[command.index('-MF') + 1])
        dep.write_text('linux_fd.o: ' + ' '.join(map(str, dependencies)) + '\n')
        if '-c' in command:
            write(Path(command[command.index('-o') + 1]), b'private object\n')
        if getattr(self, 'mutate_prior', False):
            write(self.obj / 'linux_fd.d', b'forbidden\n')
        returncode = 1 if getattr(self, 'compiler_failure', False) else 0
        return mock.Mock(returncode=returncode, stdout='fixture only\n', stderr='')

    def invoke(self, extra=()):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', self.arguments(extra=extra)))
            stack.enter_context(mock.patch.object(builder, 'require_hp_owner'))
            stack.enter_context(mock.patch.object(builder, 'toolchain_paths', return_value=self.tools))
            stack.enter_context(mock.patch.object(inputs, 'REPOSITORY', self.repo))
            stack.enter_context(mock.patch.object(inputs, 'load_contract', return_value=self.contract))
            stack.enter_context(mock.patch.object(inputs, 'repository_inputs', return_value=self.bindings))
            stack.enter_context(mock.patch.object(inputs, 'verify_core', return_value=self.core))
            stack.enter_context(mock.patch('native_source_archive.ArchiveSource', self.archive_class))
            stack.enter_context(mock.patch.object(builder.subprocess, 'run', side_effect=self.fake_compiler))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return builder.main()

    def status(self):
        return json.loads((self.output / 'status.json').read_bytes())

    def test_paired_flags_rejected_before_host_check_or_output(self):
        for extra in (['--source-archive', str(self.archive_path)],
                      ['--provider-contract', str(self.contract_path)],
                      ['--preflight-only']):
            with self.subTest(extra=extra), mock.patch.object(
                    sys, 'argv', self.arguments(archive=False, extra=extra)), mock.patch.object(
                    builder, 'require_hp_owner') as owner, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    builder.main()
                owner.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_preflight_only_has_no_compile_or_object_pass(self):
        self.assertEqual(self.invoke(['--preflight-only']), 0)
        state = self.status()
        self.assertEqual(state['state'], 'PREFLIGHT_PASS')
        self.assertEqual(state['stage'], 'ADMITTED_NO_OBJECTS')
        self.assertEqual(state['object_compilation'], 'NOT_RUN')
        self.assertEqual(state['objects'], {})
        self.assertEqual(len(self.commands), 1)
        command, keywords = self.commands[0]
        self.assertIn('-M', command)
        self.assertNotIn('-c', command)
        expected_includes = [self.overlay / 'sys'] + [
            self.repo / rel for rel in self.contract['repository_include_roots']] + [
            self.source / rel for rel in self.contract['native_include_roots']]
        self.assertEqual(command[1:7], ['-I' + str(path) for path in expected_includes])
        self.assertEqual(keywords['cwd'], self.obj)
        self.assertEqual(self.archives[0].verified, {'sys/native.h': digest(self.native)})
        self.assertFalse((self.obj / 'linux_fd.d').exists())
        self.assertFalse((self.output / 'linux_fd.o').exists())

    def test_compile_requires_independent_scan_and_equal_actual_dependencies(self):
        self.assertEqual(self.invoke(), 0)
        state = self.status()
        self.assertEqual(state['state'], 'PASS')
        self.assertEqual(len(self.commands), 2)
        self.assertIn('-M', self.commands[0][0])
        self.assertIn('-MD', self.commands[1][0])
        self.assertIn('-c', self.commands[1][0])
        self.assertEqual(state['objects']['linux_fd']['dependency_proof'],
                         state['precompile_dependencies']['linux_fd'])
        self.assertTrue((self.output / 'linux_fd.o').is_file())
        self.assertFalse((self.obj / 'linux_fd.o').exists())

    def test_actual_dependency_set_drift_fails_with_receipt(self):
        self.changed_actual_dependencies = True
        with self.assertRaisesRegex(ValueError, 'independent scan'):
            self.invoke()
        self.assertEqual(self.status()['state'], 'FAIL')
        self.assertEqual(len(self.status()['commands']), 2)

    def test_foreign_repository_header_rejected_before_compile(self):
        self.foreign_dependency = True
        with self.assertRaisesRegex(ValueError, 'unreviewed repository'):
            self.invoke()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.status()['state'], 'FAIL')
        self.assertEqual(self.archives[0].verified, None)

    def test_missing_patched_native_header_rejected_before_compile(self):
        self.omit_patched_header = True
        with self.assertRaisesRegex(ValueError, 'patched native FILE headers'):
            self.invoke()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.status()['state'], 'FAIL')

    def test_native_command_failure_retains_first_log_and_status(self):
        self.compiler_failure = True
        with self.assertRaisesRegex(RuntimeError, 'native provider command failed'):
            self.invoke()
        state = self.status()
        self.assertEqual(state['state'], 'FAIL')
        self.assertEqual(state['commands'][0]['exit_code'], 1)
        self.assertEqual((self.output / 'command-000.log').read_text(), 'fixture only\n')
        self.assertEqual(state['objects'], {})

    def test_original_dependency_creation_is_reported_even_after_preflight(self):
        self.mutate_prior = True
        with self.assertRaisesRegex(RuntimeError, 'original object/dependency/stack artifact'):
            self.invoke(['--preflight-only'])
        self.assertEqual(self.status()['state'], 'FAIL')
        self.assertIn('integrity_error', self.status())

    def test_unselected_unit_and_include_root_fail_before_output_or_command(self):
        for extra in (['--unit', 'other.c'], ['--include-root', str(self.obj)]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.invoke(extra)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.commands, [])

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        marker = write(self.output / 'keep')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke(['--preflight-only'])
        self.assertEqual(marker.read_bytes(), b'fixture\n')
        self.assertEqual(self.commands, [])

    def test_default_mode_still_rejects_dirty_native_git_source(self):
        core = dict(self.core, patched_inputs={})
        self.core_path.write_text(json.dumps(core))
        with mock.patch.object(sys, 'argv', self.arguments(archive=False)), mock.patch.object(
                builder, 'require_hp_owner'), mock.patch.object(
                builder, 'toolchain_paths', return_value=self.tools), mock.patch.object(
                builder, 'core_toolchain_receipt', return_value={}), mock.patch.object(
                builder.subprocess, 'check_output', side_effect=[PIN + '\n', ' M sys/file.h\n']) as git, mock.patch.object(
                builder.subprocess, 'run') as compiler, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                builder.main()
            self.assertEqual(git.call_count, 2)
            self.assertEqual(git.call_args_list[0].args[0][-2:], ['rev-parse', 'HEAD'])
            self.assertEqual(git.call_args_list[1].args[0][-2:], ['status', '--porcelain'])
            compiler.assert_not_called()
            self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
