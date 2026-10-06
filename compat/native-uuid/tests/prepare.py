#!/usr/bin/env python3
"""Remove only native include dependencies for real-code HP userland adapters."""
from pathlib import Path
import importlib.util
import re

ROOT = Path(__file__).resolve().parents[1]
for source, output in [("include/linux/uuid.h", "tests/test_uuid_header.h"),
                       ("linux_uuid.c", "tests/test_uuid_impl.inc")]:
    text = (ROOT / source).read_text()
    text = re.sub(r"^#include[^\n]*\n", "", text, flags=re.M)
    (ROOT / output).write_text(text)

spec = importlib.util.spec_from_file_location("uuid_generate", ROOT / "generate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
probe = (ROOT / "tests/linux_namespace_probe.c").read_text()
(ROOT / "tests/translated_namespace_probe.c").write_text(module.translate(probe))
