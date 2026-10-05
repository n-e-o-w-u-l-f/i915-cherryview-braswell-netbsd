#!/usr/bin/env python3
"""Exercise source staging on disposable Git fixtures; never invoke a compiler."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools/materialize_linux_i915.py"
PATHS = ("drivers/gpu/drm/i915", "drivers/gpu/drm/display",
         "drivers/gpu/drm/ttm", "include/drm", "include/uapi/drm")

class MaterializeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "linux"
        self.output = self.root / "output"
        for name in PATHS:
            directory = self.source / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "fixture.c").write_text("/* " + name + " */\n")
        (self.source / "drivers/gpu/drm/Makefile").write_text("fixture := y\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "source fixture")

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.source), *arguments], text=True)

    def invoke(self, allow=True):
        arguments = [sys.executable, str(TOOL), "--linux-tree", str(self.source),
                     "--out", str(self.output)]
        if allow:
            arguments.append("--allow-unverified-linux-head")
        return subprocess.run(arguments, text=True, capture_output=True)

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("user work\n")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sentinel.read_text(), "user work\n")

    def test_missing_root_creates_no_partial_output(self):
        directory = self.source / "drivers/gpu/drm/display"
        (directory / "fixture.c").unlink()
        directory.rmdir()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_sparse_missing_file_creates_no_output(self):
        (self.source / "include/drm/fixture.c").unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_dirty_source_is_rejected(self):
        (self.source / "drivers/gpu/drm/i915/fixture.c").write_text("changed\n")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_missing_git_identity_is_rejected_by_default(self):
        self.source = self.root / "plain"
        for name in PATHS:
            directory = self.source / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "fixture.c").write_text("plain\n")
        result = self.invoke(allow=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_complete_fixture_copies_exact_bytes(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((self.output / "PORT-MANIFEST.json").read_text())
        self.assertEqual(manifest["total_file_count"], 6)
        self.assertEqual(manifest["linux_head_observed"], self.git("rev-parse", "HEAD").strip())
        for entry in manifest["files"]:
            self.assertEqual((self.output / entry["path"]).read_bytes(),
                             (self.source / entry["path"]).read_bytes())

if __name__ == "__main__":
    unittest.main()
