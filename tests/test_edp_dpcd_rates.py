#!/usr/bin/env python3
"""Pinned eDP 1.4+ supported-link-rate read regression for candidate 0012.

Extracts the *actual* frozen NetBSD rate read, conversion and fallback
C block after the pinned transform and compiles it in a strictly checked
host C11 harness. Tests complete/empty/error/short DPCD reads and older
eDP fallback; unpatched negative control MUST fail on a failed AUX read
that left untrustworthy buffer contents. Verifies original NetBSD DRM
DPCD API contract and pinned Linux's error-path sanitization.

Not a native NetBSD object/kernel build or an HP hardware test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import resource
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / "tools/generate_edp_dpcd_rates_patch.py"))
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
LINUX_DP = "drivers/gpu/drm/i915/display/intel_dp.c"
NETBSD_DRM_DP = "sys/external/bsd/drm2/dist/drm/drm_dp_helper.c"

PRELUDE = r"""
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>

#define DP_EDP_14 0x14
#define DP_MAX_SUPPORTED_RATES 8
#define DP_SUPPORTED_LINK_RATES 0x10
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DRM_DEBUG_KMS(...) ((void)0)
typedef uint16_t __le16;
typedef uint8_t u8;
struct drm_dp_aux { int unused; };
struct intel_dp {
    struct drm_dp_aux aux;
    u8 edp_dpcd[2];
    int sink_rates[DP_MAX_SUPPORTED_RATES];
    int num_sink_rates;
    int use_rate_select;
};
static int read_case, read_calls, fallback_calls, common_calls;
static int le16_to_cpu(__le16 x) { return x; }
static ssize_t drm_dp_dpcd_read(struct drm_dp_aux *aux, unsigned int offset,
                               void *buffer, size_t size)
{
    __le16 *rates = buffer;
    assert(aux != NULL && offset == DP_SUPPORTED_LINK_RATES);
    assert(size == DP_MAX_SUPPORTED_RATES * sizeof(__le16));
    read_calls++;
    /* Model a failed/short transfer that leaves untrustworthy bytes.
       Invalid data is still observable to a buggy caller. */
    for (size_t i = 0; i + 1 < DP_MAX_SUPPORTED_RATES; ++i)
        rates[i] = 8100;
    rates[DP_MAX_SUPPORTED_RATES - 1] = 0;
    if (read_case == 1)
        return -5;
    if (read_case == 2)
        return 2;
    memset(rates, 0, size);
    if (read_case == 3) {
        rates[0] = 8100;  /* 162000 kHz */
        rates[1] = 13500; /* 270000 kHz */
    }
    return (ssize_t)size;
}
static void intel_dp_set_sink_rates(struct intel_dp *dp)
{
    fallback_calls++;
    dp->sink_rates[0] = 162000;
    dp->sink_rates[1] = 270000;
    dp->num_sink_rates = 2;
}
static void intel_dp_set_common_rates(struct intel_dp *dp)
{
    assert(dp->num_sink_rates != 0);
    common_calls++;
}
static void reset(struct intel_dp *dp, int version, int scenario)
{
    memset(dp, 0, sizeof(*dp));
    dp->edp_dpcd[0] = (u8)version;
    read_case = scenario;
    read_calls = fallback_calls = common_calls = 0;
}
"""

MAIN = r"""
int main(void)
{
    struct intel_dp dp;
    reset(&dp, 0x13, 1);
    run_rates(&dp);
    assert(read_calls == 0 && fallback_calls == 1 && common_calls == 1);
    assert(dp.use_rate_select == 0 && dp.num_sink_rates == 2);

    reset(&dp, DP_EDP_14, 3);
    run_rates(&dp);
    assert(read_calls == 1 && fallback_calls == 0 && common_calls == 1);
    assert(dp.use_rate_select == 1 && dp.num_sink_rates == 2);
    assert(dp.sink_rates[0] == 162000 && dp.sink_rates[1] == 270000);

    reset(&dp, DP_EDP_14, 4);
    run_rates(&dp);
    assert(read_calls == 1 && fallback_calls == 1 && common_calls == 1);
    assert(dp.use_rate_select == 0 && dp.num_sink_rates == 2);

    reset(&dp, DP_EDP_14, 1);
    run_rates(&dp);
    assert(read_calls == 1 && fallback_calls == 1 && common_calls == 1);
    assert(dp.use_rate_select == 0 && dp.num_sink_rates == 2);
    assert(dp.sink_rates[0] == 162000 && dp.sink_rates[1] == 270000);

    reset(&dp, DP_EDP_14, 2);
    run_rates(&dp);
    assert(read_calls == 1 && fallback_calls == 1 && common_calls == 1);
    assert(dp.use_rate_select == 0 && dp.num_sink_rates == 2);

    puts("I915_EDP_DPCD_RATES_HOST_C_OK");
    return 0;
}
"""

NEGATIVE_MAIN = r"""
int main(void)
{
    struct intel_dp dp;
    reset(&dp, DP_EDP_14, 1);
    run_rates(&dp);
    /* Unpatched source consumes the corrupted failed-read buffer and
       suppresses the default-rate fallback. This assertion must fail. */
    assert(fallback_calls == 1 && dp.use_rate_select == 0);
    return 0;
}
"""


def committed_source(tree: Path, pin: str, path: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != pin:
        raise RuntimeError(f"source revision mismatch: {head}")
    data = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + path], text=True
    )
    if (tree / path).read_text() != data:
        raise RuntimeError(f"dirty pinned source: {path}")
    return data


def rates_wrapper(src: str) -> str:
    start = src.index("static bool\nintel_edp_init_dpcd(")
    end = src.index("static bool\nintel_dp_get_dpcd(", start)
    function = src[start:end]
    begin = function.index("\t/* Read the eDP 1.4+ supported link rates. */")
    stop = function.index("\t/* Read the eDP DSC DPCD registers */", begin)
    return (
        "static void run_rates(struct intel_dp *intel_dp)\n{\n"
        + function[begin:stop] + "}\n"
    )


def compile_run(tmp: Path, filename: str, block: str, main: str,
                sanitizer: str, is_negative: bool) -> subprocess.CompletedProcess[str]:
    c = tmp / (filename + ".c")
    exe = tmp / filename
    c.write_text(PRELUDE + "\n" + block + "\n" + main)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=" + sanitizer, "-fno-omit-frame-pointer",
         str(c), "-o", str(exe)], check=True,
    )
    if is_negative:
        def disable_core() -> None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return subprocess.run(
            [str(exe)], check=False, text=True, capture_output=True,
            preexec_fn=disable_core,
        )
    return subprocess.run(
        [str(exe)], check=True, text=True, capture_output=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", type=Path, required=True)
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--overlay-tree", type=Path, default=None)
    ap.add_argument("--patch", type=Path, required=True)
    args = ap.parse_args()

    netbsd = TOOL["pinned_source"](args.netbsd_tree)
    revised = TOOL["transform"](netbsd)
    linux = committed_source(args.linux_tree, LINUX_PIN, LINUX_DP)
    drm = committed_source(args.netbsd_tree, TOOL["NETBSD_PIN"], NETBSD_DRM_DP)
    assert "ret = drm_dp_dpcd_read_data(&intel_dp->aux," in linux
    assert "memset(sink_rates, 0, sizeof(sink_rates));" in linux
    assert "ssize_t drm_dp_dpcd_read(struct drm_dp_aux *aux," in drm
    assert "return ret;" in drm
    assert "if (intel_dp->num_sink_rates)" in revised
    assert "else\n\t\tintel_dp_set_sink_rates(intel_dp);" in revised
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        regen = tmp / "0012-regenerated.patch"
        TOOL["generate"](args.netbsd_tree, regen)
        if regen.read_bytes() != args.patch.read_bytes():
            raise AssertionError("candidate 0012 differs from pinned generator")
        print("I915_0012_GENERATOR_BYTE_MATCH_OK", flush=True)

        result = compile_run(
            tmp, "positive", rates_wrapper(revised),
            MAIN, "address,undefined", False,
        )
        print(result.stdout.strip(), flush=True)
        result = compile_run(
            tmp, "negative", rates_wrapper(netbsd),
            NEGATIVE_MAIN, "undefined", True,
        )
        if result.returncode == 0 or "Assertion" not in result.stderr:
            raise AssertionError(
                "original unguarded AUX rate read did not fail negative control"
            )
        print("I915_0012_UNPATCHED_NEGATIVE_CONTROL_OK", flush=True)

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("overlay must differ from the frozen NetBSD tree")
        targets.append(args.overlay_tree)
    for tree in targets:
        subprocess.run(
            ["git", "-C", str(tree), "apply", "--check", str(args.patch)],
            check=True,
        )
    print("I915_0012_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"),
          flush=True)


if __name__ == "__main__":
    main()
