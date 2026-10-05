#!/usr/bin/env python3
"""Strict source-extracted NetBSD AUX IRQ-unavailable regression, 0013.

Compile the actual pinned intel_dp_aux_wait_done() with the 0013 transform
under host C11 ASan/UBSan. Exercise cold, uninstalled, runtime-disabled,
installed/active and timeout cases. The unpatched frozen source is a
negative control that must incorrectly select the IRQ wait without an IRQ.
Check pinned NetBSD IRQ state transitions and the pinned Linux poll-vs-IRQ
policy, the byte-identical generated candidate, and actual git apply --check.

This test is not a native NetBSD object build or an HP eDP runtime test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from sanitizer_support import run_sanitized
import resource
import signal
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / "tools/generate_edp_aux_irq_fallback_patch.py"))
NETBSD_IRQ = "sys/external/bsd/drm2/dist/drm/i915/i915_irq.c"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
LINUX_AUX = "drivers/gpu/drm/i915/display/intel_dp_aux.c"

PRELUDE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>

#define __NetBSD__ 1
typedef unsigned int u32;
typedef int i915_reg_t;
struct drm_i915_private {
    struct { bool irq_enabled; } drm;
    struct { bool irqs_enabled; } runtime_pm;
    int uncore, gmbus_wait_lock, gmbus_wait_queue;
};
struct intel_dp {
    struct drm_i915_private *i915;
    i915_reg_t (*aux_ch_ctl_reg)(struct intel_dp *);
    struct { const char *name; } aux;
};
static int cold, poll_calls, irq_wait_calls, irq_lock_calls, irq_unlock_calls;
static int status_reads, error_calls, hardware_busy;
#define DP_AUX_CH_CTL_SEND_BUSY 0x1u
#define dp_to_i915(dp) ((dp)->i915)
static i915_reg_t ctl_reg(struct intel_dp *dp)
{ assert(dp != NULL); return 0x53; }
static u32 intel_uncore_read_notrace(int *uncore, i915_reg_t reg)
{ assert(uncore != NULL && reg == 0x53); status_reads++; return (u32)hardware_busy; }
static void spin_lock(int *lock) { assert(lock != NULL); irq_lock_calls++; }
static void spin_unlock(int *lock) { assert(lock != NULL); irq_unlock_calls++; }
#define msecs_to_jiffies_timeout(ms) (ms)
#define DRM_SPIN_TIMED_WAIT_NOINTR_UNTIL(ret,queue,lock,ms,cond) \
  do { (void)(queue); (void)(lock); assert((ms) == 10); irq_wait_calls++; \
       (ret) = (cond) ? 1 : 0; } while (0)
#define wait_for_atomic(cond,ms) \
    (assert((ms) == 10),poll_calls++, (cond) ? 0 : -ETIMEDOUT)
#define trace_i915_reg_rw(...) ((void)0)
#define DRM_ERROR(...) ((void)(error_calls++))
"""

MAIN = r"""
static void reset(void)
{
    poll_calls = irq_wait_calls = irq_lock_calls = irq_unlock_calls = 0;
    status_reads = error_calls = hardware_busy = 0;
}
static void test_case(int is_cold, int installed, int runtime, int busy,
                      int expect_poll, int expect_error)
{
    struct drm_i915_private i915 = {0};
    struct intel_dp dp = {.i915 = &i915, .aux_ch_ctl_reg = ctl_reg,
                          .aux = {"aux"}};
    reset();
    cold = is_cold;
    i915.drm.irq_enabled = installed;
    i915.runtime_pm.irqs_enabled = runtime;
    hardware_busy = busy;
    assert(intel_dp_aux_wait_done(&dp) == (u32)busy);
    assert(poll_calls == expect_poll);
    assert(irq_wait_calls == !expect_poll);
    assert(irq_lock_calls == !expect_poll && irq_unlock_calls == !expect_poll);
    assert(status_reads == 1 && error_calls == expect_error);
}
int main(void)
{
    test_case(1,0,0,0,1,0);
    test_case(0,0,0,0,1,0);
    test_case(0,0,1,0,1,0);
    test_case(0,1,0,0,1,0);
    test_case(0,1,1,0,0,0);
    test_case(0,1,1,1,0,1);
    test_case(0,0,1,1,1,1);
    test_case(1,1,1,0,1,0);
    puts("I915_0013_PINNED_AUX_IRQ_POLL_C11_8_CASES_OK");
    return 0;
}
"""


