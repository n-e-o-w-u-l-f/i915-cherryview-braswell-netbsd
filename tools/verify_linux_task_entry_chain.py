#!/usr/bin/env python3
"""Verify actual0037 sources, then reconstruct the immutable0035 baseline.

Only byte-exact generated patches and both before/after contracts are accepted.
The disposable snapshot is returned for older source-bound regression fixtures.
The real shared NetBSD development tree is never changed here.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

from generate_linux_task_entry_patch import generate

ROOT = Path(__file__).resolve().parents[1]


def verify_stage(stage, netbsd, scratch):
    stage, netbsd, scratch = map(Path, (stage, netbsd, scratch))
    diff, entry, before, after = generate(netbsd)
    patch = ROOT / 'patches/0037-netbsd-linux-drm-ioctl-task-entry.patch'
    assert patch.read_bytes() == diff.encode(), '0037 generated patch drift'
    assert json.loads((ROOT / 'compat/native-entry/expected-source.json').read_text()) == entry
    fatal = json.loads((ROOT / 'compat/native-fatal/expected-source.json').read_text())
    fatal_patch = ROOT / 'patches/0035-netbsd-linux-fatal-wait.patch'
    assert hashlib.sha256(fatal_patch.read_bytes()).hexdigest() == fatal['patch_sha256']
    snapshot = scratch / 'verified-entry-source-chain'
    snapshot.mkdir()
    actual_sha = {}
    for rel in sorted(set(fatal['files']) | set(entry['files'])):
        source = stage / rel
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        expected = (entry['files'][rel]['after_sha256'] if rel in entry['files']
                    else fatal['files'][rel]['after'])
        assert digest == expected, rel
        actual_sha[rel] = digest
        target = snapshot / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    subprocess.run(['git', '-C', str(snapshot), 'apply', '--reverse', str(patch)], check=True)
    for rel, content in before.items():
        assert (snapshot / rel).read_bytes() == content.encode(), rel
    for rel, row in fatal['files'].items():
        assert hashlib.sha256((snapshot / rel).read_bytes()).hexdigest() == row['after'], rel
    print('ACTUAL0037_REVERSED_TO_BYTE_EXACT0035_SOURCE_CHAIN', flush=True)
    return snapshot, {'entry_contract': entry, 'fatal_contract': fatal,
                      'actual_source_sha256': actual_sha,
                      'reverse0037_to0035': 'PASSED'}
