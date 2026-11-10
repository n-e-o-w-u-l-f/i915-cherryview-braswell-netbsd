"""F35 anonymous-provider identity and narrow header-policy tests; no native execution."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_provider_inputs as admission
import test_native_provider_inputs as f33_fixture
from test_native_provider_inputs import save, sha


class AnonymousProviderInputTests(unittest.TestCase):
    # Reuse private data builders without inheriting or rerunning the F33 tests.
    setUp = f33_fixture.ProviderInputTests.setUp
    core_fixture = f33_fixture.ProviderInputTests.core_fixture
    write_core = f33_fixture.ProviderInputTests.write_core
    verify_core = f33_fixture.ProviderInputTests.verify_core

    def reviewed(self, anonymous=True):
        relative = admission.ANON_CONTRACT_PATH if anonymous else admission.CONTRACT_PATH
        return admission.load_contract(admission.REPOSITORY / relative)

    def copied_contract(self, anonymous=True):
        relative = admission.ANON_CONTRACT_PATH if anonymous else admission.CONTRACT_PATH
        return save(self.repo / relative, (admission.REPOSITORY / relative).read_bytes())

    def test_fixed_second_contract_preserves_first_contract_identity(self):
        first, second = self.reviewed(False), self.reviewed()
        self.assertEqual(admission.CONTRACT_SHA256,
                         'f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3')
        self.assertEqual(admission.ANON_CONTRACT_PATH,
                         'compat/native-file/provider-inputs-f35-anon.json')
        self.assertEqual(admission.ANON_CONTRACT_SHA256,
                         'c45f3ab9f59602955ec5ebe27974a926316787faa0ff57935e3f1c95ac00214d')
        self.assertEqual(second['repository_commit'],
                         '070f728b6ec617c079a4600c14b3e89867f50b18')
        self.assertEqual(second['units'], ['linux_anon.c'])
        self.assertEqual(second['required_patched_headers'], ['sys/sys/file.h'])
        for key in ('netbsd_pin', 'archive_sha256', 'core_status_sha256', 'provider_root',
                    'repository_include_roots', 'native_include_roots'):
            self.assertEqual(second[key], first[key])
        self.assertNotIn('required_patched_headers', first)

    def test_eight_inputs_are_exact_new_owner_and_header_plus_six_prior_headers(self):
        first, second = self.reviewed(False), self.reviewed()
        expected = {name: row for name, row in first['repository_inputs'].items()
                    if name.endswith('.h')}
        expected.update({
            'compat/native-file/linux_anon.c': dict(
                role='translation_unit', blob='2eb1210045024fca9c2d90fdb666847bd65f4444',
                sha256='1b34dab32df905280cc477554afe11a3c434360ac2a3d5638cb3acdda528291e'),
            'compat/native-file/include/linux/anon_inodes_netbsd.h': dict(
                role='anon_header', blob='553f337dd528cbdb5a362a8a1171fd38a8f040b7',
                sha256='4ca1bfa214d70c71dc72a8e93e2f685ca8abc378f019a9f8c2d270674f2be3b4')})
        self.assertEqual(len(expected), 8)
        self.assertEqual(second['repository_inputs'], expected)
        self.assertNotIn('compat/native-file/linux_fd.c', second['repository_inputs'])

    def test_both_source_owned_paths_select_only_their_fixed_digest(self):
        for anonymous, expected in ((False, admission.CONTRACT_SHA256),
                                    (True, admission.ANON_CONTRACT_SHA256)):
            path = self.copied_contract(anonymous)
            with self.subTest(path=path):
                self.assertEqual(admission.reviewed_contract_sha256(path, self.repo), expected)
                self.assertEqual(admission.load_contract(path, self.repo), self.reviewed(anonymous))

    def test_crossed_contract_bytes_rejected_in_both_directions(self):
        first, second = self.copied_contract(False), self.copied_contract()
        first_raw, second_raw = first.read_bytes(), second.read_bytes()
        first.write_bytes(second_raw)
        second.write_bytes(first_raw)
        for path in (first, second):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)

    def test_modified_anonymous_contract_cannot_change_unit_or_policy(self):
        path = self.copied_contract()
        original = json.loads(path.read_bytes())
        for key, value in (('units', ['linux_fd.c']),
                           ('required_patched_headers', []),
                           ('repository_commit', '0' * 40)):
            changed = copy.deepcopy(original)
            changed[key] = value
            path.write_text(json.dumps(changed))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'bytes differ'):
                admission.load_contract(path, self.repo)

    def test_unreviewed_path_and_direct_symlink_cannot_select_contract(self):
        path = self.copied_contract()
        alias = save(self.repo / 'compat/native-file/anonymous-alias.json', path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.reviewed_contract_sha256(alias, self.repo)
        target = save(self.base / 'external.json', path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        for function in (admission.reviewed_contract_sha256, admission.load_contract):
            with self.subTest(function=function.__name__), self.assertRaisesRegex(ValueError, 'source-owned'):
                function(path, self.repo)

    def test_foreign_repository_path_cannot_select_original_source_contract(self):
        self.copied_contract()
        actual = admission.REPOSITORY / admission.ANON_CONTRACT_PATH
        with self.assertRaisesRegex(ValueError, 'source-owned'):
            admission.reviewed_contract_sha256(actual, self.repo)

    def test_selected_contracts_reject_crossed_units_and_include_overrides(self):
        provider = self.repo / 'compat/native-file'
        for anonymous, correct, crossed in ((False, 'linux_fd.c', 'linux_anon.c'),
                                            (True, 'linux_anon.c', 'linux_fd.c')):
            contract = self.reviewed(anonymous)
            expected = ([self.repo / name for name in contract['repository_include_roots']] +
                        [self.source / name for name in contract['native_include_roots']])
            with self.subTest(anonymous=anonymous):
                self.assertEqual(admission.selected_inputs(
                    contract, self.repo, self.source, provider, [correct], []), expected)
                with self.assertRaises(ValueError):
                    admission.selected_inputs(contract, self.repo, self.source,
                                              provider, [crossed], [])
                with self.assertRaises(ValueError):
                    admission.selected_inputs(contract, self.repo, self.source,
                                              provider, [correct], list(reversed(expected)))

    def test_default_and_original_contract_still_require_both_patched_headers(self):
        core = {'patched_inputs': self.patched}
        expected = ['sys/sys/file.h', 'sys/sys/filedesc.h']
        self.assertEqual(admission.provider_header_policy(core), expected)
        self.assertEqual(admission.provider_header_policy(core, {}), expected)
        self.assertEqual(admission.provider_header_policy(core, self.reviewed(False)), expected)
        proof = admission.provider_dependencies(self.provider_paths - {self.patched_desc},
                                               *self.arguments)
        for contract in (None, {}, self.reviewed(False)):
            with self.subTest(contract=contract), self.assertRaisesRegex(ValueError, 'did not consume'):
                admission.require_provider_headers(proof, self.repo, core, contract)

    def test_anonymous_contract_requires_file_header_without_inventing_filedesc_use(self):
        core = {'patched_inputs': self.patched}
        contract = self.reviewed()
        proof = admission.provider_dependencies(self.provider_paths - {self.patched_desc},
                                               *self.arguments)
        self.assertEqual(admission.provider_header_policy(core, contract), ['sys/sys/file.h'])
        admission.require_provider_headers(proof, self.repo, core, contract)
        without_file = {path: row for path, row in proof.items()
                        if row.get('relative') != 'sys/sys/file.h'}
        with self.assertRaisesRegex(ValueError, 'did not consume'):
            admission.require_provider_headers(without_file, self.repo, core, contract)

    def test_explicit_policy_must_be_nonempty_list_of_unique_canonical_headers(self):
        core = {'patched_inputs': self.patched}
        invalid = [None, {}, 'sys/sys/file.h', 1, [],
                   ['sys/sys/file.h', 'sys/sys/file.h'],
                   ['sys/sys/file.h', None],
                   ['sys/sys/file.h', '/sys/sys/filedesc.h'],
                   ['sys/sys/file.h', '../sys/sys/filedesc.h'],
                   ['sys/sys/file.h', 'sys/./sys/filedesc.h'],
                   ['sys/sys/file.h', 'sys//sys/filedesc.h'],
                   ['sys/sys/file.h', 'sys\\sys\\filedesc.h'],
                   ['sys/sys/file.h', 'sys/sys/filedesc.c'],
                   ['sys/sys/file.h', 'sys/sys/filedesc.h '],
                   ['sys/sys/file.h', 'sys/sys/file desc.h'],
                   ['sys/sys/file.h', 'sys/sys/\0filedesc.h']]
        for names in invalid:
            with self.subTest(names=names), self.assertRaises(ValueError):
                admission.provider_header_policy(core, {'required_patched_headers': names})

    def test_policy_cannot_omit_file_header_or_add_header_outside_selected_core(self):
        core = {'patched_inputs': self.patched}
        for names in (['sys/sys/filedesc.h'], ['sys/sys/foreign.h'],
                      ['sys/sys/file.h', 'sys/sys/foreign.h'],
                      ['sys/sys/file.h', 'sys/kern/sys_generic.c']):
            with self.subTest(names=names), self.assertRaises(ValueError):
                admission.provider_header_policy(core, {'required_patched_headers': names})
        with self.assertRaisesRegex(ValueError, 'outside the selected core'):
            admission.provider_header_policy(
                {'patched_inputs': {'sys/sys/filedesc.h': '0' * 64}},
                {'required_patched_headers': ['sys/sys/file.h']})

    def test_valid_explicit_full_subset_is_sorted_and_does_not_change_default(self):
        core = {'patched_inputs': self.patched}
        names = ['sys/sys/filedesc.h', 'sys/sys/file.h']
        self.assertEqual(admission.provider_header_policy(core, {'required_patched_headers': names}),
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])
        self.assertEqual(names, ['sys/sys/filedesc.h', 'sys/sys/file.h'])
        self.assertEqual(admission.provider_header_policy(core),
                         ['sys/sys/file.h', 'sys/sys/filedesc.h'])

    def test_original_filedesc_remains_forbidden_outside_required_subset(self):
        core = {'patched_inputs': self.patched}
        contract = self.reviewed()
        paths = self.provider_paths - {self.patched_desc}
        proof = admission.provider_dependencies(paths, *self.arguments)
        admission.require_provider_headers(proof, self.repo, core, contract)
        original_desc = save(self.source / 'sys/sys/filedesc.h', b'original unpatched FD')
        with self.assertRaisesRegex(ValueError, 'original version of patched input'):
            admission.provider_dependencies(paths | {original_desc}, *self.arguments)
        with self.assertRaisesRegex(ValueError, 'original version of patched input'):
            admission.recheck_provider_dependencies(paths | {original_desc}, proof, *self.arguments)

    def test_lockstat_stays_separate_full_core_input_without_provider_consumption(self):
        core = self.core_fixture()
        contract = self.reviewed()
        proof = admission.provider_dependencies(self.provider_paths - {self.patched_desc},
                                               *self.arguments)
        admission.require_provider_headers(proof, self.repo, core, contract)
        self.assertNotIn(str(self.lockstat), proof)
        self.assertIn(str(self.lockstat), core['objects']['sys_generic']['dependency_proof'])
        self.assertEqual(self.verify_core(), core)
        self.lockstat.write_bytes(b'drift in unused provider configuration')
        with self.assertRaisesRegex(ValueError, 'configuration bytes differ'):
            self.verify_core()
        with self.assertRaisesRegex(ValueError, 'configuration bytes differ'):
            admission.recheck_provider_dependencies(self.provider_paths - {self.patched_desc},
                                                    proof, *self.arguments)


if __name__ == '__main__':
    unittest.main()
