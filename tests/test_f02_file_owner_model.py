#!/usr/bin/env python3
"""F02 host-independent FILE-owner C-model checks (NOT a NetBSD ABI test).

Compiles the source-only reference model with C11 -Werror and UBSan into an
isolated TemporaryDirectory. Validates six positive accounting scenarios and
four *deliberately incorrect* compile-time semantic mutations. Never SSHes,
modifies a kernel tree, or accesses HP-owned logs/source.
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
    "-std=c11",
    "-O1",
    "-g",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-fsanitize=undefined",
    "-fno-sanitize-recover=undefined",
)
EXPECTED_MUTANTS = {
    "MUTATE_EARLY_RELEASE": "!o.native_attached && o.linux_refs == 1",
    "MUTATE_DROP_MODULE_PIN":
        "o->module_pin && o->task_spare && o->work_reserved",
    "MUTATE_UNSLEEPABLE_SYNC": "sleepable",
    "MUTATE_SKIP_SPARE":
        "o->module_pin && o->task_spare && o->work_reserved",
}


def limit_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class FileOwnerModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="f02-file-owner-model-")
        cls.out = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def compile_and_run(self, mutation: str | None) -> subprocess.CompletedProcess[str]:
        suffix = mutation or "actual"
        output = self.out / suffix.lower()
        command = [os.environ.get("CC", "cc"), *FLAGS]
        if mutation:
            command.append("-D" + mutation)
        command.extend((str(SOURCE), "-o", str(output)))
        build = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=120
        )
        self.assertEqual(
            build.returncode, 0,
            msg=f"{suffix} failed strict C11/UBSan compilation:\n{build.stderr}"
        )
        return subprocess.run(
            [str(output)], check=False, capture_output=True, text=True,
            timeout=30, preexec_fn=limit_core
        )

    def test_actual_six_scenarios(self) -> None:
        result = self.compile_and_run(None)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout, "F02_FILE_OWNER_MODEL_PASS 6_SCENARIOS\n")
        self.assertEqual(result.stderr, "")

    def test_early_linux_release_detected(self) -> None:
        self.check_mutant("MUTATE_EARLY_RELEASE")

    def test_lost_module_pin_detected(self) -> None:
        self.check_mutant("MUTATE_DROP_MODULE_PIN")

    def test_non_sleepable_finalizer_detected(self) -> None:
        self.check_mutant("MUTATE_UNSLEEPABLE_SYNC")

    def test_missing_task_spare_detected(self) -> None:
        self.check_mutant("MUTATE_SKIP_SPARE")

    def check_mutant(self, mutation: str) -> None:
        result = self.compile_and_run(mutation)
        self.assertEqual(result.returncode, -signal.SIGABRT)
        self.assertEqual(result.stdout, "")
        self.assertIn("CHECK_FAILED ", result.stderr)
        self.assertIn(EXPECTED_MUTANTS[mutation], result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
