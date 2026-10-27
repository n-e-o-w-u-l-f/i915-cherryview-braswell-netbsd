#!/usr/bin/env python3
"""F19: pinned-original NetBSD DRM console preflight and extracted C11 regression.

Actual git apply to a disposable copy of NetBSD/src@03d918f6; exactly the
F19-edited function is extracted into compiled GCC/Clang host tests with mocked
autoconf, VGA and kernel lock operations. DOES NOT compile a NetBSD object,
supply a kernel build, or verify the HP's observed option-5 vpanic.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
DRMFB = Path("sys/external/bsd/drm2/drm/drmfb.c")
WSDISPLAY = Path("sys/dev/wscons/wsdisplay.c")
FILES = Path("sys/external/bsd/drm2/i915drm/files.i915drmkms")
BLOBS = {
    DRMFB: "f71bee4c525b4199dc4e3eb52ad3f321787e5905",
    WSDISPLAY: "64f1d2ed2113b6f16c86565dd4780be954dd2a35",
    FILES: "23d352b64eb1799caf3e9b2770f78795accc8439",
}
PATCH = (ROOT / "patches/candidates/"
         "netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch")
PREAMBLE = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>

typedef void *device_t;
typedef void *cfdata_t;
struct drm_device { int unused; };
struct drmfb_params {
    bool (*dp_is_vga_console)(struct drm_device *);
    void (*dp_disable_vga)(struct drm_device *);
};
struct drmfb_attach_args {
    device_t da_dev;
    const struct drmfb_params *da_params;
};
struct wsemuldisplaydev_attach_args { int console; };

static int actual_vga, child_present, searches, vgadetaches, vgadisables;
static int errors, locks, unlocks, locked, child_flags;

static bool detect_vga(struct drm_device *unused)
{
    (void)unused;
    return actual_vga != 0;
}
static void disable_vga(struct drm_device *unused)
{
    (void)unused;
    vgadisables++;
}
#if NVGA > 0
static void vga_cndetach(void) { vgadetaches++; }
#endif
static cfdata_t config_search(device_t dev,
    struct wsemuldisplaydev_attach_args *args, const void *cfargs)
{
    (void)dev;
    (void)cfargs;
    assert(locked == 1);
    searches++;
    child_flags = args->console;
    return child_present ? (cfdata_t)&searches : NULL;
}
static void aprint_error_dev(device_t dev, const char *message, ...)
{
    (void)dev;
    assert(strstr(message, "no wsdisplay child configured") != NULL);
    errors++;
}
#define CFARGS(...) NULL
#define KERNEL_LOCK(n,arg) do { \
    assert((n) == 1); assert(!locked); locked = 1; locks++; \
} while (0)
#define KERNEL_UNLOCK_ONE(arg) do { \
    assert(locked); locked = 0; unlocks++; \
} while (0)

static int run_exact_f19_block(bool console_property)
{
    struct drm_device object = {0};
#if NVGA > 0
    struct drm_device *const dev = &object;
    bool was_vga_console = false;
#else
    (void)object;
#endif
    const struct drmfb_params params = {
        .dp_is_vga_console = detect_vga,
        .dp_disable_vga = disable_vga
    };
    const struct drmfb_attach_args args = {
        .da_dev = NULL,
        .da_params = &params
    };
    const struct drmfb_attach_args *da = &args;
    bool is_console = console_property;
"""
POSTAMBLE = r"""
    return 0;
}

int main(void)
{
    int total = 0;
    for (int props = 0; props <= 1; ++props) {
        for (int vga = 0; vga <= 1; ++vga) {
            for (int child = 0; child <= 1; ++child) {
                actual_vga = vga;
                child_present = child;
                searches = vgadetaches = vgadisables = errors = 0;
                locks = unlocks = locked = child_flags = 0;
                const int owns_console =
                    props || (NVGA > 0 && vga);
                const int should_reject = owns_console && !child;
                const int result = run_exact_f19_block(props != 0);
                assert(result == (should_reject ? ENXIO : 0));
                assert(searches == owns_console);
                assert(locks == owns_console && unlocks == owns_console);
                assert(locked == 0);
                assert(child_flags == owns_console);
                assert(errors == should_reject);
                const int safe_vga_takeover =
                    NVGA > 0 && vga && child;
                assert(vgadetaches == safe_vga_takeover);
                assert(vgadisables == safe_vga_takeover);
                ++total;
            }
        }
    }
    assert(total == 8);
    printf("F19_EXTRACTED_NATIVE_PRECHECK_MODEL_8_OF_8_PASS_NVGA_%d\n", NVGA);
    return 0;
}
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def extract_function(text: str) -> str:
    tag = "\ndrmfb_attach(struct drmfb_softc *sc, const struct drmfb_attach_args *da)\n"
    check(text.count(tag) == 1, "missing or duplicated drmfb_attach")
    start = text.index("int\n" + tag[1:])
    end = text.index("\nint\ndrmfb_detach(", start)
    return text[start:end]


def exact_preflight_block(function: str) -> str:
    # The original VGA ownership comment is unchanged. Grab the complete
    # transformed VGA ownership/precheck/VGA detach block before property set.
    marker = "\n#if NVGA > 0\n\t/*\n\t * Whether or not we were told"
    start = function.index(marker)
    end = function.index("\n\tprop_dictionary_set_bool(dict, \"is_console\"", start)
    return function[start + 1:end]


def compile_and_run(source: str, work: Path, compiler: str,
                    dialect: str, nvga: int, suffix: str) -> int:
    filename = work / ("f19_" + suffix + ".c")
    output = work / ("f19_" + suffix)
    filename.write_text(source)
    compile_result = subprocess.run(
        [compiler, "-std=" + dialect, "-Wall", "-Wextra", "-Werror",
         "-fsanitize=undefined", "-fno-sanitize-recover=all",
         "-DNVGA=" + str(nvga), str(filename), "-o", str(output)],
        capture_output=True, text=True,
    )
    check(compile_result.returncode == 0,
          f"host compiler {compiler}/{dialect}/{nvga}: {compile_result.stderr}")
    process = subprocess.run([str(output)], capture_output=True, text=True)
    return process.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--netbsd-tree", type=Path)
    group.add_argument("--verified-blob-dir", type=Path)
    args = parser.parse_args()
    root = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree is not None:
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        check(head == PIN, "wrong original NetBSD git checkout")
    original = {}
    for path, expected in BLOBS.items():
        data = (root / path).read_bytes()
        check(blob_sha(data) == expected, f"original NetBSD source drift: {path}")
        original[path] = data.decode("utf-8")

    check("device\tintelfb: intelfbbus, drmfb, drmfb_pci, wsemuldisplaydev"
          in original[FILES], "NetBSD intelfb device lacks expected iattr")
    ws = original[WSDISPLAY]
    match = ws[ws.index("wsdisplay_emul_match("):
               ws.index("\nvoid\nwsdisplay_emul_attach(", ws.index("wsdisplay_emul_match("))]
    check("ap->console != 0" in match, "console matcher preflight assumption drift")
    check("return 10;" in match and "return 1;" in match,
          "expected pure matcher priority drift")

    with tempfile.TemporaryDirectory(prefix="f19-drmfb-candidate-") as d:
        stage = Path(d)
        file = stage / DRMFB
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes((root / DRMFB).read_bytes())
        numstat = subprocess.check_output(
            ["git", "apply", "--numstat", str(PATCH)], text=True)
        touched = {Path(line.split("\t", 2)[2])
                   for line in numstat.splitlines()}
        check(touched == {DRMFB}, "F19 changes files beyond drmfb.c")
        for options in (("--check",), ()):
            subprocess.run(["git", "-C", str(stage), "apply",
                            "--whitespace=error", *options, str(PATCH)],
                           capture_output=True, text=True, check=True)
        before = original[DRMFB]
        after = file.read_text()
        old_fn, new_fn = extract_function(before), extract_function(after)
        check(after.replace(new_fn, old_fn, 1) == before,
              "F19 changes code outside drmfb_attach")
        snippet = exact_preflight_block(new_fn)
        check(snippet.count("config_search(") == 1, "wrong preflight count")
        check(snippet.index("child = config_search(") <
              snippet.index("vga_cndetach();"),
              "existing VGA console must remain intact until preflight")
        check(snippet.index("KERNEL_LOCK(1, NULL);") <
              snippet.index("config_search(") <
              snippet.index("KERNEL_UNLOCK_ONE(NULL);"),
              "configuration search lock span drift")
        check(snippet.index("return ENXIO;") <
              snippet.index("vga_cndetach();"),
              "missing-child early exit must precede VGA detach")
        check("CFARGS(.iattr = \"wsemuldisplaydev\")" in snippet,
              "wrong autoconf interface attr")

        c_source = PREAMBLE + snippet + POSTAMBLE
        runs = 0
        for compiler in ("gcc", "clang"):
            for dialect in ("gnu99", "gnu11"):
                for nvga in (0, 1):
                    suffix = f"{compiler}_{dialect}_{nvga}"
                    rc = compile_and_run(c_source, stage, compiler,
                                         dialect, nvga, suffix)
                    check(rc == 0, f"{suffix}: positive regression failed")
                    print("F19_POSITIVE_8_CASES_PASS", suffix)
                    runs += 1

        check(snippet.count("if (child == NULL) {") == 1,
              "unable to identify failure precheck for negative test")
        broken = snippet.replace("if (child == NULL) {", "if (child != NULL) {", 1)
        rc = compile_and_run(PREAMBLE + broken + POSTAMBLE, stage,
                             "gcc", "gnu11", 1, "wrong_null_guard")
        check(rc != 0, "missing-child negative mutant unexpectedly passed")
        print("F19_MISSING_CHILD_NEGATIVE_MUTANT_REJECTED")

    check(runs == 8, "eight compiler configurations required")
    print("F19_PINNED_GIT_APPLY_EXACT_C_BLOCK_64_CASES_GCC_CLANG_UBSAN_PASS")
    print("F19_NOT_A_NETBSD_KERNEL_OBJECT_OR_HP_BOOT_TEST")


if __name__ == "__main__":
    main()
