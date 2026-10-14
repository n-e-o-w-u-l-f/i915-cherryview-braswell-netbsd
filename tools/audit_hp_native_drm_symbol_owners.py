#!/usr/bin/env python3
"""Audit current selected ELF owners, never infer ABI/KMS from lexical hits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import subprocess
from hp_graph_preflight import arguments, digest, preflight, require_hp


def verify_elf(path):
    header = Path(path).read_bytes()[:64]
    if (len(header) < 64 or header[:7] != b'\x7fELF\x02\x01\x01' or
            header[16:24] != b'\x01\x00\x3e\x00\x01\x00\x00\x00' or
            header[52:54] != b'\x40\x00'):
        raise ValueError('expected amd64 little-endian ELF relocatable object: ' + str(path))


def parse_nm(text):
    definitions, imports, weak_imports = {}, set(), set()
    for line in text.splitlines():
        parts = line.split()
        if not parts or line.endswith(':'):
            continue
        if len(parts) < 2 or len(parts[-2]) != 1:
            raise ValueError('unrecognized nm record: ' + line)
        kind, name = parts[-2:]
        if kind == 'U':
            imports.add(name)
        elif kind in ('w', 'v'):
            weak_imports.add(name)
        elif kind in 'TDBRSAGCWV':
            definitions[name] = kind
        else:
            raise ValueError('unsupported global nm symbol type: ' + kind)
    return definitions, imports, weak_imports


def symbol_graph(objects, expected_objects):
    expected_objects = set(expected_objects)
    owners, consumers, weak = {}, {}, {}
    for obj, data in sorted(objects.items()):
        for name, kind in data['definitions'].items():
            owners.setdefault(name, []).append({'object': obj, 'kind': kind})
        for name in data['imports']:
            consumers.setdefault(name, []).append(obj)
        for name in data['weak_imports']:
            weak.setdefault(name, []).append(obj)
    conflicts = {}
    for name, rows in owners.items():
        # Common symbols need explicit ABI review too; never silently choose
        # between an old adapter and a modern same-name strong definition.
        strong = [r for r in rows if r['kind'] not in ('W', 'V')]
        if len(strong) > 1:
            conflicts[name] = strong
    missing = sorted(set(expected_objects) - set(objects))
    unselected = sorted(set(objects) - expected_objects)
    unresolved = sorted(set(consumers) - set(owners))
    return {'state': 'OBJECT_SYMBOL_CLOSURE' if objects and not (missing or unselected or unresolved or conflicts) else 'GRAPH_OPEN',
            'selected_objects': len(expected_objects), 'inspected_objects': len(objects),
            'missing_objects': missing, 'unresolved_symbols': unresolved,
            'unselected_objects': unselected,
            'conflicting_strong_owners': conflicts,
            'edges': {s: {'consumers': c, 'providers': owners.get(s, [])} for s, c in sorted(consumers.items())},
            'weak_imports': dict(sorted(weak.items()))}


def verified_rows(reports, inputs):
    """Reject stale/foreign/same-basename provider objects before calling nm."""
    obj_dir, tree = Path(inputs['object_dir']), Path(inputs['tree'])
    result = {}
    for report in reports:
        data = json.loads(Path(report).read_text())
        recorded = data.get('preflight', {})
        for key in ('graph_status_sha256', 'makefile_sha256', 'tools_sha256', 'header_sha256', 'generated_header_sha256'):
            if recorded.get(key) != inputs[key]:
                raise ValueError('build evidence uses another stage: ' + str(report))
        # A failed whole probe can retain explicitly successful units.
        for row in data['units']:
            if row.get('state') != 'PASSED':
                continue
            if row.get('o_exit') != 0 or row.get('d_exit') != 0 or row.get('source_unchanged') is not True:
                raise ValueError('PASSED row lacks successful fresh dependency/compile evidence')
            source = row['source']
            obj = Path(source).stem + '.o'
            if inputs['configured_rules'].get(obj) != source or obj in result:
                raise ValueError('duplicate/unselected provider owner: ' + obj)
            artifact = row.get('artifact', {})
            actual = (obj_dir / obj).resolve(strict=True)
            if Path(artifact['path']).resolve(strict=True) != actual or not actual.stat().st_size:
                raise ValueError('wrong/empty provider artifact: ' + obj)
            if digest(actual) != artifact['sha256'] or digest(tree / 'sys' / source) != row['source_sha256']:
                raise ValueError('stale source/object evidence: ' + obj)
            verify_elf(actual)
            result[obj] = {'source': source, 'source_sha256': row['source_sha256'],
                           'artifact_sha256': artifact['sha256'], 'report_sha256': digest(report)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    parser.add_argument('--build-status', type=Path, action='append', required=True,
                        help='probe ledger; additional selected kernel-provider ledgers use the same unit schema')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require_hp()
    inputs = preflight(args.native_tree, args.object_dir, args.tool_dir, args.graph_status)
    output = args.output.resolve()
    protected = [Path(inputs[k]) for k in ('tree', 'object_dir', 'tool_dir')]
    if output.exists() or any(p == output or p in output.parents for p in protected):
        parser.error('new report outside source/object/tools required')
    rows = verified_rows(args.build_status, inputs)
    objects = {}
    nm = Path(inputs['tool_dir']) / 'bin/x86_64--netbsd-nm'
    for obj, row in rows.items():
        command = [str(nm), '-g', str(Path(inputs['object_dir']) / obj)]
        proc = subprocess.run(command, text=True, capture_output=True, timeout=120)
        if proc.returncode:
            raise RuntimeError('nm failed: ' + obj + ': ' + proc.stderr[-500:])
        definitions, imports, weak = parse_nm(proc.stdout)
        objects[obj] = dict(row, definitions=definitions, imports=sorted(imports), weak_imports=sorted(weak), command=command)
        if digest(Path(inputs['object_dir']) / obj) != row['artifact_sha256']:
            raise ValueError('object changed during inspection: ' + obj)
    graph = symbol_graph(objects, inputs['configured_rules'])
    candidates = {s: [] for s in graph['unresolved_symbols']}
    for obj, rel in inputs['configured_rules'].items():
        source = Path(inputs['tree']) / 'sys' / rel
        if not source.is_file():
            continue
        code = source.read_text(errors='replace')
        for sym in candidates:
            pattern = r'(?m)^[A-Za-z_][\w\s*]*\b' + re.escape(sym) + r'\s*\([^;{}]{0,1000}\)\s*\{'
            if re.search(pattern, code):
                candidates[sym].append({'source': rel, 'object': obj, 'source_sha256': digest(source)})
    if preflight(args.native_tree, args.object_dir, args.tool_dir, args.graph_status) != inputs:
        raise ValueError('stage changed during symbol audit')
    for obj, row in rows.items():
        if digest(Path(inputs['object_dir']) / obj) != row['artifact_sha256'] or digest(Path(inputs['tree']) / 'sys' / row['source']) != row['source_sha256']:
            raise ValueError('provider changed during audit: ' + obj)
    graph.update(timestamp_utc=datetime.now(timezone.utc).isoformat(), host=socket.gethostname(),
                 preflight=inputs, objects=objects, source_candidates=candidates,
                 limitation='Lexical candidates never close edges. Object closure is not ABI/semantic parity, final kernel link or KMS acceptance.')
    output.mkdir(mode=0o700)
    (output / 'status.json').write_text(json.dumps(graph, indent=2) + '\n')
    print(graph['state'], 'OBJECTS', len(objects), 'MISSING', len(graph['missing_objects']),
          'UNRESOLVED', len(graph['unresolved_symbols']), 'CONFLICTS', len(graph['conflicting_strong_owners']))
    return 0 if graph['state'] == 'OBJECT_SYMBOL_CLOSURE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
