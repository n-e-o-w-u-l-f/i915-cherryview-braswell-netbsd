#!/usr/bin/env python3
"""Exact membership and mocked native entrypoint admission; no native I/O.

The entrypoint controls call the real main functions with an in-memory path
model. They never inspect historical host paths, run tools, stage or compile.
"""
from contextlib import ExitStack, contextmanager, redirect_stderr
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hp_graph_contract as contract
import prepare_hp_full_graph as prepare
import probe_hp_full_graph as probe


class GraphContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = contract.REFERENCE.read_bytes().replace(b"\r\n", b"\n")
        cls.document = json.loads(cls.raw)

    def groups(self):
        return deepcopy(self.document["graph"]["units"])

    def admit(self, groups):
        return contract.selected_units(groups, linux_pin=contract.LINUX_PIN,
                                       netbsd_pin=contract.NETBSD_PIN)

    @contextmanager
    def reference(self, raw, reviewed=False):
        # reviewed=True exercises structural checks after a hypothetical,
        # explicitly reviewed replacement digest; production has no override.
        with ExitStack() as stack:
            stack.enter_context(patch.object(contract, "REFERENCE",
                                             Mock(read_bytes=Mock(return_value=raw))))
            if reviewed:
                digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
                stack.enter_context(patch.object(contract, "REFERENCE_SHA256", digest))
            yield

    def test_exact_410_rows_and_source_object_mapping(self):
        rows = self.admit(self.groups())
        self.assertEqual(len(rows), 410)
        self.assertEqual({g: sum(r["group"] == g for r in rows)
                          for g in contract.EXPECTED_COUNTS}, contract.EXPECTED_COUNTS)
        self.assertEqual(len({r["object"] for r in rows}), 410)
        self.assertEqual(rows, sorted(rows, key=lambda r: r["source"]))
        self.assertIn({"group": "i915", "source":
                       "external/bsd/drm2/dist/drm/i915/display/intel_dp.c",
                       "object": "intel_dp.o"}, rows)

    def test_order_independent_without_mutating_input(self):
        groups = {g: list(reversed(names)) for g, names in reversed(list(self.groups().items()))}
        original = deepcopy(groups)
        self.assertEqual(self.admit(groups), self.admit(self.groups()))
        self.assertEqual(groups, original)

    def test_same_count_wrong_source_rejected_in_every_group(self):
        for group in contract.EXPECTED_COUNTS:
            with self.subTest(group=group):
                groups = self.groups()
                groups[group][0] = "unreviewed_source.c"
                with self.assertRaisesRegex(ValueError, "source set differs"):
                    self.admit(groups)

    def test_missing_extra_or_nondictionary_groups_rejected(self):
        missing, extra = self.groups(), self.groups()
        del missing["ttm"]
        extra["foreign"] = []
        for groups in (missing, extra, None, [], "i915"):
            with self.subTest(groups=type(groups).__name__):
                with self.assertRaisesRegex(ValueError, "exact i915/DRM/display/TTM groups"):
                    self.admit(groups)

    def test_nonlist_and_nonstring_entries_rejected(self):
        for value in (None, {}, "display/intel_dp.c", tuple(self.groups()["i915"]),
                      [None] + self.groups()["i915"][1:]):
            with self.subTest(value=type(value).__name__):
                groups = self.groups()
                groups["i915"] = value
                with self.assertRaises(ValueError):
                    self.admit(groups)

    def test_missing_or_extra_source_rejected(self):
        for delta in (-1, 1):
            with self.subTest(delta=delta):
                groups = self.groups()
                if delta < 0:
                    groups["ttm"].pop()
                else:
                    groups["ttm"].append("new_ttm.c")
                with self.assertRaisesRegex(ValueError, "source count differs"):
                    self.admit(groups)

    def test_duplicate_source_rejected(self):
        groups = self.groups()
        groups["i915"][0] = groups["i915"][1]
        with self.assertRaisesRegex(ValueError, "duplicate selected source"):
            self.admit(groups)

    def test_cross_group_object_basename_collision_rejected(self):
        groups = self.groups()
        groups["i915"][0] = "display/" + groups["drm"][0]
        with self.assertRaisesRegex(ValueError, "object basename collision"):
            self.admit(groups)

    def test_noncanonical_unsafe_and_non_c_paths_rejected(self):
        names = ("../escape.c", "/absolute.c", "a/../b.c", "a/./b.c", "a//b.c",
                 "./foo.c", "C:/drive.c", "a\\b.c", "a\x00b.c", "a b.c",
                 "a\nb.c", "a\x1bb.c", "$(shell).c", "foo.S", "foo.C", "")
        for name in names:
            with self.subTest(name=name):
                groups = self.groups()
                groups["i915"][0] = name
                with self.assertRaises(ValueError):
                    self.admit(groups)

    def test_wrong_or_missing_stage_pins_fail_before_reference_read(self):
        for linux_pin, netbsd_pin in ((None, contract.NETBSD_PIN),
                                      (contract.LINUX_PIN, None),
                                      ("wrong", contract.NETBSD_PIN),
                                      (contract.LINUX_PIN, "wrong")):
            with self.subTest(linux=linux_pin, netbsd=netbsd_pin):
                with patch.object(contract, "_reference_groups") as load:
                    with self.assertRaisesRegex(ValueError, "stage:.*pins differ"):
                        contract.selected_units(self.groups(), linux_pin=linux_pin,
                                                netbsd_pin=netbsd_pin)
                    load.assert_not_called()

    def test_crlf_checkout_preserves_reviewed_reference_identity(self):
        with self.reference(self.raw.replace(b"\n", b"\r\n")):
            self.assertEqual(len(self.admit(self.groups())), 410)

    def test_changed_reference_and_matching_candidate_cannot_redefine_graph(self):
        document = deepcopy(self.document)
        document["graph"]["units"]["i915"][0] = "display/unreviewed.c"
        raw = (json.dumps(document) + "\n").encode()
        with self.reference(raw):
            with self.assertRaisesRegex(ValueError, "evidence SHA256 differs"):
                self.admit(document["graph"]["units"])

    def test_missing_reference_is_not_accepted(self):
        with patch.object(contract, "REFERENCE",
                          Mock(read_bytes=Mock(side_effect=FileNotFoundError("fixture")))):
            with self.assertRaises(FileNotFoundError):
                self.admit(self.groups())

    def test_reviewed_reference_still_requires_shape_pins_and_exact_counts(self):
        cases = []
        cases.append([])
        for change in ("missing_graph", "wrong_top_pin", "wrong_graph_pin",
                       "missing_group", "wrong_count", "duplicate", "unsafe", "collision"):
            document = deepcopy(self.document)
            groups = document["graph"]["units"]
            if change == "missing_graph":
                del document["graph"]
            elif change == "wrong_top_pin":
                document["linux_pin"] = "wrong"
            elif change == "wrong_graph_pin":
                document["graph"]["netbsd_pin"] = "wrong"
            elif change == "missing_group":
                del groups["ttm"]
            elif change == "wrong_count":
                groups["display"].pop()
            elif change == "duplicate":
                groups["i915"][0] = groups["i915"][1]
            elif change == "unsafe":
                groups["i915"][0] = "../escape.c"
            elif change == "collision":
                groups["i915"][0] = "display/" + groups["drm"][0]
            cases.append(document)
        for index, document in enumerate(cases):
            with self.subTest(index=index):
                with self.reference(json.dumps(document).encode(), reviewed=True):
                    with self.assertRaises(ValueError):
                        self.admit(self.groups())


