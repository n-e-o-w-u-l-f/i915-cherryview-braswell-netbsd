#!/usr/bin/env python3
"""Strict offline verifier for the pinned NetBSD 11 daily 0066 root sets.

Does not download, extract, mount, execute or write anything. A manifest-only
match is not sufficient: success requires hashing all three archive files.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

SNAPSHOT = "netbsd-11/20261021045729Z/amd64/binary/sets"
EXPECTED = {
    "rescue.tar.xz": (3863836, "ddaa11181edc1a1cc33c9c91c7fc3cd7b90072a1e021436f461a780830a01e5d43c86fe2226ea47e51c41ea9ffd6f24df6ff452eea6e4d2c2a12f7e482b9c8ef"),
    "etc.tar.xz": (510496, "afcc9af52a23095d2e3b75d1be1c0f5ac3dd1800a6255944f6a2ec0759329b2f44174d0d9d99d93203647e6658306fedec02002bf43e608139cfdc92df7d1830"),
    "base.tar.xz": (44593416, "be041b828f959f4d5d2b06685d9dd8aabee17958221f0174b68877719e87d3740f6e17b6d8060d99dacc94107f9767069caafe453ca50679b7bffae5e7e67a3b"),
}
SHA_LINE = re.compile(r"SHA512 \(([^()]+)\) = ([a-f0-9]{128})\Z")


def parse_manifest(text):
    records = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = SHA_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"malformed manifest line {number}")
        name, digest = match.groups()
        if name in records:
            raise ValueError(f"duplicate manifest entry {name!r}")
        records[name] = digest
    return records


def audit(sets_dir, manifest, expected=EXPECTED):
    records = parse_manifest(manifest)
    results = {}
    for name, (expected_size, expected_hash) in expected.items():
        row = {"manifest_matches_reference": records.get(name) == expected_hash,
               "file_exists_and_regular": False,
               "byte_size_matches_reference": False,
               "file_sha512_matches_manifest": False}
        path = sets_dir / name
        try:
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("not a regular file (symlink refused)")
            row["file_exists_and_regular"] = True
            row["byte_size_matches_reference"] = path.stat().st_size == expected_size
            digest = hashlib.sha512()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            row["archive_bytes_read_complete"] = True
            row["file_sha512_matches_manifest"] = (
                digest.hexdigest() == records.get(name))
        except (OSError, ValueError) as exc:
            row["file_error"] = str(exc)
        results[name] = row
    passed = all(all(value for key, value in result.items() if key != "file_error")
                 for result in results.values())
    return {"snapshot": SNAPSHOT, "status": "PASS" if passed else "FAIL",
            "hash_algorithm": "SHA512",
            "actual_archive_bytes_hashed": all(r.get("archive_bytes_read_complete", False)
                                              for r in results.values()),
            "files": results}


def self_test():
    with tempfile.TemporaryDirectory(prefix="i915-0075-offline-test-") as directory:
        root = Path(directory)
        payloads = {"rescue.tar.xz": b"synthetic rescue data",
                    "etc.tar.xz": b"synthetic etc data",
                    "base.tar.xz": b"synthetic base data"}
        expected = {}
        for name, payload in payloads.items():
            (root / name).write_bytes(payload)
            expected[name] = (len(payload), hashlib.sha512(payload).hexdigest())
        manifest = "\n".join(f"SHA512 ({name}) = {digest}"
                             for name, (_, digest) in expected.items()) + "\n"
        assert audit(root, manifest, expected)["status"] == "PASS"
        (root / "etc.tar.xz").write_bytes(b"tampered etc")
        assert audit(root, manifest, expected)["status"] == "FAIL"
        (root / "etc.tar.xz").write_bytes(payloads["etc.tar.xz"])
        try:
            parse_manifest(manifest + manifest)
            raise AssertionError("duplicate manifest entry accepted")
        except ValueError:
            pass
        try:
            parse_manifest("SHA512 (../escape) = not-a-digest\n")
            raise AssertionError("malformed SHA512 entry accepted")
        except ValueError:
            pass
        (root / "base.tar.xz").unlink()
        (root / "base.tar.xz").symlink_to(root / "rescue.tar.xz")
        assert audit(root, manifest, expected)["status"] == "FAIL"
        (root / "base.tar.xz").unlink()
        assert audit(root, manifest, expected)["status"] == "FAIL"
        forged = manifest.replace(expected["rescue.tar.xz"][1], "0" * 128)
        assert audit(root, forged, expected)["status"] == "FAIL"
    return {"self_test": "PASS", "cases": 7,
            "note": "synthetic fixtures only; NOT actual NetBSD archive verification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--self-test", action="store_true")
    opts = parser.parse_args()
    if opts.self_test:
        result = self_test()
    else:
        if not opts.sets_dir or not opts.manifest:
            parser.error("--sets-dir and --manifest required")
        if opts.manifest.name != "SHA512":
            parser.error("manifest filename must be SHA512")
        try:
            result = audit(opts.sets_dir, opts.manifest.read_text(encoding="ascii"))
        except (OSError, ValueError, UnicodeError) as exc:
            result = {"snapshot": SNAPSHOT, "status": "ERROR", "reason": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("status", result.get("self_test")) != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
