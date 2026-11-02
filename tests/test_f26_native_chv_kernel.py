#!/usr/bin/env python3
"""Read-only F26 source/manifest regression; never builds or boots a kernel."""
from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_f26_native_chv_kernel as f26  # noqa: E402
import run_f25_clean_netbsd_console_kernel as f25  # noqa: E402


class TestF26NativeCHV(unittest.TestCase):
    def test_all_11_unique_pinned_patch_files(self):
        self.assertEqual(len(f26.PATCHES), 11)
        names = [name for name, _, _ in f26.PATCHES]
        self.assertEqual(len(set(names)), 11)
        self.assertFalse(any("explicit-phy" in x or "gpll-clock" in x
                             for x in names))
        for name, expected, _ in f26.PATCHES:
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(f25.blob_id(path.read_bytes()), expected, name)

    def test_all_17_original_netbsd_git_blob_pins(self):
        self.assertEqual(len(f26.ORIGINAL), 17)
        paths = set().union(*(set(p[2]) for p in f26.PATCHES))
        self.assertEqual(paths, set(f26.ORIGINAL))
        self.assertTrue(all(len(sha) == 40 for sha in f26.ORIGINAL.values()))
        self.assertEqual(f26.ORIGINAL["sys/arch/x86/x86/consinit.c"],
                         f25.ORIGINAL["sys/arch/x86/x86/consinit.c"])

    def test_actual_git_numstat_matches_each_patch_scope(self):
        for name, _, expected_paths in f26.PATCHES:
            self.assertEqual(f26.patch_paths(ROOT / name),
                             set(expected_paths), name)

    def test_hp_native_version_is_required(self):
        f26.require_native_hp("NetBSD", "11.0", "amd64", "hp-tpnw121")
        f26.require_native_hp("NetBSD", "11.0", "x86_64",
                              "hp-tpnw121.lan")
        for args in (("Linux", "7.2", "x86_64", "legion"),
                     ("NetBSD", "10.0", "amd64", "hp-tpnw121"),
                     ("NetBSD", "12.0", "amd64", "hp-tpnw121"),
                     ("NetBSD", "11.0", "aarch64", "hp-tpnw121"),
                     ("NetBSD", "11.0", "amd64", "legion")):
            with self.subTest(host=args), self.assertRaises(RuntimeError):
                f26.require_native_hp(*args)

    def test_empty_or_unsafe_patch_numstat_is_rejected(self):
        for output in ("", "1\t2\t../etc/passwd\n",
                       "1\t2\t/boot.cfg\n", "nonsense\n"):
            with self.subTest(output=output):
                with mock.patch.object(
                    f26.subprocess, "run",
                    return_value=types.SimpleNamespace(stdout=output)
                ), self.assertRaises(RuntimeError):
                    f26.patch_paths(Path("unused.patch"))

    def test_f25_engine_receives_full_absolute_patch_paths(self):
        keys = ("PATCHES", "ORIGINAL", "CONFIG", "CONFIG_PATH")
        saved = {key: getattr(f25, key) for key in keys}
        try:
            f26.configure_clean_builder()
            self.assertEqual(f25.CONFIG, "F26_CHV_FULL_RTL_TEST")
            self.assertEqual(f25.CONFIG_PATH,
                             "sys/arch/amd64/conf/F26_CHV_FULL_RTL_TEST")
            self.assertEqual(f25.ORIGINAL, f26.ORIGINAL)
            self.assertEqual(f25.PATCHES,
                             [str(ROOT / name) for name, _, _ in f26.PATCHES])
        finally:
            for key, old in saved.items():
                setattr(f25, key, old)

    def test_build_refuses_missing_ack_before_io(self):
        with mock.patch.object(sys, "argv", ["run_f26_native_chv_kernel.py"]):
            with self.assertRaisesRegex(RuntimeError, "ack-compile-only"):
                f26.main()

    def test_wrong_patch_sha_denied_before_source_io(self):
        first = f26.PATCHES[0]
        changed = (first[0], "0" * 40, first[2])
        with mock.patch.object(f26, "PATCHES",
                               (changed, *f26.PATCHES[1:])):
            with self.assertRaisesRegex(RuntimeError, "unverified patch"):
                f26.verify_manifest(Path("/definitely-not-a-netbsd-stage"), ROOT)

    def test_unexpected_patch_scope_denied_before_source_io(self):
        with mock.patch.object(f26, "patch_paths",
                               return_value={"../../private"}):
            with self.assertRaisesRegex(RuntimeError, "out-of-scope"):
                f26.verify_manifest(Path("/definitely-not-a-netbsd-stage"), ROOT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
