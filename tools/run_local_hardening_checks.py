#!/usr/bin/env python3
"""Local Python-only hardening checks with an attributable result, no compiler."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('preserve previous evidence; choose a new report file')
    report = dict(state='RUNNING', started=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), platform=platform.platform(), tests=[],
                  git_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                  git_status=subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True),
                  limitation='Python/source/synthetic controls only; native C, pinned-tree integration and KMS NOT_RUN.')
    scripts = ['test_hp_graph_preflight.py', 'test_native_drm_error_paths.py', 'test_pinned_source_runner_scope.py']
    paths = sorted([*ROOT.joinpath('tools').glob('*.py'), *ROOT.joinpath('tests').glob('*.py')])
    report['python_source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    report['canonical_drm_sha256'] = hashlib.sha256((ROOT / 'compat/native-drm/drm_cdevsw.c').read_bytes()).hexdigest()
    try:
        for path in paths:
            ast.parse(path.read_text(), filename=str(path))
        report['syntax_files'] = len(paths)
        for name in scripts:
            command = [sys.executable, '-B', str(ROOT / 'tests' / name)]
            proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=300)
            report['tests'].append(dict(script=name, command=command, exit=proc.returncode,
                                        stdout=proc.stdout, stderr=proc.stderr))
            print(name, 'PASS' if proc.returncode == 0 else 'FAIL', flush=True)
        report['state'] = 'PASSED' if all(r['exit'] == 0 for r in report['tests']) else 'FAILED'
    except Exception as error:
        report['state'] = 'FAILED'
        report['error'] = str(error)
    report['finished'] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation keeps an existing concurrent result intact.
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    return 0 if report['state'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
