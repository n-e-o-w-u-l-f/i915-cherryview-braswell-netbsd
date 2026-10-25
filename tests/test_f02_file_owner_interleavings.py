#!/usr/bin/env python3
"""Compile and verify F02 bounded reference-order C model on a generic host.

Tests are source-only accounting, not data-race checks or NetBSD kernel ABI.
All compiler outputs live in an automatically cleaned temporary directory.
"""
from __future__ import annotations

import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_suffix(".c")
FLAGS = (
    "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
    "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
)
FAILURES = {
    "double_native_close": "o->native_refs > 0 && o->native_attached",
    "borrow_after_close": "linux_view_get(&o)",
    "premature_worker_drain": "o->deferred && o->linux_refs == 0 && !o->released",
    "double_linux_put": "o->linux_refs > 0 && !o->released",
}


def disable_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class F02BoundedInterleavings(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="f02-interleave-")
        cls.binary = Path(cls.temp.name) / "interleave"
        command = [os.environ.get("CC", "cc"), *FLAGS, str(SOURCE),
                   "-o", str(cls.binary)]
        built = subprocess.run(command, capture_output=True, text=True,
                               check=False, timeout=120)
        if built.returncode != 0:
            cls.temp.cleanup()
            raise AssertionError("strict C11/UBSan build failed: " + built.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def run_case(self, name: str | None = None) -> subprocess.CompletedProcess[str]:
        command = [str(self.binary)]
        if name:
            command.append(name)
        return subprocess.run(command, capture_output=True, text=True,
                              check=False, timeout=30, preexec_fn=disable_core)

    def test_all_bounded_release_orders(self) -> None:
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "F02_INTERLEAVINGS_PASS 4428_PATHS\n")
        self.assertEqual(result.stderr, "")

    def test_double_native_close_rejected(self) -> None:
        self.check_negative("double_native_close")

    def test_linux_view_after_native_close_rejected(self) -> None:
        self.check_negative("borrow_after_close")

    def test_premature_worker_drain_rejected(self) -> None:
        self.check_negative("premature_worker_drain")

    def test_double_linux_put_rejected(self) -> None:
        self.check_negative("double_linux_put")

    def check_negative(self, name: str) -> None:
        result = self.run_case(name)
        self.assertEqual(result.returncode, -signal.SIGABRT, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("CHECK_FAILED ", result.stderr)
        self.assertIn(FAILURES[name], result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
