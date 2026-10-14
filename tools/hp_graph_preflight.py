#!/usr/bin/env python3
"""Read-only, fail-closed inputs for HP native probes; never a boot gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_hp():
    host = socket.gethostname().split('.')[0]
    if platform.system() != 'NetBSD' or host != 'hp-tpnw121':
        raise ValueError('native tools are authorized only on hp-tpnw121 / NetBSD')


def relative_path(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ValueError('unsafe relative source path: ' + name)
    return path


def selected_units(groups):
    expected = json.loads((ROOT / 'docs/evidence/HP_FULL_GRAPH_API_20261005.json').read_text())['graph']['units']
    if set(groups) != set(expected):
        raise ValueError('missing/extra i915/DRM/display/TTM group')
    rows = []
    for group, names in groups.items():
        if len(names) != len(set(names)) or set(names) != set(expected[group]):
            raise ValueError('frozen selected source set differs: ' + group)
        for name in names:
            relative_path(name)
            if not name.endswith('.c'):
                raise ValueError('non-C selected unit')
            rel = 'external/bsd/drm2/dist/drm/' + ('' if group == 'drm' else group + '/') + name
            rows.append({'group': group, 'source': rel, 'object': Path(name).stem + '.o'})
    if len({r['object'] for r in rows}) != len(rows):
        raise ValueError('native object basename collision')
    return sorted(rows, key=lambda r: r['source'])


def configured_rules(text, tree):
    """Parse pinned config(5) ALLFILES + OBJS.<attribute>/OBJS selection.

    mkmakefile.c emits ordinary sources through ALLFILES, not explicit rules.
    Explicit custom rules alone cannot establish selected-kernel ownership.
    """
    result = {}
    text = text.replace('\\\n', ' ')
    variables = {}
    source_roots = re.findall(r'^S\s*=\s*(\S+)\s*$', text, re.M)
    if len(source_roots) != 1 or Path(source_roots[0]).resolve() != (tree / 'sys').resolve():
        raise ValueError('configured S must identify the explicit native tree')
    for line in text.splitlines():
        line = line.split('#', 1)[0]
        match = re.match(r'^(ALLFILES|OBJS(?:\.[\w.-]+)?)\s*(\+?=)\s*(.*)$', line)
        if not match:
            continue
        key, op, value = match.groups()
        if op == '=' and key in variables:
            raise ValueError('ambiguous configured selection: ' + key)
        variables.setdefault(key, []).extend(value.split())
    if not variables.get('ALLFILES') or not variables.get('OBJS'):
        raise ValueError('config(5) ALLFILES and OBJS selection required')
    for token in variables['ALLFILES']:
        relative_path(token)
        if not token.endswith(('.c', '.S', '.s')):
            raise ValueError('unsupported selected source: ' + token)
        obj = Path(token).stem + '.o'
        if obj in result:
            raise ValueError('ambiguous selected source owner: ' + obj)
        result[obj] = token
    selected = []
    for token in variables['OBJS']:
        if token.endswith('.ko'):
            key = 'OBJS.' + token[:-3]
            if key not in variables:
                raise ValueError('missing configured attribute: ' + key)
            selected.extend(variables[key])
        elif token.endswith('.o'):
            selected.append(token)
        else:
            raise ValueError('unsupported configured object expression: ' + token)
    if len(selected) != len(set(selected)) or set(selected) != set(result):
        raise ValueError('ALLFILES / selected OBJS ownership mismatch')
    for line in text.splitlines():
        line = line.split('#', 1)[0]
        match = re.match(r'^([\w.-]+\.o)\s*:(?![=])\s*(.*)$', line)
        if not match:
            continue
        sources = []
        for token in match[2].split():
            for prefix in ('${S}/', '$(S)/', '$S/', str(tree / 'sys') + '/'):
                if token.startswith(prefix):
                    token = token[len(prefix):]
                    break
            if token.endswith(('.c', '.S', '.s')):
                relative_path(token)
                sources.append(token)
        if not sources:
            continue
        if len(sources) != 1 or result.get(match[1]) != sources[0]:
            raise ValueError('ambiguous configured object owner: ' + match[1])
    return result


def preflight(tree, obj, tools, status):
    tree, obj, tools, status = [Path(p).resolve(strict=True) for p in (tree, obj, tools, status)]
    if len({tree, obj, tools}) != 3 or any(a in b.parents for a in (tree, obj, tools) for b in (tree, obj, tools) if a != b):
        raise ValueError('source/object/tool directories must be separate')
    staged = json.loads(status.read_text())
    if staged.get('state') != 'CONFIGURED' or staged.get('linux_pin') != LINUX_PIN or staged.get('netbsd_pin') != NETBSD_PIN:
        raise ValueError('configured frozen-reference stage required')
    rows = selected_units(staged['units'])
    # Old reports did not bind configured C files to content: they fail closed.
    hashes = staged.get('source_sha256', {})
    if set(hashes) != {r['source'] for r in rows}:
        raise ValueError('complete current 410-source hash ledger required; restage explicitly')
    manifests = staged.get('manifest_sha256', {})
    required = {'sys/external/bsd/drm2/i915drm/files.i915drmkms',
                'sys/external/bsd/drm2/drm/files.drmkms', 'sys/external/bsd/drm2/ttm/files.ttm'}
    if not required <= set(manifests):
        raise ValueError('complete config manifest hashes required')
    for name, sha in manifests.items():
        relative_path(name)
        if digest(tree / name) != sha:
            raise ValueError('modified configuration manifest: ' + name)
    generated = obj / 'Makefile'
    if digest(generated) != staged.get('makefile_sha256'):
        raise ValueError('generated Makefile hash differs from configured stage')
    rules = configured_rules(generated.read_text(), tree)
    for row in rows:
        source = tree / 'sys' / row['source']
        if digest(source) != hashes[row['source']]:
            raise ValueError('modified staged source: ' + row['source'])
        if rules.get(row['object']) != row['source']:
            raise ValueError('configured object selects another/missing source: ' + row['object'])
        row['source_sha256'] = hashes[row['source']]
    for name in ('nbmake-amd64', 'x86_64--netbsd-gcc', 'x86_64--netbsd-nm'):
        if not (tools / 'bin' / name).is_file():
            raise ValueError('missing native tool: ' + name)
    if not (obj / 'machine/cdefs.h').is_file():
        raise ValueError('missing generated native ABI headers')
    headers = {'sys/' + str(p.relative_to(tree / 'sys')): digest(p)
               for p in sorted((tree / 'sys').rglob('*.h')) if p.is_file()}
    generated_headers = {str(p.relative_to(obj)): digest(p)
                         for p in sorted(obj.rglob('*.h')) if p.is_file()}
    generated_headers['machine/cdefs.h'] = digest(obj / 'machine/cdefs.h')
    return {'state': 'INPUTS_VERIFIED', 'linux_pin': LINUX_PIN, 'netbsd_pin': NETBSD_PIN,
            'tree': str(tree), 'object_dir': str(obj), 'tool_dir': str(tools),
            'graph_status_sha256': digest(status), 'makefile_sha256': digest(generated),
            'tools_sha256': {n: digest(tools / 'bin' / n) for n in
                ('nbmake-amd64', 'x86_64--netbsd-gcc', 'x86_64--netbsd-nm')},
            'units': rows, 'configured_rules': rules,
            'header_sha256': headers, 'generated_header_sha256': generated_headers,
            'limitation': 'Input identity only; no compilation, link, ABI, recovery or KMS acceptance.'}


def arguments(parser):
    parser.add_argument('--native-tree', type=Path, required=True)
    parser.add_argument('--object-dir', type=Path, required=True)
    parser.add_argument('--tool-dir', type=Path, required=True)
    parser.add_argument('--graph-status', type=Path, required=True)


def execution_identity(inputs):
    """Run only on HP. Versions and Git identity precede compiler probes."""
    require_hp()
    result = {'python': platform.python_version(), 'system': platform.platform(),
              'hostname': socket.gethostname(), 'tools': {}}
    for name in ('x86_64--netbsd-gcc', 'x86_64--netbsd-nm'):
        command = [str(Path(inputs['tool_dir']) / 'bin' / name), '--version']
        proc = subprocess.run(command, text=True, capture_output=True, timeout=30)
        if proc.returncode:
            raise ValueError('tool version preflight failed: ' + name)
        result['tools'][name] = {'command': command, 'version': proc.stdout.splitlines()[0]}
    result['git_head'] = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    result['git_status'] = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip()
    result['implementation_sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in
        [Path(__file__), ROOT / 'tools/probe_hp_full_graph.py', ROOT / 'tools/build_hp_native_drm_adapter.py',
         ROOT / 'tools/audit_hp_native_drm_symbol_owners.py', ROOT / 'compat/native-drm/drm_cdevsw.c']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    args = parser.parse_args()
    try:
        require_hp()
        print(json.dumps(preflight(args.native_tree, args.object_dir, args.tool_dir, args.graph_status), indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