def pinned_file(tree: Path, revision: str, relative: str) -> str:
    head = subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != revision:
        raise RuntimeError("wrong source revision: " + str(tree))
    committed = subprocess.check_output(
        ["git", "-C", str(tree), "show", "HEAD:" + relative], text=True,
    )
    if (tree / relative).read_text() != committed:
        raise RuntimeError("dirty/missing pinned source: " + relative)
    return committed


def irq_wait_fragment(src: str) -> str:
    start = src.index("static u32\nintel_dp_aux_wait_done(")
    end = src.index("static u32 g4x_get_aux_clock_divider(", start)
    return src[start:end]


def compile_run(directory: Path, label: str, fragment: str,
                sanitizers: str, negative: bool) -> subprocess.CompletedProcess[str]:
    c = directory / (label + ".c")
    binary = directory / label
    c.write_text(PRELUDE + "\n" + fragment + "\n" + MAIN)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fsanitize=" + sanitizers, "-fno-omit-frame-pointer",
         str(c), "-o", str(binary)],
        check=True,
    )
    if negative:
        def suppress_core() -> None:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return run_sanitized(
            binary, check=False, capture_output=True, text=True,
            preexec_fn=suppress_core,
        )
    return run_sanitized(
        binary, check=True, capture_output=True, text=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-tree", type=Path, required=True)
    parser.add_argument("--linux-tree", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--overlay-tree", type=Path, default=None)
    args = parser.parse_args()

    original = TOOL["pinned_source"](args.netbsd_tree)
    revised = TOOL["transform"](original)
    irq = pinned_file(args.netbsd_tree, TOOL["NETBSD_PIN"], NETBSD_IRQ)
    linux = pinned_file(args.linux_tree, LINUX_PIN, LINUX_AUX)
    linux_wait = linux[linux.index("static u32\nintel_dp_aux_wait_done("):
                       linux.index("static u32 g4x_get_aux_clock_divider(")]
    assert "if (intel_parent_irq_enabled(display)) {" in linux_wait
    assert "ret = intel_de_wait_ms(display, ch_ctl," in linux_wait
    install = irq[irq.index("int intel_irq_install("):
                  irq.index("void intel_irq_uninstall(")]
    uninstall = irq[irq.index("void intel_irq_uninstall("):
                    irq.index("void intel_runtime_pm_disable_interrupts(")]
    disable = irq[irq.index("void intel_runtime_pm_disable_interrupts("):
                  irq.index("void intel_runtime_pm_enable_interrupts(")]
    assert "dev_priv->drm.irq_enabled = true;" in install
    assert "dev_priv->drm.irq_enabled = false;" in install
    assert "dev_priv->drm.irq_enabled = false;" in uninstall
    assert "dev_priv->runtime_pm.irqs_enabled = false;" in disable
    assert "dev_priv->runtime_pm.irqs_enabled = true;" in irq
    assert "return dev_priv->runtime_pm.irqs_enabled;" in irq
    assert revised.count("if (!cold && i915->drm.irq_enabled &&") == 1
    assert "done = wait_for_atomic(C, timeout_ms) == 0;" in revised

    with tempfile.TemporaryDirectory() as name:
        scratch = Path(name)
        regenerated = scratch / "0013-regenerated.patch"
        TOOL["generate"](args.netbsd_tree, regenerated)
        if regenerated.read_bytes() != args.patch.read_bytes():
            raise AssertionError("candidate 0013 differs from pinned generator")
        print("I915_0013_GENERATOR_BYTE_MATCH_OK", flush=True)
        passed = compile_run(scratch, "positive", irq_wait_fragment(revised),
                             "address,undefined", False)
        print(passed.stdout.strip(), flush=True)
        failed = compile_run(scratch, "negative", irq_wait_fragment(original),
                             "undefined", True)
        if (failed.returncode != -signal.SIGABRT or
                "poll_calls == expect_poll" not in failed.stderr):
            raise AssertionError("original IRQ-missing negative control did not fail")
        print("I915_0013_UNPATCHED_NEGATIVE_CONTROL_OK", flush=True)

    targets = [args.netbsd_tree]
    if args.overlay_tree is not None:
        if args.overlay_tree.resolve() == args.netbsd_tree.resolve():
            raise RuntimeError("overlay must be distinct from frozen NetBSD")
        targets.append(args.overlay_tree)
    for tree in targets:
        subprocess.run(
            ["git", "-C", str(tree), "apply", "--check", str(args.patch)],
            check=True,
        )
    print("I915_0013_APPLY_CHECKS_OK_" +
          ("FROZEN_AND_OVERLAY" if args.overlay_tree else "FROZEN_ONLY"))


if __name__ == "__main__":
    main()
