#!/usr/bin/env python3
"""Resolve missing Linux header inputs without replacing native OS adapters.

The ledger distinguishes imported source from existing native adapters and
unresolved generated/external inputs. Importing a header does not close its ABI
or implementation contract. Every frozen input byte is verified against the pin before owned identifier translation.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import socket
import subprocess
from collections import deque

from materialize_linux_i915 import LINUX_PIN
from namespace_linux_compiler_math import bindings, translate

INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"\n]+)[>"]', re.M)

def populate(linux, tree, ledger, prior=None):
    head = subprocess.check_output(["git", "-C", str(linux), "rev-parse", "HEAD"], text=True).strip()
    if head != LINUX_PIN:
        raise RuntimeError("unexpected Linux reference revision")
    entries = subprocess.check_output(["git", "-C", str(linux), "ls-tree", "-rz", "HEAD",
        "--", "include", "arch/x86/include/asm", "arch/x86/include/uapi/asm"]).split(b"\0")
    blobs = {}
    for entry in entries:
        if not entry: continue
        metadata, path = entry.split(b"\t", 1)
        mode, kind, sha = metadata.split()
        if kind == b"blob" and mode in (b"100644", b"100755"):
            blobs[path.decode()] = sha.decode()
    generic = {}
    for path, keyword in [("arch/x86/include/asm/Kbuild", "generic-y"),
            ("include/asm-generic/Kbuild", "mandatory-y"),
            ("include/uapi/asm-generic/Kbuild", "mandatory-y")]:
        text = subprocess.check_output(["git", "-C", str(linux), "show", "HEAD:" + path], text=True)
        for value in re.findall(r"^" + keyword + r"\s*\+=\s*(.+)$", text, re.M):
            for name in value.split():
                source = ("include/uapi/asm-generic/" if "/uapi/" in path else "include/asm-generic/") + name
                if source in blobs: generic["asm/" + name] = (source, path + ":" + keyword)
    mapping = bindings(linux)
    previous = {row["path"]: row for row in prior["rows"]
        if row["state"] in {"IMPORTED_API_UNREVIEWED", "IMPORTED_API_TRANSLATED_UNREVIEWED"}} if prior else {}
    roots = [tree / "sys/external/bsd/common/include", tree / "sys/external/bsd/drm2/include",
             tree / "sys/external/bsd/drm2/dist/include"]
    reference = tree.parent / "full-scope-audit/linux-stage-verified/PORT-MANIFEST.json"
    manifest = json.loads(reference.read_text())
    if manifest.get("linux_pin") != LINUX_PIN or not manifest.get("linux_head_verified"):
        raise RuntimeError("missing verified source-selection manifest")
    seeds = []
    for entry in manifest["files"]:
        rel = entry["path"]
        if PurePosixPath(rel).suffix not in (".c", ".h"): continue
        rel = rel.removeprefix("drivers/gpu/") if rel.startswith("drivers/gpu/") else rel
        seeds.append(tree / "sys/external/bsd/drm2/dist" / rel)
    queue = deque(seeds)
    # Reach existing native headers too: they may themselves need new inputs.
    scanned, seen, rows = set(), set(), []
    while queue:
        path = queue.popleft()
        if path in scanned: continue
        scanned.add(path)
        for name in INCLUDE.findall(path.read_text(errors="replace")):
            if name in seen: continue
            first = name.partition("/")[0]
            if first not in {"linux", "asm", "asm-generic", "uapi", "drm", "kunit", "video", "dt-bindings"} and "include/" + name not in blobs:
                continue
            local = path.parent / name
            if local.is_file(): queue.append(local); continue
            seen.add(name)
            native = next((root / name for root in roots if (root / name).is_file()), None)
            if native is not None:
                relative = str(native.relative_to(tree))
                sha = hashlib.sha256(native.read_bytes()).hexdigest()
                if relative in previous:
                    row = previous[relative]
                    if row["sha256"] != sha: raise RuntimeError("import changed; reconcile adapter provenance: " + relative)
                    rows.append(row)
                else:
                    rows.append({"include": name, "state": "EXISTING_ADAPTER_UNREVIEWED", "path": relative, "sha256": sha})
                queue.append(native); continue
            candidates = ["include/" + name, "include/uapi/" + name]
            if first == "asm":
                candidates = ["arch/x86/include/" + name, "arch/x86/include/uapi/" + name]
                # Generic fallback must be explicitly selected by the frozen
                # architecture/mandatory Kbuild rules, never guessed.
                if name in generic: candidates.append(generic[name][0])
            upstream = next((candidate for candidate in candidates if candidate in blobs), None)
            if upstream is None:
                rows.append({"include": name, "state": "UNRESOLVED_GENERATED_OR_EXTERNAL",
                    "requested_by": str(path.relative_to(tree))}); continue
            if ".." in PurePosixPath(name).parts:
                raise RuntimeError("unsafe include path: " + name)
            data = subprocess.check_output(["git", "-C", str(linux), "cat-file", "blob", blobs[upstream]])
            actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if actual != blobs[upstream]:
                raise RuntimeError("corrupt frozen header input: " + upstream)
            target = roots[-1] / name
            if tree not in target.resolve().parents:
                raise RuntimeError("include output escapes isolated stage: " + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): raise RuntimeError("source changed during import: " + name)
            frozen_hash = hashlib.sha256(data).hexdigest()
            transformed = translate(data.decode(), mapping).encode()
            changed = transformed != data
            data = transformed
            target.write_bytes(data)
            row = {"include": name, "state": "IMPORTED_API_TRANSLATED_UNREVIEWED" if changed else "IMPORTED_API_UNREVIEWED", "linux_path": upstream,
                "linux_blob": actual, "sha256": hashlib.sha256(data).hexdigest(),
                "path": str(target.relative_to(tree))}
            if changed: row["frozen_sha256"] = frozen_hash
            if name in generic and upstream == generic[name][0]: row["selected_by"] = generic[name][1]
            rows.append(row)
            queue.append(target)
    report = {"linux_pin": LINUX_PIN, "headers_scanned": len(scanned), "rows": sorted(rows, key=lambda row: row["include"]),
        "warning": "source import only: semantics, OS APIs and generated inputs require implementation and validation"}
    ledger.write_text(json.dumps(report, indent=2) + "\n")
    return report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--linux-tree", type=Path, required=True)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--prior-ledger", type=Path)
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("native integration is restricted to HP/NetBSD")
    tree = a.netbsd_tree.resolve(strict=True)
    if tree != Path("/root/hp-driver-port-20261005/netbsd-full-linux") or a.ledger.exists():
        p.error("expected isolated full graph and a new ledger; preserve existing work")
    prior = json.loads(a.prior_ledger.read_text()) if a.prior_ledger else None
    report = populate(a.linux_tree.resolve(strict=True), tree, a.ledger, prior)
    from collections import Counter
    print(json.dumps(dict(Counter(row["state"] for row in report["rows"]))))

if __name__ == "__main__":
    main()
