#!/usr/bin/env python3
"""Fail-closed semantic coverage audit of *all* frozen i915 units.

A source/coverage gate, not a NetBSD build, physical acceptance or release.
Never creates an i915-owned kernel release approval. RTL and physical gates
are independently required after this report becomes fully source-reviewed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

LINUX_PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
NETBSD_PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
ORIGINAL_TSV_BLOB = '011789f5dc3ef916b34019f088abcf53ef20e369'
EXPECTED_UNITS = 323
STRUCTURAL = {'EXACT_ACTIVE_DIST', 'ACTIVE_OVERRIDE_OR_MOVED',
              'PRESENT_NOT_BUILT', 'UNRESOLVED_NO_BASENAME'}
CLOSED = {'PORTED', 'ADAPTED', 'REFERENCE_INAPPLICABLE'}
SHA40 = re.compile(r'^[0-9a-f]{40}$')
REQUIRED_PROVENANCE = ('linux_pin', 'netbsd_pin', 'target_commit',
                       'source_path', 'semantic_review', 'native_object_evidence')
NATIVE_STAGES = (
    'real_file_ref_task_lwp_module_teardown',
    'drm_ioctl_direction_and_size0_buffer_capacity',
    'drm_ttm_gem_uvm_memory_and_mapping_lifetime',
    'pci_dma_irq_hpd_edp_display_kms',
    'rtl_pcie_firmware_mac_bb_rf_irq_tx_rx',
    'rtl_net80211_crypto_wpa2_power_resume',
    'all_modern_i915_active_objects_native_compiled',
    'rtl50_plus_modern_i915_one_kernel_link',
    'f77_stock_recovery_selectable_verified',
    'physical_cherryview_display_kms',
    'physical_rtl8723be_wpa2_encrypted_traffic',
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def read_reference(data: bytes, *, required_blob: str = ORIGINAL_TSV_BLOB,
                   expected_units: int = EXPECTED_UNITS) -> list[dict[str, str]]:
    if git_blob(data) != required_blob:
        raise ValueError('source coverage TSV Git blob does not match pinned evidence')
    try:
        text = data.decode('utf-8', 'strict')
        reader = csv.DictReader(io.StringIO(text), delimiter='\t')
        if reader.fieldnames != ['linux_source', 'structural_class',
                                 'netbsd_evidence', 'semantic_state']:
            raise ValueError('incorrect original coverage TSV header')
        rows = list(reader)
    except UnicodeDecodeError as exc:
        raise ValueError('coverage TSV UTF8 malformed') from exc
    if len(rows) != expected_units:
        raise ValueError(f'coverage must have {expected_units} units, got {len(rows)}')
    seen = set()
    for row in rows:
        if (None in row or not row['linux_source'].endswith('.c') or
                '/' not in row['linux_source'] or
                row['structural_class'] not in STRUCTURAL):
            raise ValueError('unrecognized source/structural coverage entry')
        if row['linux_source'] in seen:
            raise ValueError('duplicate Linux reference source ' + row['linux_source'])
        seen.add(row['linux_source'])
    return rows


def audited_units(rows: list[dict[str, str]], attestation: dict | None) -> tuple[list[str], Counter]:
    attestations = {} if attestation is None else attestation.get('units')
    if not isinstance(attestations, dict):
        raise ValueError('attestation units must be a dictionary')
    names = {row['linux_source'] for row in rows}
    if set(attestations) - names:
        raise ValueError('attestation references sources outside pinned Linux set')
    unclosed = []
    statuses = Counter()
    for row in rows:
        source = row['linux_source']
        entry = attestations.get(source)
        if entry is None:
            unclosed.append(source)
            statuses['NO_NATIVE_SEMANTIC_ATTESTATION'] += 1
            continue
        if not isinstance(entry, dict):
            raise ValueError('invalid source attestation for ' + source)
        status = entry.get('status')
        if status not in CLOSED:
            unclosed.append(source)
            statuses['NOT_REVIEWED'] += 1
            continue
        if entry.get('linux_pin') != LINUX_PIN or entry.get('netbsd_pin') != NETBSD_PIN:
            raise ValueError('source attestation pin mismatch: ' + source)
        if status == 'REFERENCE_INAPPLICABLE':
            if not (isinstance(entry.get('reason'), str) and
                    len(entry['reason'].strip()) >= 20 and
                    isinstance(entry.get('semantic_review'), str) and
                    SHA40.fullmatch(entry['semantic_review'])):
                raise ValueError('inapplicability needs substantive reason and pinned review: ' + source)
        else:
            for key in REQUIRED_PROVENANCE:
                if not entry.get(key):
                    raise ValueError('incomplete native semantic attestation ' + source + ': ' + key)
            for key in ('target_commit', 'semantic_review', 'native_object_evidence'):
                if not SHA40.fullmatch(str(entry[key])):
                    raise ValueError('invalid Git SHA in native source attestation: ' + source)
            if not isinstance(entry['source_path'], str) or not entry['source_path'].startswith('sys/'):
                raise ValueError('native source path must be sys/...: ' + source)
        statuses[status] += 1
    return unclosed, statuses


def evaluate(data: bytes, attestations: dict | None = None, *,
             required_blob: str = ORIGINAL_TSV_BLOB,
             expected_units: int = EXPECTED_UNITS) -> dict:
    rows = read_reference(data, required_blob=required_blob, expected_units=expected_units)
    unclosed, states = audited_units(rows, attestations)
    structural = Counter(r['structural_class'] for r in rows)
    upstream = Counter(r['semantic_state'] for r in rows)
    missing_examples = {
        phase: [r['linux_source'] for r in rows
                if r['linux_source'].startswith(phase) and r['linux_source'] in unclosed][:16]
        for phase in ('display/', 'gem/', 'gt/', 'i915_')
    }
    return {
        'gate': 'SOURCE_SEMANTICS_ONLY',
        'result': 'BLOCKED' if unclosed else 'READY_FOR_NATIVE_AND_PHYSICAL_REVIEW_ONLY',
        'linux_pin': LINUX_PIN,
        'netbsd_pin': NETBSD_PIN,
        'reference_git_blob': git_blob(data),
        'total_linux_active_units': len(rows),
        'structural_class_counts': dict(sorted(structural.items())),
        'original_semantic_state_counts': dict(sorted(upstream.items())),
        'reviewed_attestation_counts': dict(sorted(states.items())),
        'no_closed_semantics': len(unclosed),
        'open_sources': unclosed,
        'open_source_examples_by_subsystem': missing_examples,
        'separate_native_and_physical_gates': list(NATIVE_STAGES),
        'release_manifest_generated': False,
        'kernel_or_hardware_acceptance': 'NOT_RUN',
        'caution': ('Structural presence and old RTL50+i915/DRM5 link are not modern '
                    '323-unit i915/DRM/TTM parity; this is not an authority '
                    'to install, boot or generate a release approval.'),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coverage-tsv', type=Path, required=True)
    parser.add_argument('--attestations', type=Path)
    parser.add_argument('--output-json', type=Path)
    args = parser.parse_args()
    try:
        evidence = json.loads(args.attestations.read_text()) if args.attestations else None
        report = evaluate(args.coverage_tsv.read_bytes(), evidence)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print('HP_FULL_PORT_SOURCE_GATE_REFUSED:', exc, file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    if args.output_json:
        args.output_json.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')
    # This gate never approves release, and does not let a guessed status do so.
    return 2 if report['result'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
