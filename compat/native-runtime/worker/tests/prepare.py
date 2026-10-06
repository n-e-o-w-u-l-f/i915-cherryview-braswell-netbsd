#!/usr/bin/env python3
"""Compile adapters around exactly the generated native production functions."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
for original, target in [(ROOT / "include/linux/kthread.h", ROOT / "tests/test_kthread_header.h"),
                         (ROOT / "linux_kthread.c", ROOT / "tests/test_kthread_impl.inc")]:
    data = original.read_text()
    # Replace only kernel include dependencies; leave every function unmodified.
    target.write_text("\n".join(l for l in data.splitlines() if not l.startswith("#include ")) + "\n")
