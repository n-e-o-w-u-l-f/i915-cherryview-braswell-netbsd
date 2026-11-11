"""F50 same-read Worker generation provenance; no producer or native execution."""
import contextlib
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_native_worker_provider_inputs as fixture
admission = fixture.admission


class WorkerGenerationProvenanceTests(unittest.TestCase, fixture.WorkerFixture):
    setUp = fixture.WorkerFixture.setUp

    def test_positive_proof_is_source_only_and_crosslinks_all_seven_origins(self):
        receipt = self.generation()
        self.assertEqual(receipt['state'], 'VERIFIED_WORKER_SOURCE_GENERATION_ONLY')
        self.assertEqual(receipt['provenance'], fixture.PROVENANCE)
        self.assertEqual(receipt['provenance_sha256'], self.contract['generation_provenance_sha256'])
        self.assertEqual(receipt['repository_input_commit'], 'e7d7100c44322d3209d8f43d1d3a3842b52b340b')
        self.assertEqual(receipt['netbsd_pin'], '03d918f6d0e81fa05b8f1160eca0628ad39988a6')
        self.assertEqual(receipt['operation_count'], 27)
        self.assertEqual(len(receipt['inputs']), 7)
        self.assertEqual(len(receipt['outputs']), 2)
        self.assertEqual(receipt['outputs']['linux_kthread.c']['sha256'],
                         '31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274')
        self.assertEqual(receipt['definition_ownership']['task_system_fini_checked'],
                         dict(file='linux_kthread.c', call_line=86, assertion_line=87))
        for key in ('native_preprocessing', 'native_compilation', 'runtime'):
            self.assertEqual(receipt[key], 'NOT_RUN')
        for key in ('linked', 'installed', 'booted'):
            self.assertIs(receipt[key], False)
        self.assertFalse(receipt['historical_recipe']['executed'])

    def test_each_of_seventeen_passed_bindings_is_required(self):
        for name in self.contract['repository_inputs']:
            changed = dict(self.bindings); changed.pop(str(self.repo / name))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Worker generation:'):
                admission.verify_worker_generation(self.repo, self.contract, changed,
                                                   admission.WORKER_CONTRACT_SHA256)

    def test_full_passed_binding_identity_cannot_be_replaced(self):
        for name in self.contract['repository_inputs']:
            changed = copy.deepcopy(self.bindings)
            changed[str(self.repo / name)]['sha256'] = '0' * 64
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Worker generation:'):
                admission.verify_worker_generation(self.repo, self.contract, changed,
                                                   admission.WORKER_CONTRACT_SHA256)

    def test_worker_cannot_be_spoofed_into_the_unchanged_wait_profile(self):
        with self.assertRaisesRegex(ValueError, 'exact reviewed Wait contract'):
            admission.wait_input_policy(self.contract, admission.WORKER_CONTRACT_SHA256)
        with self.assertRaisesRegex(ValueError, 'Wait provider identity/shape'):
            admission.wait_input_policy(self.contract, admission.WAIT_CONTRACT_SHA256)

    def test_duplicate_provenance_key_is_checked_after_rebinding_outer_byte_identity(self):
        document = self.json()
        raw = b'{"schema":1,' + json.dumps(document).encode()[1:]
        with self.changed_provenance(raw=raw):
            with self.assertRaisesRegex(ValueError, 'Worker generation:.*duplicate JSON key'):
                self.generation()

    def test_rebound_source_scope_pins_and_boolean_types_are_still_validated(self):
        mutations = (
            lambda d: d.update(schema=True),
            lambda d: d.update(state='COMPILED'),
            lambda d: d.update(netbsd_pin='0' * 40),
            lambda d: d.update(repository_input_commit='0' * 40),
            lambda d: d.update(native_compilation='PASS'),
            lambda d: d.update(runtime='PASS'),
            lambda d: d.update(linked=0),
            lambda d: d.update(installed=1),
            lambda d: d.update(whole_patch_applied=0),
            lambda d: d.update(extra_unreviewed='claim'))
        for index, mutate in enumerate(mutations):
            document = self.json(); mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Worker generation:'):
                    self.generation()

    def test_rebound_exact_operation_audit_count_order_and_crosslinks_are_enforced(self):
        mutations = (
            lambda d: d.update(operations=[{}] * 27),
            lambda d: d['operations'].pop(),
            lambda d: d['operations'].reverse(),
            lambda d: d['operations'][0].update(old_start=1),
            lambda d: d['operations'][0].update(hunk_sha256='0' * 64))
        for index, mutate in enumerate(mutations):
            document = self.json(); mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Worker generation:'):
                    self.generation()

    def test_rebound_declared_origin_output_and_selected_section_identities_are_crosslinked(self):
        mutations = (
            lambda d: d['repository_inputs'][fixture.ORIGINS[0]].update(blob='0' * 40),
            lambda d: d['repository_inputs'][fixture.ORIGINS[-1]].update(sha256='0' * 64),
            lambda d: d['files']['linux_kthread.c'].update(size=1),
            lambda d: d['files']['include/linux/kthread.h'].update(sha256='0' * 64),
            lambda d: d['selected_sections'][next(iter(d['selected_sections']))].update(hunks=1))
        for index, mutate in enumerate(mutations):
            document = self.json(); mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Worker generation:'):
                    self.generation()

    def test_rebound_producer_ownership_history_and_open_gates_cannot_change(self):
        mutations = (
            lambda d: d.update(recovery_tool_sha256='0' * 64),
            lambda d: d['definition_ownership']['linux_kthread_wake_locked'].update(line=1),
            lambda d: d['definition_ownership']['task_system_fini_checked'].update(assertion_line=1),
            lambda d: d['historical_recipe'].update(executed=True),
            lambda d: d['historical_integration'].update(interpretation='native link verified'),
            lambda d: d.update(open_gates=[]))
        for index, mutate in enumerate(mutations):
            document = self.json(); mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Worker generation:'):
                    self.generation()

    def test_each_rebound_origin_and_witness_still_requires_its_fixed_authority(self):
        for name in fixture.ORIGINS:
            raw = (self.repo / name).read_bytes()
            with self.subTest(name=name), self.changed_payload(name, raw + b' changed origin'):
                with self.assertRaisesRegex(ValueError, 'Worker generation:'):
                    self.generation()

    def test_rebound_recovered_outputs_and_producer_bytes_cannot_substitute_other_content(self):
        for name in (fixture.UNIT, fixture.HEADER, fixture.PRODUCER):
            raw = (self.repo / name).read_bytes()
            with self.subTest(name=name), self.changed_payload(name, raw + b' changed output'):
                with self.assertRaisesRegex(ValueError, 'Worker generation:'):
                    self.generation()

    def test_proof_file_and_parent_aliases_are_rejected_even_with_identical_payload(self):
        for name in (fixture.PROVENANCE, fixture.ORIGINS[-1]):
            path = self.repo / name; raw = path.read_bytes()
            external = fixture.save(self.base / ('external-' + str(len(name))), raw)
            path.unlink(); path.symlink_to(external)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Worker generation:'):
                self.generation()
            path.unlink(); path.write_bytes(raw)
        parent = (self.repo / fixture.PROVENANCE).parent
        actual = parent.with_name('actual-worker')
        parent.rename(actual); parent.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Worker generation:'):
            self.generation()

    def test_same_read_provenance_bytes_are_parsed_and_a_second_read_cannot_be_unbound(self):
        payload = (self.repo / fixture.PROVENANCE).read_bytes()
        real_loads, real_read = admission.json.loads, admission.regular_bytes
        parsed, reads = [], []
        def checked_loads(value, *args, **kwargs):
            if isinstance(value, bytes) and value == payload:
                parsed.append(True)
                self.assertIs(kwargs.get('object_pairs_hook'), admission.unique_object)
            return real_loads(value, *args, **kwargs)
        def changing_read(path):
            value = real_read(path)
            if Path(path) == self.repo / fixture.PROVENANCE:
                reads.append(True)
                if len(reads) > 1:
                    return value + b' '
            return value
        with mock.patch.object(admission.json, 'loads', side_effect=checked_loads), \
             mock.patch.object(admission, 'regular_bytes', side_effect=changing_read):
            try:
                receipt = self.generation()
            except ValueError as error:
                self.assertGreaterEqual(len(reads), 2)
                self.assertRegex(str(error), 'Worker generation:')
            else:
                self.assertEqual(len(reads), 1)
                self.assertEqual(receipt['state'], 'VERIFIED_WORKER_SOURCE_GENERATION_ONLY')
                self.assertTrue(parsed)

    def test_final_reverification_rejects_proof_drift_since_the_first_receipt(self):
        self.assertEqual(self.generation()['state'], 'VERIFIED_WORKER_SOURCE_GENERATION_ONLY')
        path = self.repo / fixture.PROVENANCE
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'Worker generation:'):
            self.generation()

    def test_returned_receipt_does_not_alias_any_mutable_canonical_authority(self):
        names = ('_WORKER_SOURCE_IDENTITIES', '_WORKER_OUTPUT_IDENTITIES', '_WORKER_SECTIONS',
                 '_WORKER_DEFINITION_OWNERSHIP', '_WORKER_OPEN_GATES')
        originals = {name: copy.deepcopy(getattr(admission, name)) for name in names}
        with contextlib.ExitStack() as stack:
            for name in names:
                stack.enter_context(mock.patch.object(admission, name, copy.deepcopy(originals[name])))
            receipt = self.generation()
            receipt['inputs'][next(iter(receipt['inputs']))]['sha256'] = '0' * 64
            receipt['outputs']['linux_kthread.c']['size'] = 0
            receipt['selected_sections'][next(iter(receipt['selected_sections']))]['hunks'] = 0
            receipt['definition_ownership']['linux_kthread_wake_locked']['line'] = 0
            receipt['open_gates'].clear()
            for name in names:
                self.assertEqual(getattr(admission, name), originals[name])
            self.assertEqual(self.generation()['state'], 'VERIFIED_WORKER_SOURCE_GENERATION_ONLY')

    def test_generation_verifier_never_runs_git_a_producer_or_any_native_command(self):
        before = {str(p.relative_to(self.repo)): p.read_bytes()
                  for p in self.repo.rglob('*') if p.is_file()}
        with mock.patch.object(admission.subprocess, 'check_output',
                               side_effect=AssertionError('no Git/generator in pure proof check')), \
             mock.patch.object(admission.subprocess, 'run',
                               side_effect=AssertionError('no native tool or historical recipe')):
            self.assertEqual(self.generation()['state'], 'VERIFIED_WORKER_SOURCE_GENERATION_ONLY')
        after = {str(p.relative_to(self.repo)): p.read_bytes()
                 for p in self.repo.rglob('*') if p.is_file()}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
