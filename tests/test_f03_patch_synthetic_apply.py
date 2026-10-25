#!/usr/bin/env python3
"""F03 real git apply --check on generated SYNTHETIC hunk preimages ONLY.

This verifies the exact committed candidate patch's diff framing, counts and
Git applicability without rewriting any NetBSD file. It does NOT mean that
the actual four pinned NetBSD source blobs apply, compile, or work at runtime.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/candidates/netbsd-11-drm-fileops-bridge-20261025.patch"
PATCH_BLOB = "9c99357d2ee3ce21267ede4e2caed033e0906694"
PATHS = (
    "sys/sys/file.h",
    "sys/sys/filedesc.h",
    "sys/kern/kern_descrip.c",
    "sys/kern/sys_generic.c",
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=30)


def check() -> None:
    if not PATCH.is_file() or PATCH.is_symlink():
        raise ValueError("F03 candidate patch missing or symlink")
    hashed = run("git", "hash-object", str(PATCH))
    if hashed.returncode != 0 or hashed.stdout.strip() != PATCH_BLOB:
        raise ValueError("F03 patch has drifted from its accepted Git blob")

    sections = [
        c for c in re.split(r"(?=^diff --git a/)", PATCH.read_text(), flags=re.M)
        if c.strip()
    ]
    if len(sections) != len(PATHS):
        raise ValueError("expected exactly four diff file sections")

    with TemporaryDirectory(prefix="f03-synthetic-git-apply-") as temp:
        root = Path(temp)
        init = run("git", "-C", str(root), "init", "-q")
        if init.returncode:
            raise RuntimeError(init.stderr)
        hunk_count = 0
        for expected, section in zip(PATHS, sections):
            lines = section.splitlines(keepends=True)
            header = re.match(r"diff --git a/([^ ]+) b/([^\n]+)", lines[0])
            if not header or header.group(1) != expected or header.group(2) != expected:
                raise ValueError("unexpected target path")
            if lines[1] != "--- a/" + expected + "\n" or lines[2] != "+++ b/" + expected + "\n":
                raise ValueError("unexpected hunk path headers")
            preimage: dict[int, str] = {}
            i = 3
            while i < len(lines):
                match = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", lines[i])
                if not match:
                    raise ValueError("invalid hunk header: " + repr(lines[i]))
                start, old_count, _, new_count = map(int, match.groups())
                i += 1
                before = after = 0
                while i < len(lines) and not lines[i].startswith("@@ "):
                    row = lines[i]
                    i += 1
                    if row[0] not in " +-":
                        raise ValueError("invalid diff line")
                    if row[0] != "+":
                        line_number = start + before
                        if line_number in preimage and preimage[line_number] != row[1:]:
                            raise ValueError("overlapping hunk contexts disagree")
                        preimage[line_number] = row[1:]
                        before += 1
                    if row[0] != "-":
                        after += 1
                if before != old_count or after != new_count:
                    raise ValueError("hunk line count mismatch")
                hunk_count += 1
            if not preimage:
                raise ValueError("empty hunk")
            maxline = max(preimage) + 10
            text = "".join(
                preimage.get(n, f"/* SYNTHETIC only; filler line {n} */\n")
                for n in range(1, maxline + 1)
            )
            target = root / expected
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)

        if hunk_count != 6:
            raise ValueError("expected exactly six hunks")
        success = run("git", "-C", str(root), "apply", "--check",
                      "--whitespace=error", str(PATCH))
        if success.returncode:
            raise AssertionError("synthetic git apply rejected patch: " + success.stderr)
        counts = run("git", "-C", str(root), "apply", "--numstat", str(PATCH))
        expected = ["7\t2\tsys/sys/file.h", "4\t2\tsys/sys/filedesc.h",
                    "24\t4\tsys/kern/kern_descrip.c",
                    "23\t13\tsys/kern/sys_generic.c"]
        if counts.returncode or counts.stdout.splitlines() != expected:
            raise AssertionError("unexpected patch scope or insert/delete counts")

        damaged = root / PATHS[0]
        text = damaged.read_text()
        if text.count("struct uvm_object;") != 1:
            raise AssertionError("source fixture missing anchor")
        damaged.write_text(text.replace("struct uvm_object;",
                                        "struct different_object;", 1))
        rejected = run("git", "-C", str(root), "apply", "--check",
                       "--whitespace=error", str(PATCH))
        if rejected.returncode == 0 or "patch does not apply" not in rejected.stderr:
            raise AssertionError("negative damaged-context check was not rejected")
        print("F03_SYNTHETIC_GIT_APPLY_PASS 4_FILES_6_HUNKS")
        print("F03_CORRUPT_CONTEXT_REJECTED")
        print("LIMITATION: Not a pinned NetBSD full-source git apply or kernel build")


if __name__ == "__main__":
    check()
