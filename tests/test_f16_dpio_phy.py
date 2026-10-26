#!/usr/bin/env python3
"""Compile exact published F16 C code under generic stubs, never NetBSD ABI."""
from pathlib import Path
import os
import resource
import signal
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_name('test_f16_dpio_phy_model.c')
SOURCE_GIT_BLOB = 'dae4b6eb7e9470167801d019962e0739154d4496'
FLAGS = ('-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined')
MUTATIONS = {
    'wrong_chv_phy0': ('expected = IOSF_PORT_DPIO_2;', 'expected = IOSF_PORT_DPIO;'),
    'wrong_chv_phy1': ('else if (phy == DPIO_PHY1)', 'else if (phy == DPIO_PHY0)'),
    'unguarded_uninit': ('if (i915->dpio_phy_iosf_port[phy] != expected)', 'if (0)'),
    'valleyview_accepts_phy1': ('IS_VALLEYVIEW(i915) && phy == DPIO_PHY0', 'IS_VALLEYVIEW(i915)'),
    'write_skip_invalid': ('if (port < 0)\n\t\treturn;', 'if (0)\n\t\treturn;'),
    'wrong_write_opcode': ('SB_MWR_NP, reg, &val);', 'SB_MRD_NP, reg, &val);'),
}

def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class DpioPhySource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        actual = subprocess.check_output(['git','hash-object',str(SOURCE)], text=True).strip()
        if actual != SOURCE_GIT_BLOB:
            raise ValueError('F16 test C model differs from published exact source')
        cls.source = SOURCE.read_text()
        cls.temp = tempfile.TemporaryDirectory(prefix='f16-dpio-')
        cls.work = Path(cls.temp.name)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def case(self, name, mutation=None):
        code = self.source
        if mutation is not None:
            old,new = MUTATIONS[mutation]
            self.assertEqual(code.count(old), 1, f'{mutation} patch anchor ambiguity')
            code = code.replace(old, new, 1)
        src = self.work/(name+'.c');exe=self.work/name
        src.write_text(code)
        compiled = subprocess.run([os.environ.get('CC','cc'), *FLAGS, str(src), '-o', str(exe)],
            capture_output=True, text=True, timeout=40)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        return subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=15, preexec_fn=no_core)
    def test_exact_native_source_baseline(self):
        result = self.case('baseline')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'F16_EXPLICIT_DPIO_PHY_SOURCE_BASELINE_PASS\n')
    def expected_abort(self, mutation):
        result = self.case(mutation, mutation)
        self.assertEqual(result.returncode, -signal.SIGABRT, result.stderr)
        self.assertIn('CHECK_FAILED', result.stderr)
    def test_wrong_chv_phy0(self): self.expected_abort('wrong_chv_phy0')
    def test_wrong_chv_phy1(self): self.expected_abort('wrong_chv_phy1')
    def test_unguarded_uninit(self): self.expected_abort('unguarded_uninit')
    def test_valleyview_accepts_phy1(self): self.expected_abort('valleyview_accepts_phy1')
    def test_write_skip_invalid(self): self.expected_abort('write_skip_invalid')
    def test_wrong_write_opcode(self): self.expected_abort('wrong_write_opcode')

if __name__ == '__main__':
    unittest.main(verbosity=2)
