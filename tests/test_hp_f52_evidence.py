"""F52 checked source/report acceptance; no native commands performed by this test."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/HP_F52_NATIVE_SEVEN_PROVIDER_LINK_20261112.json"
HEX64 = re.compile(r"^[a-f0-9]{64}$")

class F52EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_one_exact_native_partial_link(self):
        e = self.e
        self.assertEqual(e["state"], "PASS_SEVEN_PROVIDER_PARTIAL_LINK")
        self.assertEqual(e["native_link"]["commands"], 1)
        self.assertEqual(e["native_link"]["exit_code"], 0)
        self.assertEqual(e["native_link"]["object_bytes"], 838952)
        self.assertRegex(e["native_link"]["object_sha256"], HEX64)
        self.assertEqual(e["native_link"]["elf"], "ELF64 AMD64 ET_REL")

    def test_exact_seven_inputs_and_worker_ownership(self):
        e = self.e
        self.assertEqual([v["role"] for v in e["native_link"]["inputs"]],
            ["FD", "ANON", "FILE", "TASK", "WAIT", "POLL", "WORKER"])
        self.assertTrue(all(HEX64.fullmatch(v["sha256"]) for v in e["native_link"]["inputs"]))
        self.assertEqual(e["worker"]["public_text_exports"], 19)
        self.assertEqual(e["worker"]["linux_unresolved_resolved_from_task"], 8)
        self.assertEqual(e["worker"]["native_unresolved_present_in_f26"], 24)

    def test_comdat_and_unresolved_scope(self):
        e = self.e
        self.assertEqual(e["link_symbols"]["thunks_after_coalescence"],
            ["__x86_indirect_thunk_r15", "__x86_indirect_thunk_rax"])
        self.assertEqual(e["link_symbols"]["unresolved_total"], 80)
        self.assertEqual(e["link_symbols"]["unresolved_linux"], 8)
        self.assertEqual(e["link_symbols"]["unresolved_other"], 72)

    def test_every_residual_symbol_has_source_or_binary_owner(self):
        e = self.e
        owners = e["remaining_owner_classes"]
        self.assertEqual(owners["F26_linked_native_kernel"], 71)
        self.assertEqual(owners["F32_separate_native_object"], 1)
        self.assertEqual(owners["source_definition_uncompiled"], 8)
        self.assertEqual(sum(owners.values()), e["link_symbols"]["unresolved_total"])
        self.assertEqual(sorted(e["remaining_uncompiled_source_units"]), sorted([
            "compat/native-file/linux_inode.c",
            "compat/native-file/linux_native_fileops.c",
            "compat/native-file/linux_page.c",
            "compat/native-file/linux_shmem_commit.c"]))

    def test_no_full_kernel_or_runtime_acceptance(self):
        e = self.e
        self.assertEqual(e["full_kernel"], "NOT_RUN")
        self.assertFalse(e["installed"])
        self.assertFalse(e["booted"])
        self.assertEqual(e["runtime"], "NOT_RUN")
        self.assertEqual(e["parent_acceptance"], "PARTIAL")
        self.assertRegex(e["independent_review_sha256"], HEX64)
        self.assertRegex(e["owner_review_sha256"], HEX64)

if __name__ == "__main__":
    unittest.main()
