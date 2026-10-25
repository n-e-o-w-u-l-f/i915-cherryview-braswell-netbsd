#!/usr/bin/env python3
"""Exact NetBSD pinned ioctl preparation excerpt: host C11/UBSan tests only."""
from __future__ import annotations
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parent
C = BASE / "test_f10_ioctl_direction_model.c"
FIX = BASE / "fixtures/f10_netbsd_sys_ioctl_prep_03d918f6.inc"
FIX_SHA = "26aa9e2f12e3fb9077dc594e22cf13808f03b1ec"
C_SHA = "4b969aa9338b13e5803412f2ef1bcb49a0739db2"
FLAGS = ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=undefined", "-fno-sanitize-recover=undefined"]
MUTANTS = {
    "swap_directions": (
        "if (com&IOC_IN) {", "if (com&IOC_OUT) {",
        "else if ((com&IOC_OUT) && size) {", "else if ((com&IOC_IN) && size) {"),
    "wrong_zero": ("memset(data, 0, zero_size(size));", "memset(data, 0x11, zero_size(size));"),
    "skip_copyin": ("error = copyin(SCARG(uap, data), data, size);", "error = 0;"),
}

def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class F10DirectionAbi(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="f10-direction-")
        self.work = Path(self.temp.name)
        (self.work / "fixtures").mkdir()
        shutil.copyfile(C, self.work / C.name)
        shutil.copyfile(FIX, self.work / "fixtures" / FIX.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_pinned_fixture_and_source_blobs(self):
        for path, expected in ((FIX, FIX_SHA), (C, C_SHA)):
            got = subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()
            self.assertEqual(got, expected)

    def compile_run(self, name="actual"):
        binary = self.work / "test"
        r = subprocess.run([os.environ.get("CC", "cc"), *FLAGS, str(self.work / C.name),
                            "-o", str(binary)], capture_output=True, text=True, timeout=50)
        self.assertEqual(r.returncode, 0, r.stderr)
        return subprocess.run([str(binary)], capture_output=True, text=True,
                              timeout=20, preexec_fn=no_core)

    def test_exact_original_directions(self):
        result = self.compile_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
            "F10_NETBSD_LINUX_IOCTL_DIRECTION_MISMATCH_CONFIRMED 3_DIRECTIONS\n")

    def mutant(self, name):
        contents = (self.work / "fixtures" / FIX.name).read_text()
        parts = MUTANTS[name]
        if name == "swap_directions":
            a,b,c,d = parts
            self.assertEqual(contents.count(a), 1)
            self.assertEqual(contents.count(c), 1)
            contents = contents.replace(a,b,1).replace(c,d,1)
        else:
            a,b = parts
            self.assertEqual(contents.count(a),1)
            contents = contents.replace(a,b,1)
        (self.work / "fixtures" / FIX.name).write_text(contents)
        r = self.compile_run(name)
        self.assertEqual(r.returncode, -signal.SIGABRT, r.stderr)
        self.assertIn("CHECK_FAILED ", r.stderr)

    def test_swap_directions_detected(self):
        self.mutant("swap_directions")

    def test_wrong_zero_detected(self):
        self.mutant("wrong_zero")

    def test_skip_copyin_detected(self):
        self.mutant("skip_copyin")

if __name__ == "__main__":
    unittest.main(verbosity=2)
