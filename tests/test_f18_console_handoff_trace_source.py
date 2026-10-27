#!/usr/bin/env python3
"""Verify F18 console-handoff trace against actual pinned NetBSD source.

SOURCE ONLY: does not build a NetBSD kernel or authorize another HP boot.
The default, uninstrumented C code must remain byte-for-byte unchanged
after removing only F18's guarded sections.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
BLOBS = {
    Path("sys/dev/wsfb/genfb.c"): "cb9094da52262743df52d20b2bf0b2c320886fa1",
    Path("sys/dev/wscons/wsdisplay.c"): "64f1d2ed2113b6f16c86565dd4780be954dd2a35",
    Path("sys/external/bsd/drm2/drm/drmfb.c"): "f71bee4c525b4199dc4e3eb52ad3f321787e5905",
    Path("sys/external/bsd/drm2/i915drm/intelfb.c"): "482f05fb6879cae8bebaf9aa6e3bd054dc6118b4",
}
PATCH = ROOT / "patches/candidates/netbsd11-f18-i915-console-handoff-trace-20261027.patch"
GUARD = re.compile(
    r"^#ifdef HP_I915_CONSOLE_TRACE\n"
    r"(?P<enabled>(?:(?!^#else\n|^#endif\n)[\s\S])*)"
    r"(?:^#else\n(?P<disabled>(?:(?!^#endif\n)[\s\S])*))?"
    r"^#endif\n", re.M,
)
MARKERS = {
    "sys/dev/wsfb/genfb.c": ("GFB1", "GFB2"),
    "sys/dev/wscons/wsdisplay.c": ("WSD",),
    "sys/external/bsd/drm2/drm/drmfb.c": ("DRM1", "DRM2"),
    "sys/external/bsd/drm2/i915drm/intelfb.c": ("IFB1", "IFB2"),
}


def check(state: bool, why: str) -> None:
    if not state:
        raise AssertionError(why)


def blob_oid(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def remove_optional_trace(source: str) -> tuple[str, int]:
    count = 0

    def strip(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group("disabled") or ""

    stripped = GUARD.sub(strip, source)
    check("HP_I915_CONSOLE_TRACE" not in stripped, "unrecognized trace guard")
    return stripped, count


def run() -> None:
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--netbsd-tree", type=Path)
    options.add_argument("--verified-blob-dir", type=Path)
    args = parser.parse_args()
    original_root = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree:
        head = subprocess.check_output(
            ["git", "-C", str(original_root), "rev-parse", "HEAD"], text=True).strip()
        check(head == NETBSD, f"unexpected NetBSD revision: {head}")
    original = {}
    with tempfile.TemporaryDirectory(prefix="f18-console-handoff-") as temp:
        scratch = Path(temp)
        for relative, expected in BLOBS.items():
            data = (original_root / relative).read_bytes()
            check(blob_oid(data) == expected, f"wrong original Git blob: {relative}")
            original[relative] = data.decode("utf-8")
            dest = scratch / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        changed_paths = {
            Path(line.split("\t", 2)[2])
            for line in subprocess.check_output(
                ["git", "apply", "--numstat", str(PATCH)],
                text=True).splitlines()
        }
        check(changed_paths == set(BLOBS), "trace patch changed unexpected files")
        for options in (("--check",), ()):
            subprocess.run(
                ["git", "-C", str(scratch), "apply", "--whitespace=error",
                 *options, str(PATCH)],
                capture_output=True, text=True, check=True,
            )

        for relative, base in original.items():
            source = (scratch / relative).read_text(encoding="utf-8")
            clean, count = remove_optional_trace(source)
            check(clean == base, f"unguarded source was changed: {relative}")
            expected_markers = MARKERS[str(relative)]
            check(count == len(expected_markers),
                  f"guard count mismatch: {relative}, {count}")
            for marker in expected_markers:
                check(source.count("[I915-CN " + marker + "]") == 1,
                      f"missing/duplicated marker {marker}")
                check("[I915-CN " + marker + "]" not in base,
                      f"preexisting marker in original: {marker}")

        genfb = (scratch / Path("sys/dev/wsfb/genfb.c")).read_text()
        display = (scratch / Path("sys/dev/wscons/wsdisplay.c")).read_text()
        drmfb = (scratch / Path("sys/external/bsd/drm2/drm/drmfb.c")).read_text()
        intelfb = (scratch / Path("sys/external/bsd/drm2/i915drm/intelfb.c")).read_text()
        check(genfb.index("[I915-CN GFB1]") < genfb.index("vcons_init(&sc->vd"),
              "GFB1 must precede screen preparation and the no-print interval")
        check(genfb.index("[I915-CN GFB2]") > genfb.index(
              "child = config_found(sc->sc_dev"), "GFB2 must report child result")
        check(display.index("[I915-CN WSD]") > display.index(
              "cn_tab->cn_dev = makedev"), "WSD marker must follow real cn_dev")
        check(drmfb.index("[I915-CN DRM1]") > drmfb.index(
              'prop_dictionary_set_bool(dict, "is_console", is_console)'),
              "DRM1 must report decided console ownership")
        check(drmfb.index("[I915-CN DRM2]") > drmfb.index(
              "KERNEL_UNLOCK_ONE(NULL)"), "DRM2 should not log under KERNEL_LOCK")
        check(intelfb.index("[I915-CN IFB1]") <
              intelfb.index("error = drmfb_attach(&sc->sc_drmfb"),
              "IFB1 must precede attachment")
        check(intelfb.index("[I915-CN IFB2]") >
              intelfb.index("error = drmfb_attach(&sc->sc_drmfb"),
              "IFB2 must report attachment outcome")
    print("F18_PINNED_4_NETBSD_FILES_7_TRACE_MARKERS_NO_BEHAVIOR_DIFF_PASS")


if __name__ == "__main__":
    run()
