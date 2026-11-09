#!/usr/bin/env python3
"""Select the F30 native FILE ABI probe chain and delegate to the guarded builder.

Default: recovered dispatch -> mmap-request -> early Linux DRM ioctl/F29 fix.
Two native core objects remain an ABI probe, not full kernel or driver acceptance.
The core builder retains all HP, clean-Git-pin, flags, toolchain and output guards.
"""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHAIN = tuple(
    (ROOT / 'compat/native-fileops' / (name + '.patch'),
     ROOT / 'compat/native-fileops' / (name + '.json'))
    for name in ('dispatch', 'mmap-request', 'early-drm-ioctl')
)
CORE_BUILDER = ROOT / 'tools/build_hp_native_core_patch.py'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netbsd-source', '--source', dest='source',
                        type=Path, required=True)
    parser.add_argument('--kernel-obj', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--source-archive', type=Path,
                        help='explicit fixed-pin archive used-source proof')
    args = parser.parse_args(argv)
    command = [sys.executable, '-B', str(CORE_BUILDER),
               '--source', str(args.source), '--kernel-obj', str(args.kernel_obj),
               '--output', str(args.output), '--toolchain', str(args.toolchain)]
    if args.source_archive is not None:
        command.extend(('--source-archive', str(args.source_archive)))
    for patch, contract in DEFAULT_CHAIN:
        command.extend(('--patch', str(patch), '--contract', str(contract)))
    return subprocess.run(command, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
