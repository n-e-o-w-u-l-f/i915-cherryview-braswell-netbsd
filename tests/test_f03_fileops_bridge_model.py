#!/usr/bin/env python3
"""Strict generic-host C oracle for F03 bridge; NOT a NetBSD kernel build."""
from __future__ import annotations
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_suffix('.c')
FLAGS = ('-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined')
MUTANTS = {
    'F03_MUTATE_IGNORE_USER_CALLBACK': 'dispatch(&f, true, sizeof(user), &user) == -9',
    'F03_MUTATE_LEGACY_ERROR_COPYOUT': 'user == 111 && copies == 0 && old_calls == 1',
    'F03_MUTATE_NO_ERROR_COPYOUT': 'user == 37 && copies == 2 && user_calls == 1',
    'F03_MUTATE_DROP_STRONG_REF': 'borrow == &linux && borrow->refs == 2',
    'F03_MUTATE_EARLY_FD_PUT': 'f->active && f->pins != 0',
}

def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class F03BridgeModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='f03-bridge-')
        cls.out = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compile_and_run(self, variant=None):
        binary = self.out / (variant or 'actual').lower()
        args = [os.environ.get('CC', 'cc'), *FLAGS]
        if variant:
            args.append('-D' + variant)
        args.extend((str(SOURCE), '-o', str(binary)))
        built = subprocess.run(args, text=True, capture_output=True, check=False, timeout=90)
        self.assertEqual(built.returncode, 0, built.stderr)
        return subprocess.run([str(binary)], text=True, capture_output=True,
                              check=False, timeout=30, preexec_fn=no_core)

    def test_actual_ten_contracts(self):
        result = self.compile_and_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'F03_FILEOPS_BRIDGE_MODEL_PASS 10_CONTRACTS\n')
        self.assertEqual(result.stderr, '')

    def check_mutant(self, variant):
        result = self.compile_and_run(variant)
        self.assertEqual(result.returncode, -signal.SIGABRT, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('CHECK_FAILED ' + MUTANTS[variant], result.stderr)

    def test_missing_user_callback_detected(self):
        self.check_mutant('F03_MUTATE_IGNORE_USER_CALLBACK')

    def test_legacy_error_copyout_detected(self):
        self.check_mutant('F03_MUTATE_LEGACY_ERROR_COPYOUT')

    def test_missing_optin_error_copyout_detected(self):
        self.check_mutant('F03_MUTATE_NO_ERROR_COPYOUT')

    def test_borrowed_pointer_not_strong_detected(self):
        self.check_mutant('F03_MUTATE_DROP_STRONG_REF')

    def test_native_pin_dropped_too_early_detected(self):
        self.check_mutant('F03_MUTATE_EARLY_FD_PUT')

if __name__ == '__main__':
    unittest.main(verbosity=2)
