#!/usr/bin/env python3
"""Reject corrupt pin/matrix inputs to the exhaustive 300-row precondition audit.

Do not confuse this with 300 semantically verified i915 modules: it
validates the reproducibility and fail-closed coverage evidence only.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def must(cond, reason):
    if not cond:
        raise AssertionError("I915_300_PRECONDITION_REGRESSION: " + reason)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--linux-reference", type=Path, required=True)
    p.add_argument("--netbsd-reference", type=Path, required=True)
    p.add_argument("--blob-crosswalk", type=Path, required=True)
    p.add_argument("--netbsd-root", type=Path, required=True)
    p.add_argument("--linux-snapshot", type=Path, required=True)
    args = p.parse_args()
    auditor = Path(__file__).resolve().parents[1] / "tools/audit_i915_300_semantic_preconditions.py"
    original = [json.loads(f.read_text()) for f in (
        args.linux_reference, args.netbsd_reference, args.blob_crosswalk
    )]
    with tempfile.TemporaryDirectory(prefix="i915-300-failclosed-") as tmp:
        d = Path(tmp)
        files = [d / x for x in ("linux.json", "netbsd.json", "crosswalk.json")]
        output = d / "report.json"

        def run(values):
            for file, value in zip(files, values):
                file.write_text(json.dumps(value) + "\n")
            return subprocess.run([
                sys.executable, "-B", str(auditor),
                "--linux-reference", str(files[0]),
                "--netbsd-reference", str(files[1]),
                "--blob-crosswalk", str(files[2]),
                "--netbsd-root", str(args.netbsd_root),
                "--linux-snapshot", str(args.linux_snapshot),
                "--out", str(output),
            ], text=True, capture_output=True, timeout=30)

        baseline = run(original)
        must(baseline.returncode == 0, baseline.stderr[-600:])
        j = json.loads(output.read_text())
        must(len(j["rows"]) == 300 and j["total"] == 300,
             "exact active semantic count")
        must(j["semantics_verified_and_accepted"] == 0 and
             all(row["semantic_state"] == "UNREVIEWED"
                 for row in j["rows"]), "false semantic pass")
        must(j["native_c_files_indexed"] == 264 and
             j["netbsd_code_blobs_frozen_unchanged"] == 483 and
             len(j["netbsd_known_local_modified_blobs"]) == 6,
             "NetBSD source identity accounting drift")
        must(j["linux_originals_content_verified"] == 7,
             "missing Linux-source limitations")
        print("I915_300_ALL_OWNER_PRECONDITIONS_SOURCE_FROZEN_CHECK_PASS")

        def check_mutation(label, target_index, mutator):
            edited = [json.loads(json.dumps(o)) for o in original]
            mutator(edited[target_index])
            result = run(edited)
            must(result.returncode != 0 and
                 "I915_300_SOURCE_GATE_REFUSED" in result.stderr,
                 label + " was not refused " + result.stderr[-330:])
            print("I915_300_NEGATIVE_" + label + "_REFUSED")

        check_mutation("MISSING_ROW", 0,
                       lambda a: a["rows"].pop())
        check_mutation("CROSSWALK_REORDER", 2,
                       lambda a: a["rows"].reverse())
        check_mutation("NETBSD_CODE_BLOB_TAMPER", 1,
                       lambda a: a["files"][0].__setitem__("blob", "0" * 40))
        check_mutation("LINUX_PIN_TAMPER", 0,
                       lambda a: a.__setitem__("linux_pin", "0" * 40))
        check_mutation("LINUX_BLOB_TAMPER", 0,
                       lambda a: next(r for r in a["rows"]
                           if r["linux_source"] == "display/intel_backlight.c")
                           .__setitem__("linux_blob", "0" * 40))
        print("I915_300_FIVE_PIN_IDENTITY_NEGATIVE_MUTATIONS_REFUSED")
        print("LIMIT: identity and owner evidence only, NOT semantic hardware parity")


if __name__ == "__main__":
    main()
