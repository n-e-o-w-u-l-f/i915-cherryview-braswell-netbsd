"""Exact selected-contract generated headers: admission, provenance and drift."""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_source_archive as provenance
import build_hp_native_core_patch as core


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SelectedConfigurationContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hash = sha(b'generated actual configuration')

    def step(self, name, document=None, raw=None):
        path = self.root / (name + '.json')
        data = json.dumps(document).encode() if raw is None else raw.encode()
        path.write_bytes(data)
        return dict(contract=str(path), contract_sha256=sha(data))

    def test_missing_metadata_preserves_default_git_or_archive_admission(self):
        step = self.step('legacy', {'files': {}})
        for mode in (False, True):
            with self.subTest(mode=mode):
                self.assertEqual(provenance.selected_generated_configuration([step], mode),
                                 ({}, []))

    def test_selected_mapping_records_exact_contract_origin(self):
        mapping = {'lockstat.h': self.hash}
        step = self.step('selected', {'generated_configuration': mapping})
        declarations, origins = provenance.selected_generated_configuration([step], True)
        self.assertEqual(declarations, mapping)
        self.assertEqual(origins, [{**step, 'generated_configuration': mapping}])

    def test_non_archive_metadata_is_rejected(self):
        step = self.step('selected', {'generated_configuration': {'lockstat.h': self.hash}})
        with self.assertRaisesRegex(ValueError, 'explicit source archive'):
            provenance.selected_generated_configuration([step], False)

    def test_null_non_object_or_empty_mappings_are_rejected(self):
        for index, mapping in enumerate((None, [], 'header', 1, {})):
            step = self.step(str(index), {'generated_configuration': mapping})
            with self.subTest(mapping=mapping), self.assertRaisesRegex(ValueError, 'nonempty object'):
                provenance.selected_generated_configuration([step], True)

    def test_unsafe_and_opt_names_are_rejected(self):
        names = ('', '.', '..', '/absolute.h', '../outside.h', 'nested/name.h',
                 'nested\\name.h', 'name with space.h', 'tab\tname.h',
                 'new\nname.h', 'nul\x00name.h', '*.h', 'name?.h',
                 'opt_param.h', 'OPT_PARAM.h', 'name.h/../other.h')
        for name in names:
            with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                provenance.validate_generated_configuration({name: self.hash})

    def test_non_string_and_malformed_hashes_are_rejected(self):
        for value in (None, 1, '', 'a' * 63, 'g' * 64, 'A' * 64, 'a' * 65):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'SHA256'):
                provenance.validate_generated_configuration({'lockstat.h': value})

    def test_repeated_declaration_across_contracts_even_same_hash_is_rejected(self):
        for second in (self.hash, '0' * 64):
            first = self.step('first', {'generated_configuration': {'lockstat.h': self.hash}})
            later = self.step('second', {'generated_configuration': {'lockstat.h': second}})
            with self.subTest(second=second), self.assertRaisesRegex(ValueError, 'duplicate'):
                provenance.selected_generated_configuration([first, later], True)

    def test_duplicate_json_keys_even_same_value_are_rejected(self):
        entry = '"lockstat.h":"' + self.hash + '"'
        raw = '{"generated_configuration":{' + entry + ',' + entry + '}}'
        step = self.step('duplicate-key', raw=raw)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            provenance.selected_generated_configuration([step], True)
        raw = '{"generated_configuration":{' + entry + '},"generated_configuration":{' + entry + '}}'
        step = self.step('duplicate-map', raw=raw)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            provenance.selected_generated_configuration([step], True)

    def test_changed_selected_contract_is_rejected(self):
        step = self.step('selected', {'generated_configuration': {'lockstat.h': self.hash}})
        Path(step['contract']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed before'):
            provenance.selected_generated_configuration([step], True)

    def test_unselected_contract_metadata_is_not_read(self):
        self.step('unselected', {'generated_configuration': {'lockstat.h': self.hash}})
        self.assertEqual(provenance.selected_generated_configuration([], True), ({}, []))

    def test_core_rejects_non_archive_declaration_before_output_or_git(self):
        source, obj, tools = [self.root / v for v in ('source', 'obj', 'tools')]
        for path in (source, obj, tools):
            path.mkdir()
        patch = self.root / 'patch';patch.write_text('unused patch')
        contract = self.step('selected', {'generated_configuration': {'lockstat.h': self.hash}})
        output = self.root / 'fresh-output'
        argv = ['builder', '--source', str(source), '--kernel-obj', str(obj),
                '--output', str(output), '--toolchain', str(tools),
                '--patch', str(patch), '--contract', contract['contract']]
        with mock.patch.object(sys, 'argv', argv), \
             mock.patch.object(core, 'require_hp_owner'), \
             mock.patch.object(core, 'toolchain_paths', return_value={'root': tools}), \
             mock.patch.object(core, 'patch_chain', return_value=([contract], {}, {}, [])), \
             mock.patch.object(core, 'create_private_output') as create, \
             mock.patch.object(core, 'checked') as checked, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                core.main()
            self.assertEqual(result.exception.code, 2)
            create.assert_not_called()
            checked.assert_not_called()
        self.assertFalse(output.exists())


class ExactDeclaredHeaderInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.overlay, self.obj = [self.root / v for v in ('source', 'overlay', 'obj')]
        for path in (self.source, self.overlay, self.obj):
            path.mkdir()
        self.body = b'#define NLOCKSTAT 1\n'
        self.header = self.obj / 'lockstat.h'
        self.header.write_bytes(self.body)
        self.mapping = {'lockstat.h': sha(self.body)}

    def bind(self, paths, patched=None, mapping=None):
        return provenance.bind_dependencies(paths, self.source, self.overlay,
            self.obj, {} if patched is None else patched,
            self.mapping if mapping is None else mapping)

    def test_declared_direct_header_is_distinct_from_archive_and_opt_configuration(self):
        opt = self.obj / 'opt_compat_netbsd32.h';opt.write_bytes(b'#define COMPAT_NETBSD32 1\n')
        rows = self.bind([self.header, opt])
        self.assertEqual(rows[str(self.header)]['kind'], 'declared_generated_configuration')
        self.assertEqual(rows[str(opt)]['kind'], 'generated_configuration')
        self.assertEqual(provenance.archive_expectations({}, rows), {})
        self.assertEqual(provenance.declared_configuration_inputs(self.obj, self.mapping),
                         {str(self.header): sha(self.body)})
        provenance.require_declared_configuration_consumed(rows, self.mapping)
        provenance.recheck_dependencies([self.header, opt], rows, self.source,
            self.overlay, self.obj, {}, self.mapping)

    def test_default_without_manifest_still_rejects_non_opt_header(self):
        with self.assertRaisesRegex(ValueError, 'foreign'):
            provenance.bind_dependencies([self.header], self.source, self.overlay,
                                         self.obj, {})

    def test_wrong_declared_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            self.bind([self.header], mapping={'lockstat.h': '0' * 64})

    def test_nested_same_basename_and_undeclared_direct_header_are_rejected(self):
        nested = self.obj / 'nested/lockstat.h';nested.parent.mkdir();nested.write_bytes(self.body)
        other = self.obj / 'other.h';other.write_bytes(self.body)
        for path in (nested, other):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'foreign'):
                self.bind([path])

    def test_symlink_escape_and_even_same_content_symlink_are_rejected(self):
        for directory in (self.root, self.source):
            target = directory / 'target.h';target.write_bytes(self.body)
            self.header.unlink();self.header.symlink_to(target)
            with self.subTest(directory=directory), self.assertRaisesRegex(ValueError, 'direct regular'):
                self.bind([self.header])
            self.header.unlink();self.header.write_bytes(self.body)

    def test_missing_or_directory_instead_of_header_is_rejected(self):
        self.header.unlink()
        with self.assertRaisesRegex(ValueError, 'direct regular'):
            self.bind([])
        self.header.mkdir()
        with self.assertRaisesRegex(ValueError, 'direct regular'):
            self.bind([])

    def test_archive_source_same_basename_cannot_satisfy_declaration(self):
        source_header = self.source / 'lockstat.h';source_header.write_bytes(self.body)
        rows = self.bind([source_header])
        self.assertEqual(rows[str(source_header)]['kind'], 'archive')
        with self.assertRaisesRegex(ValueError, 'not consumed'):
            provenance.require_declared_configuration_consumed(rows, self.mapping)

    def test_patched_overlay_same_basename_cannot_satisfy_declaration(self):
        overlay_header = self.overlay / 'lockstat.h';overlay_header.write_bytes(self.body)
        rows = self.bind([overlay_header], patched={'lockstat.h': sha(self.body)})
        self.assertEqual(rows[str(overlay_header)]['kind'], 'patched')
        with self.assertRaisesRegex(ValueError, 'not consumed'):
            provenance.require_declared_configuration_consumed(rows, self.mapping)

    def test_unused_or_partially_consumed_declaration_is_rejected(self):
        other = self.obj / 'device_count.h';other.write_bytes(b'other')
        mapping = {**self.mapping, 'device_count.h': sha(b'other')}
        rows = self.bind([self.header], mapping=mapping)
        with self.assertRaisesRegex(ValueError, 'not consumed'):
            provenance.require_declared_configuration_consumed(rows, mapping)

    def test_post_preflight_header_drift_is_rejected(self):
        rows = self.bind([self.header])
        self.header.write_bytes(b'#define NLOCKSTAT 2\n')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            provenance.recheck_dependencies([self.header], rows, self.source,
                self.overlay, self.obj, {}, self.mapping)


if __name__ == '__main__':
    unittest.main()
