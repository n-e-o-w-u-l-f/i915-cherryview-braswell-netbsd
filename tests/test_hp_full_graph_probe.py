#!/usr/bin/env python3
"""Synthetic native-command admission controls; runs no compiler or make."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import probe_hp_full_graph as probe


def elf():
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[16:24] = b"\x01\x00\x3e\x00\x01\x00\x00\x00"
    header[52:54] = b"\x40\x00"
    return bytes(header)


class FreshProbe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.tree, self.obj, self.tools, self.base, self.output = [self.work / name for name in ("tree", "obj", "tools", "base", "out")]
        for path in (self.tree, self.obj, self.tools, self.base, self.output):
            path.mkdir()
        self.source = self.tree / "sys/external/bsd/drm2/dist/drm/test.c"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"int actual_source;\n")
        self.header = self.tree / "sys/header.h"
        self.header.write_bytes(b"#define VALUE 1\n")
        self.item = {"group": "drm", "source": self.source.relative_to(self.tree / "sys").as_posix(),
                     "object": "test.o", "source_sha256": probe.digest(self.source)}
        self.dependency, self.artifact = self.obj / "test.d", self.obj / "test.o"

    def dependencies(self):
        self.dependency.write_text("test.o: " + self.source.as_posix() + " \\\n " + self.header.as_posix() + "\n")

    def compile(self, command=None):
        def successful(command, obj, env, log, timeout):
            if command[-1] == "test.d":
                self.dependencies()
            else:
                self.artifact.write_bytes(elf())
            return 0
        with patch.object(probe, "run_command", side_effect=command or successful) as runner:
            row = probe.compile_one(self.item, self.tree, self.obj, self.tools,
                                    self.base, self.output, {}, 1)
        return row, runner

    def test_fresh_native_command_model_retains_exact_inputs_and_elf(self):
        row, runner = self.compile()
        self.assertEqual(row["state"], "PASSED")
        self.assertEqual(runner.call_count, 2)
        self.assertTrue(row["source_unchanged"] and row["inputs_unchanged"] and row["dependency_graph_unchanged"])
        inputs = json.loads(Path(row["input_inventory"]["path"]).read_text())
        self.assertEqual(set(inputs), {str(self.source), str(self.header)})

    def test_stale_object_or_dependency_prevents_any_native_command(self):
        for path in (self.artifact, self.dependency):
            with self.subTest(path=path):
                path.write_text("preserved")
                row, runner = self.compile()
                self.assertEqual(row["state"], "FAILED")
                runner.assert_not_called()
                self.assertEqual(path.read_text(), "preserved")
                path.unlink()

    def test_source_drift_prevents_native_command(self):
        self.source.write_text("changed")
        row, runner = self.compile()
        self.assertEqual(row["state"], "FAILED")
        runner.assert_not_called()

    def test_failed_dependency_retains_failure_without_object_command(self):
        row, runner = self.compile(lambda *args: 1)
        self.assertEqual(row["state"], "FAILED")
        self.assertEqual(row["d_exit"], 1)
        self.assertNotIn("o_exit", row)
        self.assertEqual(runner.call_count, 1)

    def test_zero_exit_without_new_dependency_is_rejected(self):
        row, runner = self.compile(lambda *args: 0)
        self.assertEqual(row["state"], "FAILED")
        self.assertEqual(runner.call_count, 1)

    def test_changed_real_header_rejects_object(self):
        def command(argv, *args):
            if argv[-1] == "test.d":
                self.dependencies()
            else:
                self.header.write_text("changed")
                self.artifact.write_bytes(elf())
            return 0
        row, _ = self.compile(command)
        self.assertEqual(row["state"], "FAILED")
        self.assertFalse(row["inputs_unchanged"])

    def test_fake_non_elf_output_is_rejected(self):
        def command(argv, *args):
            if argv[-1] == "test.d":
                self.dependencies()
            else:
                self.artifact.write_bytes(b"not an object")
            return 0
        row, _ = self.compile(command)
        self.assertEqual(row["state"], "FAILED")
        self.assertIn("ELF relocatable", row["error"])

    def test_dependency_cannot_escape_private_inputs(self):
        outside = self.work / "outside.h"
        outside.write_text("unadmitted")
        self.dependency.write_text("test.o: " + self.source.as_posix() + " " + outside.as_posix())
        with self.assertRaisesRegex(RuntimeError, "escapes"):
            probe.dependency_inputs(self.dependency, self.source, self.tree, self.obj, self.base)

    def test_dependency_must_bind_actual_source(self):
        self.dependency.write_text("test.o: " + self.header.as_posix())
        with self.assertRaisesRegex(RuntimeError, "selected C source"):
            probe.dependency_inputs(self.dependency, self.source, self.tree, self.obj, self.base)


if __name__ == "__main__":
    unittest.main()
