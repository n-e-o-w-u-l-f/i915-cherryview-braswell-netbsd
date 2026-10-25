#!/usr/bin/env python3
"""Offline semantic coverage acceptance tests; no native NetBSD compile."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MOD = Path(__file__).resolve().parents[1] / 'tools/gate_full_hp_port_coverage.py'
spec = importlib.util.spec_from_file_location('fullscope', MOD)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
HEAD = ('linux_source\tstructural_class\tnetbsd_evidence\tsemantic_state\n')
ROWS = [
    'display/vlv_clock.c\tUNRESOLVED_NO_BASENAME\t\tUNREVIEWED',
    'gem/i915_gem_context.c\tEXACT_ACTIVE_DIST\tdist:gem/i915_gem_context.c\tUNREVIEWED',
    'gt/intel_rps.c\tACTIVE_OVERRIDE_OR_MOVED\tglue:intel_rps.c\tUNREVIEWED',
]
SRC = (HEAD + '\n'.join(ROWS) + '\n').encode()
BLOB = gate.git_blob(SRC)
SHA = 'a'*40

def reviewed_native():
    return dict(status='ADAPTED', linux_pin=gate.LINUX_PIN,
                netbsd_pin=gate.NETBSD_PIN,target_commit=SHA,
                source_path='sys/external/bsd/drm2/test.c',
                semantic_review='b'*40,native_object_evidence='c'*40)

class FullPort(unittest.TestCase):
    def report(self, content=SRC, attestations=None, blob=BLOB):
        return gate.evaluate(content, attestations,required_blob=blob,expected_units=3)

    def test_real_shape_unreviewed_fails_closed(self):
        r=self.report()
        self.assertEqual(r['result'],'BLOCKED')
        self.assertEqual(r['total_linux_active_units'],3)
        self.assertEqual(r['no_closed_semantics'],3)
        self.assertEqual(r['release_manifest_generated'],False)
        self.assertEqual(r['kernel_or_hardware_acceptance'],'NOT_RUN')
        self.assertIn('rtl_pcie_firmware_mac_bb_rf_irq_tx_rx',r['separate_native_and_physical_gates'])

    def test_structural_present_does_not_imply_semantic_parity(self):
        r=self.report()
        self.assertEqual(r['structural_class_counts']['EXACT_ACTIVE_DIST'],1)
        self.assertIn('gem/i915_gem_context.c',r['open_sources'])

    def test_positive_semantics_still_no_release(self):
        a={row.split('\t')[0]:reviewed_native() for row in ROWS}
        r=self.report(attestations={'units':a})
        self.assertEqual(r['result'],'READY_FOR_NATIVE_AND_PHYSICAL_REVIEW_ONLY')
        self.assertFalse(r['release_manifest_generated'])
        self.assertEqual(r['kernel_or_hardware_acceptance'],'NOT_RUN')

    def test_tamper_refused_by_blob(self):
        with self.assertRaisesRegex(ValueError,'blob'):
            self.report(content=SRC.replace(b'UNREVIEWED',b'PORTED',1))

    def test_duplicate_linux_source_refused(self):
        rows=[ROWS[0],ROWS[0],ROWS[2]]
        data=(HEAD+'\n'.join(rows)+'\n').encode()
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.report(content=data,blob=gate.git_blob(data))

    def test_missing_native_object_receipt_rejected(self):
        bad=reviewed_native();del bad['native_object_evidence']
        with self.assertRaisesRegex(ValueError,'native_object_evidence'):
            self.report(attestations={'units':{'display/vlv_clock.c':bad}})

    def test_foreign_or_stale_source_pin_rejected(self):
        bad=reviewed_native();bad['linux_pin']='1'*40
        with self.assertRaisesRegex(ValueError,'pin mismatch'):
            self.report(attestations={'units':{'display/vlv_clock.c':bad}})

    def test_extra_source_not_in_reference_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside pinned'):
            self.report(attestations={'units':{'fake.c':reviewed_native()}})

    def test_inapplicable_requires_reason_and_review(self):
        bad=dict(status='REFERENCE_INAPPLICABLE',linux_pin=gate.LINUX_PIN,
                 netbsd_pin=gate.NETBSD_PIN,reason='old',semantic_review='c'*40)
        with self.assertRaisesRegex(ValueError,'substantive reason'):
            self.report(attestations={'units':{'display/vlv_clock.c':bad}})
        bad['reason']='Target Cherryview cannot physically expose this non-CHV engine'
        r=self.report(attestations={'units':{'display/vlv_clock.c':bad}})
        self.assertEqual(r['no_closed_semantics'],2)

    def test_root_level_active_linux_source_is_allowed(self):
        data=(HEAD+ROWS[0]+'\n'+'i915_pci.c\tEXACT_ACTIVE_DIST\tdist:i915_pci.c\tUNREVIEWED\n'+ROWS[2]+'\n').encode()
        r=self.report(content=data,blob=gate.git_blob(data))
        self.assertEqual(r['no_closed_semantics'],3)

    def test_path_traversal_rejected(self):
        data=(HEAD+ROWS[0]+'\n'+'../bad.c\tEXACT_ACTIVE_DIST\tdist:bad.c\tUNREVIEWED\n'+ROWS[2]+'\n').encode()
        with self.assertRaisesRegex(ValueError,'unrecognized source'):
            self.report(content=data,blob=gate.git_blob(data))

    def test_cli_exit_refuses_release_without_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.tsv';p.write_bytes(SRC)
            # Default command intentionally refuses the non-authoritative
            # three-row fixture rather than accept an arbitrary source file.
            r=subprocess.run([sys.executable,str(MOD),'--coverage-tsv',str(p)],
                             text=True,capture_output=True,timeout=10)
            self.assertEqual(r.returncode,2)
            self.assertIn('blob',r.stderr)

if __name__=='__main__':unittest.main(verbosity=2)
