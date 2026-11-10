"""Explicit optional NetBSD32 admission routing; no syscall or compiler execution."""
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
import build_hp_native_fileops as entry
import build_hp_native_core_patch as core
import check_f32_netbsd32_admission as checker


class OptionalGuardSelection(unittest.TestCase):
    def args(self):
        return ['--source', '/pristine', '--kernel-obj', '/configured',
                '--toolchain', '/tools', '--output', '/private']

    def selected(self, args):
        with patch.object(entry.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(entry.main(args), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, '-B', str(entry.CORE_BUILDER)])
            self.assertEqual(run.call_args.kwargs, {'check': False})
            return command

    def test_omitted_switch_preserves_three_default_pairs(self):
        command = self.selected(self.args())
        self.assertEqual(len(entry.DEFAULT_CHAIN), 3)
        selected = [command[i + 1] for i, value in enumerate(command) if value == '--patch']
        self.assertEqual(selected, [str(row[0]) for row in entry.DEFAULT_CHAIN])
        self.assertNotIn(str(entry.NETBSD32_GUARD[0]), command)

    def test_explicit_guard_appends_fourth_pair_and_archive_is_forwarded(self):
        command = self.selected(self.args() + ['--include-netbsd32-guard',
                                               '--source-archive', '/pinned.tar.gz'])
        self.assertEqual(command[command.index('--source-archive') + 1], '/pinned.tar.gz')
        pairs = entry.DEFAULT_CHAIN + (entry.NETBSD32_GUARD,)
        self.assertEqual([command[i + 1] for i, v in enumerate(command) if v == '--patch'],
                         [str(row[0]) for row in pairs])
        self.assertEqual([command[i + 1] for i, v in enumerate(command) if v == '--contract'],
                         [str(row[1]) for row in pairs])

    def test_fourth_contract_binds_original_owner_predecessor_and_partial_policy(self):
        pairs = entry.DEFAULT_CHAIN + (entry.NETBSD32_GUARD,)
        _, initial, final, units = core.patch_chain(*[list(v) for v in zip(*pairs)])
        contract = json.loads(entry.NETBSD32_GUARD[1].read_text())
        self.assertEqual(set(contract['files']), {checker.RELATIVE})
        self.assertEqual(initial[checker.RELATIVE], checker.BEFORE)
        self.assertEqual(final[checker.RELATIVE], checker.AFTER)
        self.assertEqual(len(units), 3)
        self.assertEqual(contract['prior_patch_sha256'], core.digest(entry.DEFAULT_CHAIN[-1][0]))
        self.assertIs(contract['compat32_translation_implemented'], False)
        self.assertEqual(contract['generated_configuration'], checker.GENERATED_CONFIGURATION)

    def test_arbitrary_patch_override_rejected_before_delegation(self):
        with patch.object(entry.subprocess, 'run') as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                entry.main(self.args() + ['--include-netbsd32-guard', '--patch', '/wrong'])
            self.assertEqual(result.exception.code, 2)
            run.assert_not_called()

    def test_help_marks_guard_as_partial_without_execution(self):
        text = io.StringIO()
        with patch.object(entry.subprocess, 'run') as run, redirect_stdout(text):
            with self.assertRaises(SystemExit) as result:
                entry.main(['--help'])
            self.assertEqual(result.exception.code, 0)
            run.assert_not_called()
        normalized = ' '.join(text.getvalue().split())
        self.assertIn('--include-netbsd32-guard', normalized)
        self.assertIn('no Compat32 translation support', normalized)


if __name__ == '__main__':
    unittest.main(verbosity=2)
