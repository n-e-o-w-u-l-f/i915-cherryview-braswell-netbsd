#!/usr/bin/env python3
"""Deterministic parser regression tests, not kernel ABI acceptance."""
import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "tools/audit_f07_fileops_initializers.py"
spec = importlib.util.spec_from_file_location("f07_scan", P)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class TestFileopsShape(unittest.TestCase):
    def test_in_tree_drm_designated(self):
        self.assertEqual(scanner.scan('const struct fileops drm_fileops = {\n'
                                      '  .fo_name = "drm", .fo_ioctl = shim,\n};'),
                         [('drm_fileops', True, 1)])

    def test_positional_detected(self):
        self.assertEqual(scanner.scan('static struct fileops ops = { open, read };'),
                         [('ops', False, 1)])

    def test_commented_positional_ignored(self):
        self.assertEqual(scanner.scan('/* struct fileops fake = { zero }; */\n'
                                      'struct fileops real = { /*note*/ .fo_close = close };'),
                         [('real', True, 2)])

    def test_multiline_declaration(self):
        self.assertEqual(scanner.scan('static const struct\nfileops\n'
                                      'more = {\n .fo_ioctl = fn,\n};'),
                         [('more', True, 1)])

    def test_zero_initializer_reviewed(self):
        self.assertEqual(scanner.scan('const struct fileops zero = {0};'),
                         [('zero', False, 1)])

    def test_no_false_declaration(self):
        self.assertEqual(scanner.scan('struct fileops;\n'
                                      'const struct fileops *fp = getops();'), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
