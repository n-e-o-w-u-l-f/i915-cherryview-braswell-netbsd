#!/usr/bin/env python3
"""Pinned NetBSD eDP DPCD short/failed link-rate read guard, source-only.

Compile the exact rate-decoder fragment from the pinned native intel_dp.c
with C11 sanitizers; this is not native kernel compilation or KMS proof.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess
import tempfile

PINNED_DP_SHA256 = "7f79318fee13fd67da6d0c0b21da90a372310e297c38767397bfd96129db0141"
PATCH_SHA256 = "a50717c043eff10e31c5dd8d9582632d71197203c5a13738e12e7e520817a5fa"
REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
BEG = "\t\t__le16 sink_rates[DP_MAX_SUPPORTED_RATES];"
END = "\t\tintel_dp->num_sink_rates = i;"
OLD = "\t\tdrm_dp_dpcd_read(&intel_dp->aux, DP_SUPPORTED_LINK_RATES,\n\t\t\t\tsink_rates, sizeof(sink_rates));"
NEW = (
    "\t\tif (drm_dp_dpcd_read(&intel_dp->aux, DP_SUPPORTED_LINK_RATES,\n"
    "\t\t\t\t     sink_rates, sizeof(sink_rates)) !=\n"
    "\t\t    (ssize_t)sizeof(sink_rates)) {\n"
    "\t\t\tDRM_DEBUG_KMS(\"Unable to read eDP supported link rates, \"\n"
    "\t\t\t\t\t      \"using default rates\\n\");\n"
    "\t\t\tmemset(sink_rates, 0, sizeof(sink_rates));\n"
    "\t\t}"
)

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
typedef uint16_t __le16;
#define DP_MAX_SUPPORTED_RATES 8
#define DP_SUPPORTED_LINK_RATES 0x10
/* The kernel's ARRAY_SIZE is evaluated for its count. Only the mock's
   int loop bound is narrowed to avoid an unrelated host-Werror diagnostic. */
#define ARRAY_SIZE(v) ((int)(sizeof(v)/sizeof((v)[0])))
#define DRM_DEBUG_KMS(...) ((void)0)
#define le16_to_cpu(v) (v)
struct intel_dp {
  int aux;
  int sink_rates[DP_MAX_SUPPORTED_RATES];
  int num_sink_rates;
  bool use_rate_select;
  int fallback_calls;
};
static int scenario;
static ssize_t drm_dp_dpcd_read(int *aux, unsigned reg, void *out, size_t n) {
  const __le16 sample[DP_MAX_SUPPORTED_RATES] = {8100,13500,16200,0,10000};
  assert(aux && reg == DP_SUPPORTED_LINK_RATES && n == sizeof(sample));
  if(scenario == 0 || scenario == 4) {
    if(scenario == 4) memset(out,0,n);
    else memcpy(out,sample,n);
    return (ssize_t)n;
  }
  if(scenario == 2) { memcpy(out,sample,2); return 2; }
  if(scenario == 3) return 0;
  assert(scenario == 1);
  return -EIO;
}
static void intel_dp_set_sink_rates(struct intel_dp *dp) {dp->fallback_calls++;}
static void probe(struct intel_dp *intel_dp) {
__FRAGMENT__
  if (intel_dp->num_sink_rates) intel_dp->use_rate_select=true;
  else intel_dp_set_sink_rates(intel_dp);
}
int main(void) {
  for(scenario=0;scenario<5;scenario++){
    struct intel_dp dp={0};
    for(int i=0;i<ARRAY_SIZE(dp.sink_rates);i++) dp.sink_rates[i]=-100;
    probe(&dp);
    if(scenario==0) {
      assert(dp.num_sink_rates==3 && dp.use_rate_select && !dp.fallback_calls);
      assert(dp.sink_rates[0]==162000 && dp.sink_rates[1]==270000 &&
             dp.sink_rates[2]==324000 && dp.sink_rates[3]==-100);
    } else {
      assert(dp.num_sink_rates==0 && !dp.use_rate_select &&
             dp.fallback_calls==1 && dp.sink_rates[0]==-100);
    }
  }
  puts("I915_0012_PINNED_DPCD_RATE_READ_5_C11_CASES_OK");
  return 0;
}
'''


def verify(input_bytes: bytes, patch_bytes: bytes) -> str:
    if hashlib.sha256(input_bytes).hexdigest() != PINNED_DP_SHA256:
        raise ValueError("not pinned NetBSD intel_dp.c bytes")
    if hashlib.sha256(patch_bytes).hexdigest() != PATCH_SHA256:
        raise ValueError("not pinned i915 owner candidate 0012 patch")
    original = input_bytes.decode("utf-8")
    start = original.index(BEG)
    stop = original.index(END, start) + len(END)
    old_fragment = original[start:stop]
    if old_fragment.count(OLD) != 1 or "memset(sink_rates" in old_fragment:
        raise ValueError("old eDP rate read context changed")
    expected = original[:start] + old_fragment.replace(OLD, NEW, 1) + original[stop:]
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile="a/" + REL, tofile="b/" + REL,
    ))
    if diff.encode("utf-8") != patch_bytes:
        raise ValueError("candidate 0012 differs from exact source transform")
    if expected.count(NEW) != 1:
        raise ValueError("new short-read branch missing/duplicated")
    if "memset(sink_rates, 0, sizeof(sink_rates));" not in expected[start:stop+len(NEW)]:
        raise ValueError("short-read error must clear entire rate array")
    return expected


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-intel-dp", type=Path, required=True)
    ap.add_argument("--patch", type=Path, required=True)
    args = ap.parse_args()
    original = args.netbsd_intel_dp.read_bytes()
    patch = args.patch.read_bytes()
    expected = verify(original, patch)
    with tempfile.TemporaryDirectory(prefix="chv-dpcd-rates-") as tmp:
        work = Path(tmp)
        target = work / REL
        target.parent.mkdir(parents=True)
        target.write_bytes(original)
        for flags in (["--check"], []):
            subprocess.run(["git", "-C", str(work), "apply", *flags,
                            str(args.patch.resolve())], check=True,
                           capture_output=True)
        if target.read_text() != expected:
            raise AssertionError("real git apply differs from exact patch")
        duplicate = subprocess.run(
            ["git", "-C", str(work), "apply", "--check",
             str(args.patch.resolve())], capture_output=True)
        if duplicate.returncode == 0:
            raise AssertionError("duplicate patch accepted")
        fragment = expected[expected.index(BEG):
                            expected.index(END, expected.index(BEG))+len(END)]
        c_file, binary = work / "test.c", work / "test"
        c_file.write_text(HARNESS.replace("__FRAGMENT__", fragment))
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-pedantic", "-fsanitize=undefined",
                        "-fno-omit-frame-pointer", str(c_file), "-o",
                        str(binary)], check=True, capture_output=True)
        test = subprocess.run([str(binary)], check=True, capture_output=True,
                              text=True)
        assert "I915_0012_PINNED_DPCD_RATE_READ_5_C11_CASES_OK" in test.stdout
        subprocess.run(["git", "-C", str(work), "apply", "--reverse",
                        str(args.patch.resolve())], check=True,
                       capture_output=True)
        if target.read_bytes() != original:
            raise AssertionError("original source not exactly restored")

    # Independent source-invariant negative cases: mutation must be rejected.
    for mutant in (
        original + b"x",
        original.replace(b"DP_MAX_SUPPORTED_RATES", b"DP_MAX_SUPPORTED_RATEZ", 1),
    ):
        try:
            verify(mutant, patch)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt original passed")
    for mutant in (patch+b"x", patch.replace(b"memset(sink_rates", b"memcmp(sink_rates", 1),
                   patch.replace(b"(ssize_t)sizeof(sink_rates)", b"2", 1)):
        try:
            verify(original, mutant)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt patch passed")
    print("I915_0012_DPCD_RATE_SOURCE_PATCH_5_CASES_5_MUTANTS_PASS")
    print("LIMIT: source-extracted host C, not NetBSD target kernel/HP hardware")


if __name__ == "__main__":
    main()
