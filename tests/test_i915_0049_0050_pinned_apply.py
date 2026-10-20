#!/usr/bin/env python3
"""Read-only NetBSD pin + staged i915 patch applicability check (not a build)."""
import argparse
import hashlib
from pathlib import Path
import subprocess

NETBSD_PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
SOURCES = {
    'sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c': '9798385b02f247c08db9b16624d5ddc9d11a8ca5',
    'sys/external/bsd/drm2/dist/drm/i915/i915_drv.c': 'bf64ff40059fc38188f6f3d7b55bef9793abeb57',
    'sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c': '2cbe50d346b20bb9a23382993c361e7db94b6e9d',
}
PATCHES = {
    '0049-netbsd-i915-attach-probe-error-owner-reset.patch': '126334e9da25a2398e99530aa4cbaa7eaa20a455',
    '0050-netbsd-i915-drm-register-rollback-v2.patch': 'd8cf75f69bccc078bc457dcfdfc1d90e79e6caa6',
    '0009-netbsd-opregion-optional-asle-cleanup.patch': 'b257d451560584a86c6f092dcde6b0b69b0e33c8',
}

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def run(*argv: str, cwd: Path) -> bytes:
    return subprocess.check_output(argv, cwd=cwd, stderr=subprocess.STDOUT)


def check(src: Path, candidates: Path) -> None:
    assert run('git', 'rev-parse', 'HEAD', cwd=src).decode().strip() == NETBSD_PIN, 'NetBSD revision mismatch'
    for relative, expected in SOURCES.items():
        data = (src / relative).read_bytes()
        assert git_blob(data) == expected, f'wrong pinned source: {relative}'
        assert data == run('git', 'show', 'HEAD:' + relative, cwd=src), f'dirty source: {relative}'
    for filename, expected in PATCHES.items():
        data = (candidates / filename).read_bytes()
        assert git_blob(data) == expected, f'changed candidate: {filename}'
        run('git', 'apply', '--check', str((candidates / filename).resolve()), cwd=src)
        print(f'PINNED_PATCH_APPLIES: {filename}: PASS')
    print('HP_I915_0049_0050_0009_PINNED_APPLY_PASS; NATIVE_KERNEL_NOT_RUN')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--netbsd-tree', type=Path)
    ap.add_argument('--candidates', type=Path)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        assert git_blob(b'hello') == 'b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0'
        assert len(PATCHES) == 3 and len(SOURCES) == 3
        print('HP_I915_0049_0050_PIN_VALIDATOR_SELF_TEST_PASS_2_2')
        return
    if a.netbsd_tree is None or a.candidates is None:
        ap.error('require --netbsd-tree and --candidates, or --self-test')
    check(a.netbsd_tree, a.candidates)

if __name__ == '__main__':
    main()
