"""Active F30 ownership and FILE ABI CLI routing; no native compiler execution."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_hp_native_core_patch as core
import build_hp_native_fileops as entry
import check_f30_native_ioctl_chain as checker


class ActiveChain(unittest.TestCase):
    def chain(self):
        return core.patch_chain(*[list(values) for values in zip(*entry.DEFAULT_CHAIN)])

    def test_active_default_has_exact_native_owners_and_f29_syscall(self):
        chain, initial, final, units = self.chain()
        self.assertEqual([Path(row['patch']).stem for row in chain],
                         ['dispatch', 'mmap-request', 'early-drm-ioctl'])
        self.assertEqual(initial, checker.BEFORE)
        self.assertEqual(final, checker.FINAL)
        self.assertEqual(set(units), {'sys/kern/sys_generic.c', 'sys/kern/kern_descrip.c'})

    def test_recovered_headers_and_descriptor_owner_are_preserved(self):
        _, _, final, _ = self.chain()
        dispatch = json.loads(entry.DEFAULT_CHAIN[0][1].read_text())
        mmap = json.loads(entry.DEFAULT_CHAIN[1][1].read_text())
        self.assertEqual(final['sys/sys/file.h'], mmap['files']['sys/sys/file.h']['after_sha256'])
        for name in ('sys/sys/filedesc.h', 'sys/kern/kern_descrip.c'):
            self.assertEqual(final[name], dispatch['files'][name]['after_sha256'])
        self.assertEqual(set(json.loads(entry.DEFAULT_CHAIN[-1][1].read_text())['files']),
                         {'sys/kern/sys_generic.c'})

    def test_f29_reference_and_immediate_mmap_predecessor_are_bound(self):
        contract = json.loads(entry.DEFAULT_CHAIN[-1][1].read_text())
        self.assertEqual(contract['prior_patch_sha256'], core.digest(entry.DEFAULT_CHAIN[1][0]))
        self.assertEqual(contract['standalone_f29']['patch_sha256'],
                         core.digest(ROOT / contract['standalone_f29']['path']))
        self.assertEqual(contract['standalone_f29']['sys_generic_sha256'],
                         checker.FINAL['sys/kern/sys_generic.c'])


class PublicEntrypoint(unittest.TestCase):
    def arguments(self, source_flag='--netbsd-source'):
        return [source_flag, '/explicit/source', '--kernel-obj', '/existing/object',
                '--toolchain', '/explicit/tools', '--output', '/new/private']

    def test_existing_and_source_alias_delegate_exact_active_chain(self):
        for source_flag in ('--netbsd-source', '--source'):
            with self.subTest(source_flag=source_flag), patch.object(entry.subprocess, 'run',
                    return_value=SimpleNamespace(returncode=0)) as run:
                self.assertEqual(entry.main(self.arguments(source_flag)), 0)
                command = run.call_args.args[0]
                self.assertEqual(command[:3], [sys.executable, '-B', str(entry.CORE_BUILDER)])
                self.assertEqual(command[3:11], ['--source', '/explicit/source',
                    '--kernel-obj', '/existing/object', '--output', '/new/private',
                    '--toolchain', '/explicit/tools'])
                expected = []
                for candidate, contract in entry.DEFAULT_CHAIN:
                    expected.extend(('--patch', str(candidate), '--contract', str(contract)))
                self.assertEqual(command[11:], expected)
                run.assert_called_once_with(command, check=False)

    def test_core_guard_refusal_exit_is_propagated(self):
        with patch.object(entry.subprocess, 'run', return_value=SimpleNamespace(returncode=2)):
            self.assertEqual(entry.main(self.arguments()), 2)

    def test_missing_toolchain_refuses_before_any_delegation(self):
        arguments = self.arguments()
        offset = arguments.index('--toolchain')
        del arguments[offset:offset + 2]
        with patch.object(entry.subprocess, 'run') as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                entry.main(arguments)
            self.assertEqual(result.exception.code, 2)
            run.assert_not_called()

    def test_arbitrary_patch_override_is_not_a_public_escape(self):
        with patch.object(entry.subprocess, 'run') as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                entry.main(self.arguments() + ['--patch', '/foreign.patch'])
            self.assertEqual(result.exception.code, 2)
            run.assert_not_called()

    def test_help_names_default_chain_without_executing_core(self):
        output = io.StringIO()
        with patch.object(entry.subprocess, 'run') as run, redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                entry.main(['--help'])
            self.assertEqual(result.exception.code, 0)
            run.assert_not_called()
        self.assertIn('mmap-request', output.getvalue())
        self.assertIn('early Linux DRM ioctl/F29 fix', ' '.join(output.getvalue().split()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
