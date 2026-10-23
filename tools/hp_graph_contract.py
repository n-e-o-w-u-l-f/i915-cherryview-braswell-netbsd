#!/usr/bin/env python3
"""Pure frozen-source graph admission; not configured-object or build proof.

Only the reviewed repository evidence is read. No host, native filesystem,
compiler or subprocess operation is performed by this contract.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
EXPECTED_COUNTS = {"i915": 323, "drm": 66, "display": 8, "ttm": 13}
REFERENCE = (Path(__file__).resolve().parents[1] /
             "docs/evidence/HP_FULL_GRAPH_API_20261005.json")
# SHA256 of the reviewed Git blob. Only CRLF -> LF normalization is allowed
# for local checkouts; reference changes require an explicit source review.
REFERENCE_SHA256 = "79cc1e9bd6ceee1efbc289b091eb98706df4c496b31408925cbe1f3085db6c3b"


def _check_pins(linux_pin, netbsd_pin, label):
    if linux_pin != LINUX_PIN or netbsd_pin != NETBSD_PIN:
        raise ValueError(label + ": frozen Linux/NetBSD reference pins differ")


def relative_c_path(name):
    """Accept only canonical, relative, token-safe POSIX C source names."""
    if not isinstance(name, str) or not name:
        raise ValueError("selected source must be a nonempty string")
    path = PurePosixPath(name)
    if (path.is_absolute() or path.as_posix() != name or
            any(part in ("", ".", "..") for part in name.split("/")) or
            any(char.isspace() for char in name) or
            any(not char.isascii() or not (char.isalnum() or char in "_./+-")
                for char in name) or
            any(char in name for char in ("\\", ":", "\x00"))):
        raise ValueError("unsafe relative source path: " + repr(name))
    if path.suffix != ".c":
        raise ValueError("selected source is not a C unit: " + name)
    return path


def _validated_groups(groups, label):
    if not isinstance(groups, dict) or set(groups) != set(EXPECTED_COUNTS):
        raise ValueError(label + ": exact i915/DRM/display/TTM groups required")
    objects = set()
    for group, count in EXPECTED_COUNTS.items():
        names = groups[group]
        if not isinstance(names, list):
            raise ValueError(label + ": source list required: " + group)
        paths = [relative_c_path(name) for name in names]
        if len(names) != len(set(names)):
            raise ValueError(label + ": duplicate selected source: " + group)
        if len(names) != count:
            raise ValueError(label + ": frozen source count differs: " + group)
        for path in paths:
            obj = path.stem + ".o"
            if obj in objects:
                raise ValueError(label + ": native object basename collision: " + obj)
            objects.add(obj)
    return groups


def _reference_groups():
    raw = REFERENCE.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError("reviewed frozen graph evidence SHA256 differs")
    document = json.loads(raw)
    if not isinstance(document, dict) or not isinstance(document.get("graph"), dict):
        raise ValueError("frozen graph evidence must contain a graph object")
    graph = document["graph"]
    for owner in (document, graph):
        _check_pins(owner.get("linux_pin"), owner.get("netbsd_pin"), "evidence")
    return _validated_groups(graph.get("units"), "evidence")


def selected_units(groups, *, linux_pin, netbsd_pin):
    """Return deterministic source/object rows after exact pinned admission.

    Membership is independent of input order. This does not establish what
    config(5)/make selected, input content, compilation, linking or runtime.
    """
    _check_pins(linux_pin, netbsd_pin, "stage")
    expected = _reference_groups()
    _validated_groups(groups, "stage")
    rows = []
    for group in EXPECTED_COUNTS:
        if set(groups[group]) != set(expected[group]):
            raise ValueError("frozen selected source set differs: " + group)
        prefix = "external/bsd/drm2/dist/drm/" + ("" if group == "drm" else group + "/")
        rows.extend({"group": group, "source": prefix + name,
                     "object": PurePosixPath(name).stem + ".o"}
                    for name in groups[group])
    return sorted(rows, key=lambda row: row["source"])
