#!/usr/bin/env python3
"""Strict standalone size-domain model, NOT native NetBSD kernel ABI acceptance."""
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
    'MUTATE_LINUX_SIZE_MASK_13': 'LINUX_SIZE(high) == 8192 && NETBSD_SIZE(high) == 0',
    'MUTATE_SKIP_DRIVER_SIZE': 'linux_ksize(8, 8, sizeof(struct drm_get_cap_pinned)) == 16',
    'MUTATE_PAGE_EDGE': 'accepted_by_netbsd(NETBSD_SIZE(edge))',
    'MUTATE_TRUST_USER_SIZE': '!safe_kernel_data_capacity(NETBSD_SIZE(small), 16)',
}
def suppress_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class IoctlSizeAbi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory(prefix='f05-ioctl-size-')
        cls.path = Path(cls.dir.name)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def compile_and_run(self, mutant: str | None = None):
        exe = self.path / (mutant or 'actual')
        args = [os.environ.get('CC', 'cc'), *FLAGS]
        if mutant:
            args.append('-D' + mutant)
        args += [str(SOURCE), '-o', str(exe)]
        compiled = subprocess.run(args, capture_output=True, text=True,
                                  timeout=60, check=False)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        return subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=30, check=False, preexec_fn=suppress_core)

    def test_original_13_contracts(self):
        r = self.compile_and_run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        self.assertEqual(r.stdout, 'F05_IOCTL_SIZE_ABI_MODEL_PASS 13_CONTRACTS\n')

    def check_mutant(self, name):
        r = self.compile_and_run(name)
        self.assertEqual(r.returncode, -signal.SIGABRT, r.stderr)
        self.assertEqual(r.stdout, '')
        self.assertIn('CHECK_FAILED ' + MUTANTS[name], r.stderr)

    def test_mutant_linux_mask(self):
        self.check_mutant('MUTATE_LINUX_SIZE_MASK_13')

    def test_mutant_driver_size(self):
        self.check_mutant('MUTATE_SKIP_DRIVER_SIZE')

    def test_mutant_page_boundary(self):
        self.check_mutant('MUTATE_PAGE_EDGE')

    def test_mutant_capacity_admission(self):
        self.check_mutant('MUTATE_TRUST_USER_SIZE')

if __name__ == '__main__':
    unittest.main(verbosity=2)
