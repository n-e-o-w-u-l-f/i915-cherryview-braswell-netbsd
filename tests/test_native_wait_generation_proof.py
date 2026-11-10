"""F44 same-read Wait generation-proof checks; private copies only, no generator or native tool."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_provider_inputs as admission
import test_native_wait_provider_inputs as fixture
from test_native_provider_inputs import save, sha

PROVENANCE = fixture.PROVENANCE
INPUT_PROVENANCE = fixture.INPUT_PROVENANCE
LEDGER = fixture.LEDGER


def encoded(document):
    return (json.dumps(document, indent=2) + '\n').encode()


def duplicate_json(document):
    first = next(iter(document))
    prefix = json.dumps(first) + ':' + json.dumps(document[first]) + ','
    return ('{' + prefix + json.dumps(document, separators=(',', ':'))[1:]).encode()


class WaitGenerationProofTests(unittest.TestCase, fixture.WaitFixture):
    setUp = fixture.WaitFixture.setUp

    def test_full_positive_proof_is_source_only_and_records_all_bound_identities(self):
        receipt = self.generation()
        self.assertEqual(receipt['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')
        self.assertEqual(receipt['provenance'], PROVENANCE)
        self.assertEqual(receipt['provenance_sha256'], self.contract['generation_provenance_sha256'])
        self.assertEqual(receipt['linux_pin'], 'fd179f8a05be3ccae366b9b96e176b51fbe54aab')
        self.assertEqual(receipt['netbsd_pin'], admission.PIN)
        self.assertEqual(receipt['operation_count'], 49)
        self.assertEqual(receipt['outputs'], admission._WAIT_OUTPUT_IDENTITIES)
        self.assertEqual(receipt['inputs'], admission._WAIT_SOURCE_IDENTITIES)
        self.assertEqual(receipt['witnesses'], admission._WAIT_WITNESSES)
        self.assertEqual(receipt['recovery_tool_sha256'], admission._WAIT_RECOVERY_TOOL_SHA256)
        self.assertEqual(receipt['native_preprocessing'], 'NOT_RUN')
        self.assertEqual(receipt['native_compilation'], 'NOT_RUN')
        self.assertIs(receipt['linked'], False)
        self.assertEqual(receipt['runtime'], 'NOT_RUN')

    def test_exactly_fifteen_previously_git_bound_paths_are_required(self):
        for name in self.contract['repository_inputs']:
            changed = copy.deepcopy(self.bindings)
            changed.pop(str(self.repo / name))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Wait generation.*fifteen'):
                admission.verify_wait_generation(self.repo, self.contract, changed, fixture.WAIT_SHA)
        changed = copy.deepcopy(self.bindings)
        changed[str(self.repo / 'foreign')] = dict(kind='repository')
        with self.assertRaisesRegex(ValueError, 'Wait generation.*fifteen'):
            admission.verify_wait_generation(self.repo, self.contract, changed, fixture.WAIT_SHA)

    def test_each_proof_row_must_match_the_contract_before_its_payload_is_read(self):
        for name in fixture.PROOFS:
            changed = copy.deepcopy(self.bindings)
            changed[str(self.repo / name)]['blob'] = '0' * 40
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, 'Wait generation.*Git-bound generation row differs'):
                admission.verify_wait_generation(self.repo, self.contract, changed, fixture.WAIT_SHA)

    def test_same_read_hash_and_blob_are_checked_before_json_parse(self):
        name = PROVENANCE
        for field, bad in (('sha256', '0' * 64), ('blob', '0' * 40)):
            before_row = copy.deepcopy(self.contract['repository_inputs'][name])
            before_binding = copy.deepcopy(self.bindings[str(self.repo / name)])
            self.contract['repository_inputs'][name][field] = bad
            self.bindings[str(self.repo / name)][field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, 'Wait generation.*same-read generation SHA256/blob differs'):
                self.generation()
            self.contract['repository_inputs'][name] = before_row
            self.bindings[str(self.repo / name)] = before_binding

    def test_rebound_whitespace_cannot_leave_a_stale_top_level_provenance_pin(self):
        raw = (self.repo / PROVENANCE).read_bytes()
        original = json.loads(raw)
        with self.changed_payload(PROVENANCE, raw + b'\n'):
            self.assertEqual(self.read_json(PROVENANCE), original)
            self.assertNotEqual(self.contract['repository_inputs'][PROVENANCE]['sha256'],
                                self.contract['generation_provenance_sha256'])
            with self.assertRaisesRegex(ValueError, 'Wait generation.*generation provenance pin differs'):
                self.generation()

    def test_rebound_scope_pin_and_boolean_mutations_reach_the_scope_guard(self):
        original = self.read_json(PROVENANCE)
        mutations = (
            lambda d: d.update(schema=True),
            lambda d: d.update(state='COMPILED'),
            lambda d: d.update(linux_pin='0' * 40),
            lambda d: d.update(netbsd_pin='0' * 40),
            lambda d: d.update(source_mode='clean checkout'),
            lambda d: d.update(native_preprocessing='PASS'),
            lambda d: d.update(native_compilation='PASS'),
            lambda d: d.update(runtime='PASS'),
            lambda d: d.update(linked=True),
            lambda d: d.update(linked=0),
            lambda d: d.update(installed=True),
            lambda d: d.update(installed=0),
            lambda d: d.update(open_gates=[]),
            lambda d: d.update(extra_unbound_state=True),
            lambda d: d.pop('state'))
        for index, mutate in enumerate(mutations):
            document = copy.deepcopy(original)
            mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Wait generation.*generation scope/pins/flags differ'):
                    self.generation()

    def test_rebound_declared_output_raw_witness_and_tool_identity_mutations_are_rejected(self):
        original = self.read_json(PROVENANCE)
        mutations = (
            lambda d: d['files']['linux_wait.c'].update(size=1),
            lambda d: d['files']['linux_wait.c'].update(sha256='0' * 64),
            lambda d: d['inputs']['include/linux/wait.h'].update(git_blob='0' * 40),
            lambda d: d['inputs']['include/linux/wait.h'].update(source_url='https://example.invalid'),
            lambda d: d['witnesses']['recipe'].update(path='../unreviewed.py'),
            lambda d: d.update(recovery_tool_sha256='0' * 64))
        for index, mutate in enumerate(mutations):
            document = copy.deepcopy(original)
            mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Wait generation.*generation declared identities differ'):
                    self.generation()

    def test_rebound_operation_count_names_order_and_fingerprint_mutations_are_rejected(self):
        original = self.read_json(PROVENANCE)
        mutations = (
            lambda d: d['operations'].pop(),
            lambda d: d['operations'].__setitem__(1, copy.deepcopy(d['operations'][0])),
            lambda d: d['operations'].reverse(),
            lambda d: d['operations'][0].update(count=99),
            lambda d: d['operations'][0].update(kind='invented'),
            lambda d: d.update(operations='49 operations'))
        for index, mutate in enumerate(mutations):
            document = copy.deepcopy(original)
            mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Wait generation.*generation operation audit differs'):
                    self.generation()

    def test_duplicate_output_provenance_keys_fail_after_rebinding_row_and_pin(self):
        raw = duplicate_json(self.read_json(PROVENANCE))
        with self.changed_provenance(raw=raw):
            with self.assertRaisesRegex(ValueError, 'Wait generation.*duplicate JSON key'):
                self.generation()

    def test_duplicate_raw_input_provenance_keys_fail_after_binding_updated_bytes(self):
        raw = duplicate_json(self.read_json(INPUT_PROVENANCE))
        with self.changed_payload(INPUT_PROVENANCE, raw):
            with self.assertRaisesRegex(ValueError, 'Wait generation.*duplicate JSON key'):
                self.generation()

    def test_duplicate_ledger_keys_fail_after_rebinding_ledger_and_witness_chain(self):
        raw = duplicate_json(self.read_json(LEDGER))
        with self.changed_ledger(raw):
            with self.assertRaisesRegex(ValueError, 'Wait generation.*duplicate JSON key'):
                self.generation()

    def test_raw_input_provenance_schema_pin_and_file_crosslinks_are_checked(self):
        original = self.read_json(INPUT_PROVENANCE)
        mutations = (
            lambda d: d.update(schema=True),
            lambda d: d.update(linux_pin='0' * 40),
            lambda d: d.update(state='CLEAN_GIT_TREE'),
            lambda d: d.update(acquisition='unbound source download'),
            lambda d: d['files']['kernel/sched/wait.c'].update(sha256='0' * 64))
        for index, mutate in enumerate(mutations):
            document = copy.deepcopy(original)
            mutate(document)
            with self.subTest(index=index), self.changed_payload(INPUT_PROVENANCE, encoded(document)):
                with self.assertRaisesRegex(ValueError, 'Wait generation.*input provenance cross-link differs'):
                    self.generation()

    def test_each_rebound_upstream_raw_payload_still_requires_the_pinned_authority(self):
        for name in ('compat/native-runtime/wait-inputs-f43/include/linux/wait.h',
                     'compat/native-runtime/wait-inputs-f43/kernel/sched/wait.c'):
            raw = (self.repo / name).read_bytes()
            with self.subTest(name=name), self.changed_payload(name, raw + b' upstream drift'):
                with self.assertRaisesRegex(ValueError, 'Wait generation.*pinned upstream raw authority differs'):
                    self.generation()

    def test_each_rebound_recovered_output_still_requires_its_historical_identity(self):
        for name in fixture.COMPILED[:2]:
            raw = (self.repo / name).read_bytes()
            with self.subTest(name=name), self.changed_payload(name, raw + b' output drift'):
                with self.assertRaisesRegex(ValueError, 'Wait generation.*historical recovered output differs'):
                    self.generation()

    def test_rebound_recipe_bytes_cannot_substitute_a_different_witness(self):
        name = 'compat/native-runtime/task/generate_wait.py'
        raw = (self.repo / name).read_bytes()
        with self.changed_payload(name, raw + b'\n# changed witness\n'):
            with self.assertRaisesRegex(ValueError, 'Wait generation.*recipe/ledger witness differs'):
                self.generation()

    def test_ledger_output_crosslink_is_reached_after_rebinding_all_witness_pins(self):
        document = self.read_json(LEDGER)
        document['linux_wait.c'] = '0' * 64
        with self.changed_ledger(encoded(document)):
            with self.assertRaisesRegex(ValueError, 'Wait generation.*historical ledger cross-link differs'):
                self.generation()

    def test_rebound_producer_bytes_are_crosslinked_to_the_bound_output_document(self):
        name = 'tools/recover_native_wait.py'
        raw = (self.repo / name).read_bytes()
        with self.changed_payload(name, raw + b'\n# producer drift\n'):
            with self.assertRaisesRegex(ValueError, 'Wait generation.*producer cross-link differs'):
                self.generation()

    def test_json_proof_aliases_and_parent_aliases_are_rejected(self):
        for name in (PROVENANCE, INPUT_PROVENANCE, LEDGER):
            path = self.repo / name
            raw = path.read_bytes()
            target = save(self.base / ('external-' + str(len(name)) + '.json'), raw)
            path.unlink()
            path.symlink_to(target)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Wait generation.*aliased'):
                self.generation()
            path.unlink()
            path.write_bytes(raw)
        parent = (self.repo / PROVENANCE).parent
        moved = parent.with_name('actual-recovered')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Wait generation.*aliased'):
            self.generation()

    def test_only_same_bound_byte_payloads_are_parsed_as_the_three_json_documents(self):
        json_names = (PROVENANCE, INPUT_PROVENANCE, LEDGER)
        expected = {(self.repo / name).read_bytes(): name for name in json_names}
        parsed = []
        real_loads = admission.json.loads
        def checked_loads(raw, *args, **kwargs):
            self.assertIsInstance(raw, bytes)
            self.assertIn(raw, expected)
            parsed.append(expected[raw])
            return real_loads(raw, *args, **kwargs)
        with mock.patch.object(admission.json, 'loads', side_effect=checked_loads):
            self.assertEqual(self.generation()['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')
        self.assertCountEqual(parsed, json_names)

    def test_a_second_ledger_read_must_be_hash_bound_or_the_first_payload_reused(self):
        path = self.repo / LEDGER
        forged = self.read_json(LEDGER)
        forged['unverified_second_read'] = True
        forged_raw = encoded(forged)
        real_read = admission.regular_bytes
        reads = []
        def changing_read(current):
            raw = real_read(current)
            if Path(current) == path:
                reads.append(True)
                if len(reads) > 1:
                    return forged_raw
            return raw
        with mock.patch.object(admission, 'regular_bytes', side_effect=changing_read):
            try:
                result = self.generation()
            except ValueError as error:
                self.assertEqual(len(reads), 2)
                self.assertRegex(str(error), 'Wait generation.*same-read generation SHA256/blob differs')
            else:
                # Reusing a single already-bound ledger payload is also safe.
                self.assertEqual(len(reads), 1)
                self.assertEqual(result['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')

    def test_final_reverification_rejects_proof_payload_drift_since_first_receipt(self):
        self.assertEqual(self.generation()['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')
        path = self.repo / INPUT_PROVENANCE
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'Wait generation.*same-read generation SHA256/blob differs'):
            self.generation()

    def test_returned_receipt_metadata_does_not_alias_canonical_authority(self):
        original_inputs = copy.deepcopy(admission._WAIT_SOURCE_IDENTITIES)
        original_outputs = copy.deepcopy(admission._WAIT_OUTPUT_IDENTITIES)
        original_witnesses = copy.deepcopy(admission._WAIT_WITNESSES)
        with mock.patch.object(admission, '_WAIT_SOURCE_IDENTITIES', copy.deepcopy(original_inputs)), \
             mock.patch.object(admission, '_WAIT_OUTPUT_IDENTITIES', copy.deepcopy(original_outputs)), \
             mock.patch.object(admission, '_WAIT_WITNESSES', copy.deepcopy(original_witnesses)):
            receipt = self.generation()
            receipt['inputs']['include/linux/wait.h']['size'] = 0
            receipt['outputs']['linux_wait.c']['sha256'] = '0' * 64
            receipt['witnesses']['recipe']['path'] = '../changed'
            self.assertEqual(admission._WAIT_SOURCE_IDENTITIES, original_inputs)
            self.assertEqual(admission._WAIT_OUTPUT_IDENTITIES, original_outputs)
            self.assertEqual(admission._WAIT_WITNESSES, original_witnesses)
            second = self.generation()
            self.assertEqual(second['inputs'], original_inputs)
            self.assertEqual(second['outputs'], original_outputs)
            self.assertEqual(second['witnesses'], original_witnesses)

    def test_generation_check_has_no_subprocess_or_recipe_side_effects(self):
        before = {str(path.relative_to(self.repo)): path.read_bytes()
                  for path in self.repo.rglob('*') if path.is_file()}
        with mock.patch.object(admission.subprocess, 'check_output',
                               side_effect=AssertionError('generation checker must not execute Git/recipes')), \
             mock.patch.object(admission.subprocess, 'run',
                               side_effect=AssertionError('generation checker must not execute native tools')):
            self.assertEqual(self.generation()['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')
        after = {str(path.relative_to(self.repo)): path.read_bytes()
                 for path in self.repo.rglob('*') if path.is_file()}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
