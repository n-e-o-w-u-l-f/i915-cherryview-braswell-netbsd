"""Admission checks for ordered native patches; these are not native ABI tests."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('native_core', ROOT/'tools/build_hp_native_core_patch.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class ChainAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def contract(self, index, files, **extra):
        patch = self.root/f'{index}.patch'
        patch.write_bytes(f'patch {index}'.encode())
        record = dict(netbsd_pin=core.PIN, patch_sha256=core.digest(patch),
                      files={name: dict(before_sha256=before, after_sha256=after)
                             for name, (before, after) in files.items()}, **extra)
        contract = self.root/f'{index}.json'
        contract.write_text(json.dumps(record), encoding='utf8')
        return patch, contract

    def valid(self):
        first = self.contract(1, {'sys/uvm/map.c': ('a'*64, 'b'*64),
                                  'sys/uvm/map.h': ('c'*64, 'd'*64)})
        second = self.contract(2, {'sys/uvm/map.c': ('b'*64, 'e'*64),
                                   'sys/uvm/mm.h': ('f'*64, '0'*64)},
                               prior_entry_patch_sha256=core.digest(first[0]))
        return [first[0], second[0]], [first[1], second[1]]

    def test_ordered_composition_keeps_original_and_final(self):
        chain, initial, final, units = core.patch_chain(*self.valid())
        self.assertEqual(initial['sys/uvm/map.c'], 'a'*64)
        self.assertEqual(final['sys/uvm/map.c'], 'e'*64)
        self.assertEqual(units, ['sys/uvm/map.c'])
        self.assertEqual(len(chain), 2)

    def test_wrong_order_refused(self):
        patches, contracts = self.valid()
        with self.assertRaisesRegex(ValueError, 'predecessor'):
            core.patch_chain(patches[::-1], contracts[::-1])

    def test_noncomposing_source_digest_refused(self):
        patches, contracts = self.valid()
        data = json.loads(contracts[1].read_text())
        data['files']['sys/uvm/map.c']['before_sha256'] = '9'*64
        contracts[1].write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'noncomposing'):
            core.patch_chain(patches, contracts)

    def test_patch_drift_refused(self):
        patches, contracts = self.valid()
        patches[0].write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'identity'):
            core.patch_chain(patches, contracts)

    def test_duplicate_and_unpaired_refused(self):
        patches, contracts = self.valid()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            core.patch_chain([patches[0]]*2, [contracts[0]]*2)
        with self.assertRaisesRegex(ValueError, 'one ordered'):
            core.patch_chain(patches[:1], contracts)

    def test_unsafe_source_path_refused(self):
        patch, contract = self.contract(3, {'sys/../evil.c': ('a'*64, 'b'*64)})
        with self.assertRaisesRegex(ValueError, 'unqualified'):
            core.patch_chain([patch], [contract])

    def test_missing_c_owner_refused(self):
        patch, contract = self.contract(4, {'sys/uvm/map.h': ('a'*64, 'b'*64)})
        with self.assertRaisesRegex(ValueError, 'C owners'):
            core.patch_chain([patch], [contract])

    def test_ambiguous_output_name_refused(self):
        patch, contract = self.contract(5, {'sys/a/map.c': ('a'*64, 'b'*64),
                                           'sys/b/map.c': ('c'*64, 'd'*64)})
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            core.patch_chain([patch], [contract])


if __name__ == '__main__':
    unittest.main()
