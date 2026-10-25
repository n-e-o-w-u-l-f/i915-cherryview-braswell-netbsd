#!/usr/bin/env python3
"""F09: Git-blob-pinned F06 test against four ORIGINAL NetBSD file bytes.

Run only on a separate source staging directory. The source is never changed:
Git dry-run and actual patch application happen on verified temporary copies.
No NetBSD native kernel compile or full checkout identity is asserted.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

PINNED_NETBSD = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
PATCH_BLOB = "2fca0c1dc147e595fe2e83c3f7e57f0306773199"
SOURCE_BLOBS = {
    "sys/sys/file.h": "4938650485c3d6acf892a846b2f330d1fc53c424",
    "sys/sys/filedesc.h": "e94f711b756ef0a6e01a4f682e8ba70928058ea7",
    "sys/kern/kern_descrip.c": "56f87d84b4f3a077710f08f0bfd14708983a39a6",
    "sys/kern/sys_generic.c": "0894053933da09868b6ff80d34e00ddfca7cf96b",
}
RESULT_BLOBS = {
    "sys/sys/file.h": "18f8eaa3da748430dc74183a3c2e30e9290cb0a3",
    "sys/sys/filedesc.h": "2dc956d195548a2a8878049689ff3a07d281c5c6",
    "sys/kern/kern_descrip.c": "4e6821ccc78c4076d9b877ede1a6bd37bf631561",
    "sys/kern/sys_generic.c": "e890db33c17cd8321d56e1f849b6ca758920aa28",
}
DEFAULT_PATCH = (Path(__file__).resolve().parents[1] / "patches" / "candidates"
                 / "netbsd-11-drm-fileops-bridge-copyout-owned-highbit-guard-20261025.patch")


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def run(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                       check=False, timeout=45)
    if r.returncode:
        raise RuntimeError(f"{args[0]} exit {r.returncode}: "
                           + (r.stderr or r.stdout).strip()[:700])
    return r.stdout.strip()


def verify_four_files(source_root: Path, patch_path: Path,
                      before: dict[str, str] = SOURCE_BLOBS,
                      after: dict[str, str] = RESULT_BLOBS,
                      patch_sha: str = PATCH_BLOB) -> dict[str, str]:
    if not patch_path.is_file() or patch_path.is_symlink():
        raise ValueError("missing or symlinked F06 candidate patch")
    patch = patch_path.read_bytes()
    if git_blob(patch) != patch_sha:
        raise ValueError("patch Git blob mismatch")
    if set(before) != set(after) or not before:
        raise ValueError("pre/post manifests must cover identical nonempty paths")
    if not patch.endswith(b"\n") or patch.startswith(b"#"):
        raise ValueError("expected unmodified unified diff")
    text = patch.decode("utf-8")
    sections = [line.removeprefix("diff --git a/").split(" b/", 1)[0]
                for line in text.splitlines() if line.startswith("diff --git a/")]
    if sections != list(before):
        raise ValueError("unexpected patch file list or order")
    if len(before) == 4 and text.count("@@ -") != 6:
        raise ValueError("F06 must contain six hunks")

    with tempfile.TemporaryDirectory(prefix="f09-original-four-git-") as temp:
        stage = Path(temp)
        for relative, expected in before.items():
            if (Path(relative).is_absolute() or ".." in Path(relative).parts
                    or not relative.startswith("sys/")):
                raise ValueError("unsafe manifest path")
            src = source_root / relative
            if not src.is_file() or src.is_symlink():
                raise ValueError("missing/linked original source: " + relative)
            data = src.read_bytes()
            if git_blob(data) != expected:
                raise ValueError("original NetBSD Git blob mismatch: " + relative)
            dst = stage / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)

        run("git", "apply", "--check", "--whitespace=error", str(patch_path), cwd=stage)
        stats = run("git", "apply", "--numstat", str(patch_path), cwd=stage)
        if sorted(x.split("\t")[-1] for x in stats.splitlines()) != sorted(before):
            raise ValueError("unexpected Git patch scope")
        run("git", "apply", "--whitespace=error", str(patch_path), cwd=stage)
        calculated = {relative: git_blob((stage / relative).read_bytes())
                      for relative in before}
        if calculated != after:
            raise ValueError("F06 patched output Git blob mismatch: " + str(calculated))
    return calculated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, default=DEFAULT_PATCH)
    args = parser.parse_args()
    try:
        results = verify_four_files(args.source_root.resolve(), args.patch.resolve())
    except (OSError, ValueError, RuntimeError) as err:
        print("F09_ORIGINAL_GIT_GATE_BLOCKED:", err)
        return 1
    print("F09_ORIGINAL_FOUR_SOURCE_GIT_APPLY_PASS")
    for file, sha in results.items():
        print(file, sha)
    print("LIMIT: no NetBSD full-tree HEAD, header compilation or kernel link validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
