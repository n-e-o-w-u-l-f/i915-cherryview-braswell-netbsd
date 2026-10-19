#!/usr/bin/env python3
"""Conservative NetBSD 11 IOSF/PUNIT+CPU QoS shim semantic gate.

This is an explicit BLOCKER test. It reports the exact no-op semantics
of pinned NetBSD compatibility headers. Passing its source-identity
assertions NEVER means IOSF runtime parity with Linux was achieved.
No native HP compile, physical test or compiler invocation.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re

PINS = {
    "punit_header": "b72c89aed5d1e0ad258c0dd8a6561eafe6398089",
    "qos_header": "52d2df0db516eb5473d53a0b8c98ab7fb8d62690",
    "native_sideband": "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed",
    "linux_iosf": "1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758",
}
MBI_FUNCTIONS = (
    "iosf_mbi_punit_acquire",
    "iosf_mbi_punit_release",
    "iosf_mbi_assert_punit_acquired",
)
QOS_FUNCTIONS = (
    "pm_qos_add_request",
    "pm_qos_update_request",
    "pm_qos_remove_request",
)


def refuse(reason: str):
    raise ValueError("I915_IOSF_SHIM_CONTRACT_REFUSED: " + reason)


def gitblob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def body(text: str, name: str) -> str:
    match = re.search(r"\b" + re.escape(name) +
                      r"\s*\([^{};]{0,350}\)\s*\{", text)
    if not match:
        refuse("missing C declaration " + name)
    pos = text.index("{", match.start()) + 1
    end = text.find("}", pos)
    if end < 0:
        refuse("unclosed C body " + name)
    return text[pos:end]


def verify(mbi: str, qos: str, native: str, upstream: str) -> None:
    for name in MBI_FUNCTIONS:
        if body(mbi, name).strip():
            refuse("PUNIT function changed; re-evaluate implementation: " + name)
    for name in QOS_FUNCTIONS:
        if body(qos, name).strip():
            refuse("QoS function changed; re-evaluate implementation: " + name)
    if not re.search(r"struct\s+pm_qos_request\s*\{\s*char\s+dummy;\s*\};", qos):
        refuse("QoS request structure changed; reassess actual resources")
    for name in MBI_FUNCTIONS[:2]:
        if native.count(name + "();") != 1:
            refuse("native sideband PUNIT callsite changed " + name)
    for name in QOS_FUNCTIONS:
        if name not in native and name == "pm_qos_update_request":
            refuse("native Valleyview PUNIT QoS usage missing")
    for phrase in (
        "iosf_mbi_punit_acquire();", "iosf_mbi_punit_release();",
        "cpu_latency_qos_update_request(",
    ):
        if phrase not in upstream:
            refuse("Linux upstream PUNIT behavioral reference changed " + phrase)
    if not re.search(r"if\s*\(IS_VALLEYVIEW\(i915\)\)", native):
        refuse("native only-Valleyview QoS requirement changed")
    # Compatibility stubs do not implement cross-driver exclusion,
    # CPU latency enforcement or initialized Linux-style requests.
    # This is a source fact, not a claim that an HP-CHV hang occurred.


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-punit-header", required=True, type=Path)
    p.add_argument("--netbsd-qos-header", required=True, type=Path)
    p.add_argument("--netbsd-sideband", required=True, type=Path)
    p.add_argument("--linux-iosf", required=True, type=Path)
    x = p.parse_args()
    sources = {
        "punit_header": x.netbsd_punit_header,
        "qos_header": x.netbsd_qos_header,
        "native_sideband": x.netbsd_sideband,
        "linux_iosf": x.linux_iosf,
    }
    contents = {}
    for key, source in sources.items():
        raw = source.read_bytes()
        if gitblob(raw) != PINS[key]:
            refuse("not pinned source " + key)
        contents[key] = raw.decode("utf-8")
    verify(contents["punit_header"], contents["qos_header"],
           contents["native_sideband"], contents["linux_iosf"])

    # Mutation-control the warning itself: a future real
    # implementation MUST invalidate the known-no-op classification
    # and be separately reviewed for runtime safety, not auto-accepted.
    samples = (
        ("PUNIT_ACQUIRE", "punit_header", "iosf_mbi_punit_acquire"),
        ("PUNIT_RELEASE", "punit_header", "iosf_mbi_punit_release"),
        ("PUNIT_ASSERT", "punit_header", "iosf_mbi_assert_punit_acquired"),
        ("QOS_ADD", "qos_header", "pm_qos_add_request"),
        ("QOS_UPDATE", "qos_header", "pm_qos_update_request"),
        ("QOS_REMOVE", "qos_header", "pm_qos_remove_request"),
    )
    for marker, key, name in samples:
        original = contents[key]
        before = body(original, name)
        if before.strip():
            refuse("no-op expectation incorrect " + marker)
        call = name + "("
        at = original.index(call)
        start = original.index("{", at)
        modified = original[:start + 1] + "\n\t/* implemented; audit again */\n" + original[start + 1:]
        test = dict(contents)
        test[key] = modified
        try:
            verify(test["punit_header"], test["qos_header"],
                   test["native_sideband"], test["linux_iosf"])
        except ValueError as err:
            if "changed; re-evaluate implementation" not in str(err):
                raise
        else:
            raise AssertionError("unverified implementation accepted " + marker)
    print("I915_IOSF_SIX_NOOP_SHIM_BODIES_SOURCE_IDENTIFIED")
    print("I915_IOSF_SIX_SHIM_MUTATIONS_REQUIRE_REEVALUATION")
    print("STATUS: BLOCKED_RUNTIME_PARITY, not accepted even if this audit passes")


if __name__ == "__main__":
    main()
