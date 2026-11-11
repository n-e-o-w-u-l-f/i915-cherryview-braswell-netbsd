"""F46 referenced Wait proof tests; fixture pins may rebind, production pins never change."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_native_poll_provider_inputs as fixture
from test_native_wait_generation_proof import duplicate_json, encoded

admission = fixture.admission
PROVENANCE = fixture.wait_fixture.PROVENANCE
INPUT_PROVENANCE = fixture.wait_fixture.INPUT_PROVENANCE
LEDGER = fixture.wait_fixture.LEDGER


class PollGenerationProofTests(unittest.TestCase, fixture.PollFixture):
    setUp = fixture.PollFixture.setUp

    def test_positive_reference_reuses_original_wait_roles_git_and_generation_checker(self):
        real_checker = admission.verify_wait_generation
        with fixture.referenced_wait(self) as wait_contract:
            with mock.patch.object(admission, 'verify_wait_generation', wraps=real_checker) as checked:
                result = admission.verify_poll_generation(
                    self.repo, self.contract, self.bindings, admission.POLL_CONTRACT_SHA256)
            checked.assert_called_once()
            arguments = checked.call_args.args
            self.assertEqual(arguments[1], wait_contract)
            self.assertEqual(len(arguments[2]), 15)
            self.assertEqual(arguments[1]['repository_inputs'][fixture.WAIT_BODY]['role'],
                             'translation_unit')
            self.assertEqual(self.contract['repository_inputs'][fixture.WAIT_BODY]['role'],
                             'generation_proof_owner')
            self.assertEqual(result['wait_repository_commit'], wait_contract['repository_commit'])
            self.assertEqual(result['wait_contract_sha256'], self.contract['wait_contract_sha256'])
        self.assertEqual(result['state'], 'VERIFIED_REFERENCED_WAIT_GENERATION_ONLY')
        self.assertEqual(result['wait_contract'], admission.WAIT_CONTRACT_PATH)
        self.assertEqual(len(result['shared_repository_inputs']), 15)
        self.assertEqual(result['wait_generation']['operation_count'], 49)
        self.assertEqual(result['wait_generation']['state'], 'VERIFIED_SOURCE_GENERATION_ONLY')
        self.assertEqual(result['native_preprocessing'], 'NOT_RUN')
        self.assertEqual(result['native_compilation'], 'NOT_RUN')
        self.assertIs(result['linked'], False)
        self.assertEqual(result['runtime'], 'NOT_RUN')

    def test_each_of_twenty_six_bound_rows_is_required_before_reference_lookup(self):
        for name in self.contract['repository_inputs']:
            changed = dict(self.bindings)
            changed.pop(str(self.repo / name))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,
                    'Poll generation: exactly twenty-six Git-bound Poll rows required'):
                admission.verify_poll_generation(self.repo, self.contract, changed,
                                                  admission.POLL_CONTRACT_SHA256)

    def test_passed_poll_bindings_must_match_the_full_contract_identity(self):
        for field, value in (('sha256', '0' * 64), ('blob', '0' * 40),
                             ('role', 'fixture'), ('relative', 'foreign')):
            changed = copy.deepcopy(self.bindings)
            changed[str(self.repo / fixture.API_OWNER)][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,
                    'Poll generation: Git-bound Poll row differs'):
                admission.verify_poll_generation(self.repo, self.contract, changed,
                                                  admission.POLL_CONTRACT_SHA256)

    def test_original_wait_profile_still_rejects_poll_generation_roles_and_digest(self):
        with self.assertRaisesRegex(ValueError, 'generation proofs require the exact reviewed Wait contract'):
            admission.wait_input_policy(self.contract, admission.POLL_CONTRACT_SHA256)
        with self.assertRaisesRegex(ValueError, 'Wait provider identity/shape'):
            admission.wait_input_policy(self.contract, admission.WAIT_CONTRACT_SHA256)

    def test_shared_identity_crosslink_is_independent_of_a_bound_wait_claim(self):
        name = fixture.WAIT_HEADER
        for field, value in (('sha256', '0' * 64), ('blob', '0' * 40)):
            def mutate(document):
                document['repository_inputs'][name][field] = value
            with self.subTest(field=field), fixture.referenced_wait(self, mutate) as document:
                forged = {str(self.repo / relative): dict(kind='repository', relative=relative, **row)
                          for relative, row in document['repository_inputs'].items()}
                # Isolate the cross-link after simulating a separately admitted reference.
                # The positive test above exercises the actual private Git lookup.
                with mock.patch.object(admission, 'repository_inputs', return_value=forged):
                    with self.assertRaisesRegex(ValueError,
                            'Poll generation: referenced Wait input identity differs'):
                        admission.verify_poll_generation(self.repo, self.contract, self.bindings,
                                                          admission.POLL_CONTRACT_SHA256)

    def test_reference_manifest_bytes_are_checked_against_the_fixed_path_digest(self):
        with fixture.referenced_wait(self):
            path = self.repo / admission.WAIT_CONTRACT_PATH
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'Poll generation: provider contract bytes differ'):
                admission.verify_poll_generation(self.repo, self.contract, self.bindings,
                                                  admission.POLL_CONTRACT_SHA256)

    def test_reference_manifest_cannot_be_a_symlink_even_with_identical_bytes(self):
        with fixture.referenced_wait(self):
            path = self.repo / admission.WAIT_CONTRACT_PATH
            raw = path.read_bytes()
            target = fixture.save(self.base / 'external-wait.json', raw)
            path.unlink()
            path.symlink_to(target)
            try:
                with self.assertRaisesRegex(ValueError, 'Poll generation: .*source-owned'):
                    admission.verify_poll_generation(self.repo, self.contract, self.bindings,
                                                      admission.POLL_CONTRACT_SHA256)
            finally:
                path.unlink()
                path.write_bytes(raw)

    def test_duplicate_output_provenance_keys_reach_wait_parser_after_fixture_rebinding(self):
        raw = duplicate_json(self.read_json(PROVENANCE))
        with self.changed_provenance(raw=raw):
            with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: duplicate JSON key'):
                self.generation()

    def test_duplicate_raw_provenance_keys_reach_wait_parser_after_fixture_rebinding(self):
        raw = duplicate_json(self.read_json(INPUT_PROVENANCE))
        with self.changed_payload(INPUT_PROVENANCE, raw):
            with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: duplicate JSON key'):
                self.generation()

    def test_duplicate_ledger_keys_reach_wait_parser_after_witness_chain_rebinding(self):
        raw = duplicate_json(self.read_json(LEDGER))
        with self.changed_ledger(raw):
            with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: duplicate JSON key'):
                self.generation()

    def test_rebound_generation_scope_flags_and_operation_audit_remain_enforced(self):
        original = self.read_json(PROVENANCE)
        changes = (lambda d: d.update(native_compilation='PASS'),
                   lambda d: d.update(linked=True),
                   lambda d: d.update(linux_pin='0' * 40),
                   lambda d: d['operations'].pop())
        for index, mutate in enumerate(changes):
            document = copy.deepcopy(original)
            mutate(document)
            with self.subTest(index=index), self.changed_provenance(document):
                with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: generation'):
                    self.generation()

    def test_rebound_input_provenance_cannot_change_pinned_source_crosslinks(self):
        document = self.read_json(INPUT_PROVENANCE)
        document['files']['kernel/sched/wait.c']['sha256'] = '0' * 64
        with self.changed_payload(INPUT_PROVENANCE, encoded(document)):
            with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: input provenance cross-link'):
                self.generation()

    def test_rebound_ledger_cannot_change_historical_output_crosslinks(self):
        document = self.read_json(LEDGER)
        document['linux_wait.c'] = '0' * 64
        with self.changed_ledger(encoded(document)):
            with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: historical ledger cross-link'):
                self.generation()

    def test_rebound_upstream_and_recovered_bytes_still_require_original_authority(self):
        for name, message in (
                ('compat/native-runtime/wait-inputs-f43/kernel/sched/wait.c', 'pinned upstream raw authority'),
                (fixture.WAIT_BODY, 'historical recovered output'),
                (fixture.WAIT_HEADER, 'historical recovered output')):
            raw = (self.repo / name).read_bytes()
            with self.subTest(name=name), self.changed_payload(name, raw + b' changed'):
                with self.assertRaisesRegex(ValueError, 'Poll generation: Wait generation: ' + message):
                    self.generation()

    def test_final_reference_proof_drift_cannot_reuse_the_earlier_generation_receipt(self):
        self.assertEqual(self.generation()['state'], 'VERIFIED_REFERENCED_WAIT_GENERATION_ONLY')
        path = self.repo / INPUT_PROVENANCE
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'Poll generation: provider working bytes differ'):
            self.generation()

    def test_receipt_shared_rows_and_wait_metadata_do_not_alias_authority(self):
        result = self.generation()
        result['shared_repository_inputs'][fixture.WAIT_HEADER]['sha256'] = '0' * 64
        result['wait_generation']['inputs']['include/linux/wait.h']['size'] = 0
        again = self.generation()
        self.assertEqual(again['shared_repository_inputs'][fixture.WAIT_HEADER]['sha256'],
                         self.contract['repository_inputs'][fixture.WAIT_HEADER]['sha256'])
        self.assertEqual(again['wait_generation']['inputs'], admission._WAIT_SOURCE_IDENTITIES)

    def test_reference_check_executes_only_readonly_git_and_never_a_generator_or_compiler(self):
        with fixture.referenced_wait(self):
            real_run = admission.subprocess.run
            commands = []
            def checked_run(command, *args, **kwargs):
                commands.append(command)
                self.assertEqual(command[0], 'git')
                self.assertIn('ls-tree', command)
                return real_run(command, *args, **kwargs)
            with mock.patch.object(admission.subprocess, 'run', side_effect=checked_run):
                result = admission.verify_poll_generation(
                    self.repo, self.contract, self.bindings, admission.POLL_CONTRACT_SHA256)
            self.assertEqual(len(commands), 15)
            self.assertEqual(result['wait_generation']['operation_count'], 49)


if __name__ == '__main__':
    unittest.main()