class NativeBoundary(Exception):
    """In-memory fixture reached the first operation outside admission."""


class EntrypointAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.groups = json.loads(contract.REFERENCE.read_bytes())["graph"]["units"]

    @contextmanager
    def environment(self, module, groups=None, stage_changes=None,
                    system="NetBSD", release="11.0", hostname="hp-tpnw121.fritz.box"):
        groups = deepcopy(self.groups if groups is None else groups)
        work = PurePosixPath("/root/hp-driver-port-20261005")
        reads, writes = [], []
        manifest = {"linux_head_verified": True, "linux_pin": contract.LINUX_PIN,
                    "netbsd_pin": contract.NETBSD_PIN, "files": []}
        staged = {"state": "CONFIGURED", "linux_pin": contract.LINUX_PIN,
                  "netbsd_pin": contract.NETBSD_PIN, "units": groups}
        target = manifest if module is prepare else staged
        target.update(stage_changes or {})
        readmap = {work / "full-scope-audit/linux-stage-verified/PORT-MANIFEST.json":
                   json.dumps(manifest), work / "full-linux-graph-status.json": json.dumps(staged)}

        class MemoryPath:
            def __init__(self, value):
                self.path = PurePosixPath(str(value))

            def __str__(self):
                return str(self.path)

            def __truediv__(self, value):
                return MemoryPath(self.path / value)

            def __eq__(self, other):
                return isinstance(other, MemoryPath) and self.path == other.path

            @property
            def parent(self):
                return MemoryPath(self.path.parent)

            def resolve(self, strict=False):
                return self

            def exists(self):
                return False

            def read_text(self, *args, **kwargs):
                reads.append(str(self.path))
                if self.path in readmap:
                    return readmap[self.path]
                raise NativeBoundary("read beyond admission: " + str(self.path))

            def mkdir(self, *args, **kwargs):
                writes.append(str(self.path))
                raise NativeBoundary("would create native stage/output")

        argv = [module.__name__, "--workspace", str(work)]
        if module is probe:
            argv.extend(["--output", str(work / "new-contract-proof")])
        directories = {"drivers/gpu/drm/i915": "i915", "drivers/gpu/drm": "drm",
                       "drivers/gpu/drm/display": "display", "drivers/gpu/drm/ttm": "ttm"}
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", argv))
            stack.enter_context(patch.object(module, "Path", MemoryPath))
            stack.enter_context(patch.object(module.platform, "system", return_value=system))
            stack.enter_context(patch.object(module.platform, "release", return_value=release))
            stack.enter_context(patch.object(module.socket, "gethostname", return_value=hostname))
            run = stack.enter_context(patch.object(module.subprocess, "run",
                                      side_effect=AssertionError("unexpected external execution")))
            check_output = stack.enter_context(patch.object(module.subprocess, "check_output",
                                               side_effect=AssertionError("unexpected external execution")))
            if module is prepare:
                stack.enter_context(patch.object(module, "selected", side_effect=
                                    lambda root, directory, *args: groups.get(directories[directory])))
            yield reads, writes, run, check_output

    def rejected(self, module, groups=None, stage_changes=None, **host):
        with self.environment(module, groups, stage_changes, **host) as observation:
            reads, writes, run, check_output = observation
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                module.main()
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(writes, [])
            run.assert_not_called()
            check_output.assert_not_called()
            self.assertFalse(any(path.endswith("/Makefile") for path in reads))
            return reads

    def test_prepare_wrong_same_size_set_aborts_before_staging_or_tool_execution(self):
        groups = deepcopy(self.groups)
        groups["i915"][0] = "display/unreviewed.c"
        self.assertEqual(len(self.rejected(prepare, groups)), 1)

    def test_prepare_missing_dependency_group_aborts_before_staging(self):
        groups = deepcopy(self.groups)
        del groups["ttm"]
        self.assertEqual(len(self.rejected(prepare, groups)), 1)

    def test_prepare_wrong_materialized_pin_aborts_before_staging(self):
        self.assertEqual(len(self.rejected(prepare, stage_changes={"netbsd_pin": "wrong"})), 1)

    def test_probe_wrong_same_size_set_aborts_before_native_makefile_read(self):
        groups = deepcopy(self.groups)
        groups["drm"][0] = "unreviewed.c"
        self.assertEqual(len(self.rejected(probe, groups)), 1)

    def test_probe_missing_dependency_group_aborts_before_native_makefile_read(self):
        groups = deepcopy(self.groups)
        del groups["ttm"]
        self.assertEqual(len(self.rejected(probe, groups)), 1)

    def test_probe_wrong_missing_pins_or_unconfigured_state_aborts(self):
        for changes in ({"linux_pin": "wrong"}, {"netbsd_pin": None}, {"state": "FAILED"}):
            with self.subTest(changes=changes):
                self.assertEqual(len(self.rejected(probe, stage_changes=changes)), 1)

    def test_foreign_os_release_and_similar_hostname_stop_before_native_reads(self):
        for module in (prepare, probe):
            for host in ({"system": "Linux"}, {"release": "10.1"},
                         {"release": "12.0"}, {"hostname": "hp-tpnw121-other"}):
                with self.subTest(module=module.__name__, host=host):
                    self.assertEqual(self.rejected(module, **host), [])

    def test_valid_prepare_reaches_only_first_simulated_stage_creation(self):
        with self.environment(prepare) as (reads, writes, run, check_output):
            with self.assertRaises(NativeBoundary):
                prepare.main()
            self.assertEqual(writes, ["/root/hp-driver-port-20261005/netbsd-full-linux"])
            self.assertEqual(len(reads), 1)
            run.assert_not_called()
            check_output.assert_not_called()

    def test_valid_probe_reaches_next_native_selection_gate_without_execution(self):
        with self.environment(probe) as (reads, writes, run, check_output):
            with self.assertRaises(NativeBoundary):
                probe.main()
            self.assertEqual(writes, [])
            self.assertEqual(reads[-1], "/root/hp-driver-port-20261005/full-linux-obj/Makefile")
            run.assert_not_called()
            check_output.assert_not_called()


if __name__ == "__main__":
    unittest.main()
