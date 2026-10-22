#!/usr/bin/env python3
"""0078 replay of a strictly userland C backlight contract model; no NetBSD or HP."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MODEL = Path(__file__).with_name("0078_backlight_class_contract_model.c")
EXPECTED_SHA256 = "fab5e15866f0646782e2871ff42d86a0488e3d7018705f8fe514675563ecc747"
MARKER = re.compile(
    r"HP_I915_0078_MODEL_PASS checks=(\d+) allocations=(\d+) "
    r"releases=(\d+) registrations=(\d+) unregistrations=(\d+) "
    r"live=(\d+) gpu=(\d+)$"
)


def check_run(command, *, environment=None):
    run = subprocess.run(command, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, timeout=30,
                         env=environment, check=False)
    if run.returncode:
        raise RuntimeError(
            f"failure exit={run.returncode} command={command!r}"
            f"\nstdout:\n{run.stdout}\nstderr:\n{run.stderr}")
    return run


def run_tests(verbose=False, sanitizer=True):
    payload = MODEL.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"source SHA256 mismatch {digest}")
    compilers = [cmd for cmd in ("gcc", "clang") if shutil.which(cmd)]
    if len(compilers) != 2:
        raise RuntimeError("Both gcc and clang required for independent compilation")
    results = []
    with tempfile.TemporaryDirectory(prefix="hp-i915-0078-") as temp:
        for cc in compilers:
            executable = str(Path(temp) / f"0078-{cc}")
            args = [cc, "-std=c11", "-O2", "-Wall", "-Wextra",
                    "-Wpedantic", "-Werror", "-Wconversion", "-Wshadow",
                    "-o", executable, str(MODEL)]
            if verbose:
                args.insert(1, "-v")
            compilation = check_run(args)
            if verbose:
                print(f"COMPILER_VERBOSE_{cc}:\n{compilation.stderr}")
            for iteration in (1, 2):
                execution = check_run([executable])
                match = MARKER.fullmatch(execution.stdout.strip())
                if not match:
                    raise RuntimeError(f"invalid marker {execution.stdout!r}")
                values = list(map(int, match.groups()))
                if values != [41, 3, 3, 3, 3, 0, 0]:
                    raise RuntimeError(f"bad counters {values!r}")
                results.append({"compiler": cc, "iteration": iteration,
                                "marker": execution.stdout.strip()})
        if sanitizer:
            executable = str(Path(temp) / "0078-sanitizer")
            args = ["gcc", "-std=c11", "-O1", "-g",
                    "-fsanitize=address,undefined",
                    "-fno-omit-frame-pointer", "-Wall", "-Wextra",
                    "-Wpedantic", "-Werror", "-o", executable,
                    str(MODEL)]
            if verbose:
                args.insert(1, "-v")
            compilation = check_run(args)
            if verbose:
                print(f"SANITIZER_COMPILER_VERBOSE:\n{compilation.stderr}")
            environ = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1")
            execution = check_run([executable], environment=environ)
            match = MARKER.fullmatch(execution.stdout.strip())
            if match is None or list(map(int, match.groups())) != [41, 3, 3, 3, 3, 0, 0]:
                raise RuntimeError(f"bad sanitizer marker: {execution.stdout!r}")
            results.append({"compiler": "gcc+ASAN+UBSAN", "iteration": 1,
                            "marker": execution.stdout.strip()})
    return {"status": "PASS", "source_sha256": digest, "runs": results,
            "host": "isolated userland, not NetBSD or HP", "hardware": "NOT_RUN",
            "netbsd_kernel_compile": "NOT_RUN", "qemu": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true",
                        help="include compiler -v diagnostic logs")
    parser.add_argument("--skip-sanitizer", action="store_true")
    args = parser.parse_args()
    result = run_tests(verbose=args.verbose,
                       sanitizer=not args.skip_sanitizer)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
