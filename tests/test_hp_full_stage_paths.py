#!/usr/bin/env python3
"""Pure private-path, configured-owner and exact provenance controls.

Uses temporary synthetic source bytes and mocked pinned Git readers. No native
host, compiler, make, Git process or historical stage is accessed.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import namespace_linux_compiler_math as namespace
import prepare_hp_full_graph as prepare


class StagePaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.inputs = [self.work / name for name in ("linux-reference", "netbsd-reference", "materialized", "tools")]
        for path in self.inputs:
            path.mkdir()

    def test_new_sibling_outputs_are_admitted(self):
        outputs = prepare.stage_outputs(self.work, self.inputs)
        self.assertEqual(outputs["netbsd-full-linux"], self.work / "netbsd-full-linux")
        self.assertFalse(any(path.exists() for path in outputs.values()))

    def test_existing_output_or_interrupted_status_is_preserved(self):
        for name in ("netbsd-full-linux", "full-linux-graph-status.tmp", "full-linux-api-inputs.json"):
            with self.subTest(name=name):
                path = self.work / name
                path.write_text("preserved")
                with self.assertRaisesRegex(RuntimeError, "preserve existing"):
                    prepare.stage_outputs(self.work, self.inputs)
                self.assertEqual(path.read_text(), "preserved")
                path.unlink()

    def test_output_may_not_be_inside_an_input(self):
        with self.assertRaisesRegex(RuntimeError, "overlaps"):
            prepare.stage_outputs(self.work, [self.work])

    def test_dangling_output_symlink_is_preserved(self):
        path = self.work / "full-linux-obj"
        try:
            path.symlink_to(self.work / "missing")
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(RuntimeError, "preserve existing"):
            prepare.stage_outputs(self.work, self.inputs)
        self.assertTrue(path.is_symlink())

    def test_reference_copy_owns_sys_common_and_excludes_git_metadata(self):
        reference = self.inputs[1]
        (reference / ".git").mkdir()
        (reference / ".git/config").write_text("original Git config")
        (reference / ".gitignore").write_text("original ignore")
        for name in ("sys", "common"):
            (reference / name).mkdir()
            (reference / name / "source.c").write_text(name)
        (reference / "Makefile").write_text("source makefile")
        tree = self.work / "private"
        tree.mkdir()
        try:
            prepare.copy_reference(reference, tree)
        except OSError as error:
            if not (tree / "Makefile").exists():
                self.skipTest(str(error))
            raise
        self.assertFalse((tree / ".git").exists())
        self.assertFalse((tree / ".gitignore").exists())
        for name in ("sys", "common"):
            self.assertFalse((tree / name).is_symlink())
            (tree / name / "source.c").write_text("private change")
            self.assertEqual((reference / name / "source.c").read_text(), name)
        self.assertEqual((reference / ".git/config").read_text(), "original Git config")

    def test_namespace_ledger_cannot_overlap_native_tree_or_existing_input(self):
        linux, tree = self.inputs[:2]
        manifest = self.work / "manifest.json"
        manifest.write_text("{}")
        for output in (tree / "ledger.json", manifest):
            with self.subTest(output=output):
                with self.assertRaises(RuntimeError):
                    namespace.stage_paths(linux, tree, manifest, output)


class ConfiguredOwners(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name).resolve()
        self.source = "external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
        self.path = self.tree / "sys" / self.source
        self.path.parent.mkdir(parents=True)
        self.path.write_text("synthetic source")
        self.rows = [{"group": "i915", "source": self.source, "object": "intel_dp.o"}]

    def check(self, allfiles=None, objects="intel_dp.o"):
        return prepare.configured_graph(self.rows, self.tree,
            self.source if allfiles is None else allfiles, objects)

    def test_expanded_relative_and_absolute_sources_bind_exact_owner(self):
        for allfiles in (self.source, str(self.path)):
            with self.subTest(allfiles=allfiles):
                verified = self.check(allfiles)
                self.assertEqual(verified[0]["source"], self.source)
                self.assertEqual(verified[0]["source_sha256"],
                                 hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_missing_selected_object_does_not_pass(self):
        with self.assertRaisesRegex(RuntimeError, "owner differs"):
            self.check(objects="other.o")

    def test_duplicate_expanded_object_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate expanded"):
            self.check(objects="intel_dp.o intel_dp.o")

    def test_same_basename_old_owner_is_rejected_even_when_modern_source_is_listed(self):
        old = self.tree / "sys/external/bsd/drm2/i915drm/intel_dp.c"
        old.parent.mkdir(parents=True)
        old.write_text("old adapter")
        with self.assertRaisesRegex(RuntimeError, "owner differs"):
            self.check(self.source + " " + str(old))

    def test_private_common_support_sources_are_allowed(self):
        common = self.tree / "common/lib/support.c"
        common.parent.mkdir(parents=True)
        common.write_text("native common support")
        verified = self.check(self.source + " ../common/lib/support.c",
                              "intel_dp.o support.o")
        self.assertEqual(len(verified), 1)

    def test_configured_source_outside_private_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / "intel_dp.c"
            external.write_text("foreign owner")
            with self.assertRaisesRegex(RuntimeError, "escapes"):
                self.check(self.source + " " + str(external))


class ImportProvenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.linux, self.tree = self.work / "linux", self.work / "native"
        self.linux.mkdir()
        self.tree.mkdir()
        self.mapping = {"uuid_t": "netbsd_linux_uuid_t"}
        self.sources = {"drivers/gpu/drm/simple.c": "uuid_t value;\n",
                        "include/linux/vfio.h": "#include <linux/iommu.h>\nuuid_t data;\n"}
        self.seed = self.tree / "sys/external/bsd/drm2/dist/drm/simple.c"
        self.header = self.tree / "sys/external/bsd/drm2/dist/include/linux/vfio.h"
        self.seed.parent.mkdir(parents=True)
        self.header.parent.mkdir(parents=True)
        self.seed.write_bytes(self.sources["drivers/gpu/drm/simple.c"].encode())
        self.manifest = self.work / "manifest.json"
        self.manifest.write_text(json.dumps({"linux_pin": namespace.PIN,
            "linux_head_verified": True, "files": [{"path": "drivers/gpu/drm/simple.c"}]}))
        self.api, self.out = self.work / "api.json", self.work / "out.json"

    def imported(self, current=True, tamper=False):
        old = self.sources["include/linux/vfio.h"]
        data = namespace.translate(namespace.adapt_includes(old, "include/linux/vfio.h")
                                   if current else old, self.mapping)
        if tamper:
            data += "unsigned unowned_change;\n"
        self.header.write_bytes(data.encode())
        row = {"include": "linux/vfio.h", "state": "IMPORTED_API_TRANSLATED_UNREVIEWED",
               "linux_path": "include/linux/vfio.h", "path": self.header.relative_to(self.tree).as_posix(),
               "sha256": hashlib.sha256(self.header.read_bytes()).hexdigest()}
        if current:
            row["translation"] = namespace.translation_identity(self.mapping)
        report = {"linux_pin": namespace.PIN, "rows": [row]}
        self.api.write_text(json.dumps(report))
        return report

    def integrate(self):
        with patch.object(namespace, "bindings", return_value=self.mapping), \
                patch.object(namespace, "frozen", side_effect=lambda linux, path: self.sources[path]):
            return namespace.integrate(self.linux, self.tree, self.manifest, self.api, self.out)

    def test_current_import_include_and_identifier_provenance_is_accepted(self):
        self.imported()
        header = self.header.read_bytes()
        self.integrate()
        self.assertEqual(self.header.read_bytes(), header)
        self.assertEqual(self.seed.read_text(), "netbsd_linux_uuid_t value;\n")
        self.assertIn("#include <linux/uuid.h>", self.header.read_text())

    def test_legacy_importer_exact_transform_upgrades_without_accepting_arbitrary_bytes(self):
        self.imported(current=False)
        self.integrate()
        self.assertIn("#include <linux/uuid.h>", self.header.read_text())
        row = json.loads(self.out.read_text())["rows"][0]
        self.assertEqual(row["translation"], namespace.translation_identity(self.mapping))
        self.assertEqual(row["sha256"], hashlib.sha256(self.header.read_bytes()).hexdigest())

    def test_updated_ledger_hash_does_not_authorize_unowned_content(self):
        self.imported(tamper=True)
        seed = self.seed.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "outside owned translation"):
            self.integrate()
        self.assertEqual(self.seed.read_bytes(), seed)
        self.assertFalse(self.out.exists())

    def test_wrong_producer_mapping_fingerprint_is_rejected(self):
        report = self.imported()
        report["rows"][0]["translation"]["mapping_sha256"] = "wrong"
        self.api.write_text(json.dumps(report))
        with self.assertRaisesRegex(RuntimeError, "unrecognized API import"):
            self.integrate()
        self.assertFalse(self.out.exists())

    def test_existing_output_fails_before_git_reader_or_source_mutation(self):
        self.imported()
        self.out.write_text("retained evidence")
        with patch.object(namespace, "bindings") as reader:
            with self.assertRaisesRegex(RuntimeError, "preserve existing"):
                namespace.integrate(self.linux, self.tree, self.manifest, self.api, self.out)
            reader.assert_not_called()
        self.assertEqual(self.out.read_text(), "retained evidence")


if __name__ == "__main__":
    unittest.main()
