#!/usr/bin/env python3
"""Frozen NetBSD i915 DP AUX payload boundary regression, candidate 0043.

Applies the actual candidate patch to a scratch copy of a pinned NetBSD file;
inspects the real patched C function; rejects five dangerous source mutants;
models 64-bit size_t extremes; reverses byte-exactly. This is a SOURCE test,
not kernel compilation or live HP hardware acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

NETBSD_SHA = "1dd8858b2d331906190258c8602af55966ff986c"
LINUX_SHA = "3cb07b0a901cff7291eca9479f24128989d6c0e7"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
MAX_SIZE_T = 2**64 - 1


def gitblob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError("I915_DP_AUX_BOUNDS_REFUSED: " + reason)


def function(code: str) -> str:
    found = re.search(
        r"static\s+ssize_t\s+intel_dp_aux_transfer\s*\("
        r"struct drm_dp_aux \*aux,\s*struct drm_dp_aux_msg \*msg\)"
        r"\s*\{", code
    )
    require(found is not None, "native DP AUX entrypoint missing")
    begin = found.start()
    after = code.find("\n}\n", found.end())
    require(after != -1, "native DP AUX body unterminated")
    return code[begin:after + 3]


def audit(code: str) -> None:
    c = function(code)
    need = (
        "u8 txbuf[20], rxbuf[20];",
        "size_t txsize, rxsize;",
        "if (msg->size && !msg->buffer)\n\t\treturn -EINVAL;",
        "if (msg->size > sizeof(txbuf) - HEADER_SIZE)\n"
        "\t\t\treturn -E2BIG;",
        "if (msg->size >= sizeof(rxbuf))\n\t\t\treturn -E2BIG;",
        "if (ret)\n\t\t\t\tmemcpy(msg->buffer, rxbuf + 1, ret);",
        "txsize = msg->size ? HEADER_SIZE + msg->size : BARE_ADDRESS_SIZE;",
        "rxsize = msg->size + 1;",
    )
    for source_line in need:
        require(source_line in c, "missing gate " + source_line[:58])

    def ordered(*tokens: str) -> bool:
        indexes = [c.find(t) for t in tokens]
        return -1 not in indexes and indexes == sorted(indexes) and len(set(indexes)) == len(indexes)

    require(ordered(
        "if (msg->size && !msg->buffer)",
        "intel_dp_aux_header(txbuf, msg);",
        "switch (msg->request & ~DP_AUX_I2C_MOT)"),
        "NULL gate must precede potential AUX payload use")
    require(ordered(
        "case DP_AUX_I2C_WRITE_STATUS_UPDATE:",
        "if (msg->size > sizeof(txbuf) - HEADER_SIZE)",
        "txsize = msg->size ? HEADER_SIZE + msg->size : BARE_ADDRESS_SIZE;"),
        "write arithmetic before hard bound")
    require(ordered(
        "case DP_AUX_I2C_READ:",
        "if (msg->size >= sizeof(rxbuf))",
        "rxsize = msg->size + 1;"),
        "read arithmetic before hard bound")
    require(c.count("if (msg->size > sizeof(txbuf) - HEADER_SIZE)") == 1 and
            c.count("if (msg->size >= sizeof(rxbuf))") == 1,
            "ambiguous AUX length checks")
    require(re.search(r"#define\s+HEADER_SIZE\s+\(BARE_ADDRESS_SIZE\s+\+\s+1\)",
                      code) is not None and
            re.search(r"#define\s+BARE_ADDRESS_SIZE\s+3", code) is not None,
            "header layout changed: 20-byte limit needs new audit")


def requested_payload_status(request: str, size: int, has_buffer: bool) -> str:
    # Simple model bound to the concrete C guards by audit(); not C execution.
    if size and not has_buffer:
        return "EINVAL"
    if request == "write":
        if size > 20 - 4:
            return "E2BIG"
    elif request == "read":
        if size >= 20:
            return "E2BIG"
    else:
        return "EINVAL"
    return "SAFE_TO_SEND"


def run(cmd: list[str], cwd: Path) -> None:
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    require(p.returncode == 0, "scratch git apply failure: " + p.stderr[-500:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-dp", required=True, type=Path)
    parser.add_argument("--linux-dp-aux", required=True, type=Path)
    parser.add_argument("--patch", required=True, type=Path)
    args = parser.parse_args()

    original = args.netbsd_dp.read_bytes()
    linux = args.linux_dp_aux.read_bytes()
    require(gitblob(original) == NETBSD_SHA, "wrong frozen NetBSD C")
    require(gitblob(linux) == LINUX_SHA, "wrong frozen Linux C")
    upstream = function(linux.decode())
    require("u8 txbuf[20], rxbuf[20];" in upstream, "upstream AUX limit changed")
    require("txsize = msg->size ? HEADER_SIZE + msg->size" in upstream,
            "upstream write-path reference changed")

    with tempfile.TemporaryDirectory(prefix="hp-i915-dp-aux-0043-") as tmp:
        root = Path(tmp)
        target = root / REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
        patch = str(args.patch.resolve(strict=True))
        run(["git", "apply", "--check", patch], root)
        run(["git", "apply", patch], root)
        patched = target.read_text()
        audit(patched)
        print("I915_DP_AUX_0043_PINNED_PATCH_SOURCE_PASS")

        mutants = (
            ("null_length", "if (msg->size && !msg->buffer)",
             "if (false)"),
            ("write_overflow", "if (msg->size > sizeof(txbuf) - HEADER_SIZE)",
             "if (msg->size > SIZE_MAX)"),
            ("write_off_by_one", "if (msg->size > sizeof(txbuf) - HEADER_SIZE)",
             "if (msg->size >= sizeof(txbuf) - HEADER_SIZE)"),
            ("read_overflow", "if (msg->size >= sizeof(rxbuf))",
             "if (msg->size > sizeof(rxbuf))"),
            ("read_zero_copy", "if (ret)\n\t\t\t\tmemcpy(msg->buffer, rxbuf + 1, ret);",
             "memcpy(msg->buffer, rxbuf + 1, ret);"),
        )
        for name, anchor, replacement in mutants:
            require(patched.count(anchor) == 1, "ambiguous mutant " + name)
            bad = patched.replace(anchor, replacement, 1)
            try:
                audit(bad)
            except AssertionError as exc:
                require("I915_DP_AUX_BOUNDS_REFUSED" in str(exc),
                        "unexpected rejection " + name)
            else:
                raise AssertionError("bad AUX guard accepted: " + name)
        print("I915_DP_AUX_FIVE_UNSAFE_SOURCE_MUTANTS_REFUSED")

        # Boundary model preserves max writes=16 bytes, reads=19 bytes;
        # rejects too-large and machine-word maximum BEFORE addition.
        samples = (0, 1, 15, 16, 17, 19, 20, MAX_SIZE_T)
        for length in samples:
            for request in ("read", "write"):
                got = requested_payload_status(request, length, True)
                cap = 19 if request == "read" else 16
                require(got == ("SAFE_TO_SEND" if length <= cap else "E2BIG"),
                        "payload bound wrong " + request + " " + str(length))
                if length:
                    require(requested_payload_status(request, length, False) == "EINVAL",
                            "missing NULL rejection " + request)
            require(requested_payload_status("invalid", length, True) == "EINVAL",
                    "invalid request admitted")
        print("I915_DP_AUX_SIZE_T_BOUNDARY_MODEL_40_CASES_PASS")

        run(["git", "apply", "--reverse", patch], root)
        require(target.read_bytes() == original, "not byte-exact rollback")
        print("I915_DP_AUX_EXACT_REVERSE_PASS")

    print("LIMIT: source/parsing/scratch apply only; no native NetBSD kernel compile or HP KMS test.")


if __name__ == "__main__":
    main()
