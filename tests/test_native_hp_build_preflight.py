#!/usr/bin/env python3
"""HP admission/path regressions only; no compiler, kernel or driver models."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_hp_build as native


class HostAdmission(unittest.TestCase):
    def check(self, **changes):
        values = dict(system='NetBSD', release='11.0', machine='amd64',
                      geteuid=1000, gethostname='hp-tpnw121.lan')
        values.update(changes)
        with patch.object(native.platform, 'system', return_value=values['system']), \
                patch.object(native.platform, 'release', return_value=values['release']), \
                patch.object(native.platform, 'machine', return_value=values['machine']), \
                patch.object(native.os, 'geteuid', return_value=values['geteuid']), \
                patch.object(native.socket, 'gethostname', return_value=values['gethostname']):
            native.require_hp_owner()

    def test_current_and_previous_non_root_owners_are_admitted(self):
        self.check(geteuid=1000)
        self.check(geteuid=1004)

    def test_root_other_host_os_version_and_architecture_are_rejected(self):
        for changes in ({'geteuid': 0}, {'gethostname': 'legion'},
                        {'system': 'Linux'}, {'release': '10.1'},
                        {'machine': 'aarch64'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check(**changes)


class ToolchainAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-hp-tools-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('nbmake-amd64', 'x86_64--netbsd-gcc'):
            path = self.bin / name
            path.write_text('#!/bin/sh\nexit 99\n')
            path.chmod(0o700)

    def test_actual_executable_paths_and_matching_config_are_admitted(self):
        tools = native.toolchain_paths(self.root)
        command = str(self.bin / 'x86_64--netbsd-gcc')
        self.assertEqual(native.configured_compiler(command, tools), [command])

    def test_missing_or_non_executable_tool_is_rejected(self):
        path = self.bin / 'nbmake-amd64'
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            native.toolchain_paths(self.root)
        path.unlink()
        with self.assertRaises(OSError):
            native.toolchain_paths(self.root)

    def test_tool_symlink_escaping_root_is_rejected(self):
        outside = self.root.parent / (self.root.name + '-foreign')
        outside.write_text('not a tool')
        self.addCleanup(outside.unlink)
        path = self.bin / 'nbmake-amd64'
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            native.toolchain_paths(self.root)

    def test_foreign_relative_wrapped_or_additional_compiler_is_rejected(self):
        tools = native.toolchain_paths(self.root)
        for command in ('/usr/tools/bin/x86_64--netbsd-gcc',
                        'x86_64--netbsd-gcc', 'ccache ' + str(tools['compiler']),
                        str(tools['compiler']) + ' -DUNOWNED'):
            with self.subTest(command=command), self.assertRaises((ValueError, OSError)):
                native.configured_compiler(command, tools)


class CoreToolchainReceipt(unittest.TestCase):
    setUp = ToolchainAdmission.setUp

    def receipt(self):
        tools = native.toolchain_paths(self.root)
        return tools, dict(toolchain=str(tools['root']),
                          native_tool_sha256={str(tools[key]):
                              native.hashlib.sha256(tools[key].read_bytes()).hexdigest()
                              for key in ('make', 'compiler')})

    def test_matching_core_provenance_is_retained_without_rebaselining(self):
        tools, receipt = self.receipt()
        admitted = native.core_toolchain_receipt(receipt, tools)
        self.assertEqual(admitted, receipt['native_tool_sha256'])
        self.assertIsNot(admitted, receipt['native_tool_sha256'])

    def test_historical_missing_root_or_tool_hashes_is_rejected(self):
        tools, receipt = self.receipt()
        for key in ('toolchain', 'native_tool_sha256'):
            record = dict(receipt)
            record.pop(key)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'receipt required'):
                native.core_toolchain_receipt(record, tools)

    def test_same_path_tool_drift_after_core_pass_is_rejected(self):
        for key in ('make', 'compiler'):
            with self.subTest(key=key):
                tools, receipt = self.receipt()
                path = tools[key]
                data = path.read_bytes()
                path.write_bytes(data + b'# changed since core PASS\n')
                with self.assertRaisesRegex(ValueError, 'changed since ABI receipt'):
                    native.core_toolchain_receipt(receipt, tools)
                path.write_bytes(data)

    def test_different_core_toolchain_root_is_rejected(self):
        tools, receipt = self.receipt()
        receipt['toolchain'] = str(self.root.parent)
        with self.assertRaisesRegex(ValueError, 'root differs'):
            native.core_toolchain_receipt(receipt, tools)

    def test_core_hashes_for_different_tool_paths_are_rejected(self):
        tools, receipt = self.receipt()
        value = receipt['native_tool_sha256'].pop(str(tools['make']))
        receipt['native_tool_sha256'][str(self.root / 'foreign-nbmake')] = value
        with self.assertRaisesRegex(ValueError, 'paths differ'):
            native.core_toolchain_receipt(receipt, tools)

    def test_malformed_recorded_tool_digest_is_rejected(self):
        tools, receipt = self.receipt()
        for value in (None, 'invalid', 'z' * 64):
            receipt['native_tool_sha256'][str(tools['compiler'])] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid native core'):
                native.core_toolchain_receipt(receipt, tools)


class PrivateOutput(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-hp-output-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()

    def test_owned_fresh_output_is_created_exclusively_with_private_permissions(self):
        path = native.private_output(self.root / 'output', [self.source])
        self.assertFalse(path.exists())
        native.create_private_output(path)
        self.assertEqual(path.stat().st_uid, os.geteuid())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_existing_and_dangling_symlink_outputs_are_preserved(self):
        existing = self.root / 'output'
        existing.write_text('keep this receipt')
        with self.assertRaises(ValueError):
            native.private_output(existing, [self.source])
        self.assertEqual(existing.read_text(), 'keep this receipt')
        link = self.root / 'dangling'
        link.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError):
            native.private_output(link, [self.source])
        self.assertTrue(link.is_symlink())

    def test_output_inside_input_or_input_symlink_is_rejected(self):
        link = self.root / 'source-alias'
        link.symlink_to(self.source, target_is_directory=True)
        for output in (self.source / 'output', link / 'output'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                native.private_output(output, [self.source])

    def test_exclusive_mkdir_preserves_path_created_after_preflight(self):
        output = native.private_output(self.root / 'raced', [self.source])
        output.write_text('other writer')
        with self.assertRaises(FileExistsError):
            native.create_private_output(output)
        self.assertEqual(output.read_text(), 'other writer')

    def test_sticky_shared_parent_is_admitted_for_safe_temporary_workflows(self):
        shared = self.root / 'shared'
        shared.mkdir()
        shared.chmod(0o1777)
        actual_stat = Path.stat
        def stat_other_owner(path, *args, **kwargs):
            info = actual_stat(path, *args, **kwargs)
            if path == shared:
                class Info:
                    st_mode = info.st_mode
                    st_uid = os.geteuid() + 1
                return Info()
            return info
        with patch.object(Path, 'stat', stat_other_owner):
            output = native.private_output(shared / 'private', [self.source])
        native.create_private_output(output)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)

    def test_unowned_non_sticky_parent_is_rejected_without_creating_output(self):
        with patch.object(native.os, 'geteuid', return_value=os.geteuid() + 1):
            with self.assertRaises(ValueError):
                native.private_output(self.root / 'output', [self.source])
        self.assertFalse((self.root / 'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
