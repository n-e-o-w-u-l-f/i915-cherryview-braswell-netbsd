#!/usr/bin/env python3
"""Six strict synthetic-fixture tests of the F09 native Git checker.

This fixture is deliberately NOT the pinned NetBSD source set.
"""
from __future__ import annotations
import difflib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/check_f09_four_original_git.py"
spec = importlib.util.spec_from_file_location("f09_checker", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class F09SourceGateFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="f09-gate-test-")
        self.root = Path(self.temp.name)
        self.original = self.root / "input/sys/test.c"
        self.original.parent.mkdir(parents=True)
        self.preimage = b"alpha\nbeta\ngamma\ndelta\n"
        self.postimage = b"alpha\nbeta-replaced\ngamma\ndelta\n"
        self.original.write_bytes(self.preimage)
        old = self.preimage.decode().splitlines(keepends=True)
        new = self.postimage.decode().splitlines(keepends=True)
        diff = list(difflib.unified_diff(old, new, fromfile="a/sys/test.c",
                                         tofile="b/sys/test.c", n=3))
        self.patch = self.root / "candidate.patch"
        self.patch.write_text("diff --git a/sys/test.c b/sys/test.c\n"+"".join(diff))
        self.before = {"sys/test.c": checker.git_blob(self.preimage)}
        self.after = {"sys/test.c": checker.git_blob(self.postimage)}
        self.patch_sha = checker.git_blob(self.patch.read_bytes())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_gate(self):
        return checker.verify_four_files(self.root / "input", self.patch,
                                         self.before, self.after, self.patch_sha)

    def test_native_git_accepts_fixture(self):
        self.assertEqual(self.run_gate(), self.after)

    def test_original_bytes_remain_unchanged(self):
        self.run_gate()
        self.assertEqual(self.original.read_bytes(), self.preimage)

    def test_corrupt_preimage_rejected(self):
        self.original.write_bytes(self.preimage.replace(b"beta", b"wrong"))
        with self.assertRaisesRegex(ValueError, "original NetBSD Git blob mismatch"):
            self.run_gate()

    def test_corrupt_patch_rejected(self):
        self.patch.write_bytes(self.patch.read_bytes()+b"garbage\n")
        with self.assertRaisesRegex(ValueError, "patch Git blob mismatch"):
            self.run_gate()

    def test_wrong_post_hash_rejected(self):
        self.after["sys/test.c"] = "0"*40
        with self.assertRaisesRegex(ValueError, "patched output Git blob mismatch"):
            self.run_gate()

    def test_missing_file_rejected(self):
        self.original.unlink()
        with self.assertRaisesRegex(ValueError, "missing/linked original"):
            self.run_gate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
