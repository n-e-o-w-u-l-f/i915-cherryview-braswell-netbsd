#!/usr/bin/env python3
"""Pinned NetBSD i915 probe/async/parent-task SOURCE contract oracle.

Read only. No HP access, build, kernel patch, fault injection, or hardware test.
The expected BUG_PRESENT on the frozen NetBSD source is a PASS for detection,
not evidence that any production defect is fixed.
"""
import argparse
import hashlib
import json
from pathlib import Path

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
FILES = {
    "drv": ("sys/external/bsd/drm2/dist/drm/i915/i915_drv.c",
            "bf64ff40059fc38188f6f3d7b55bef9793abeb57"),
    "fbdev": ("sys/external/bsd/drm2/dist/drm/i915/display/intel_fbdev.c",
              "381b63df5d1f57337057d541827a7726e602f477"),
    "async": ("sys/external/bsd/drm2/include/linux/async.h",
              "a761ff7606b4ddce958af193833b995b2e313b09"),
    "native": ("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c",
               "9798385b02f247c08db9b16624d5ddc9d11a8ca5"),
    "intelfb": ("sys/external/bsd/drm2/i915drm/intelfb.c",
                "482f05fb6879cae8bebaf9aa6e3bd054dc6118b4"),
}


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def body(source, signature):
    at = source.index(signature)
    opened = source.index("{", at + len(signature))
    depth = 1
    for pos in range(opened + 1, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[opened + 1:pos]
    raise ValueError("unterminated function: " + signature)


def failure_branch_dirty(attach_body):
    error = attach_body.index("if (error)")
    after = attach_body.index("sc->sc_drm_dev =", error)
    branch = attach_body[error:after]
    return "return;" in branch and "sc_task_thread" not in branch


def assess(src):
    drv = body(src["drv"], "int i915_driver_probe(")
    registration = body(src["drv"], "static void i915_driver_register(")
    modeset = body(src["drv"], "static int i915_driver_modeset_probe(")
    async_fn = body(src["async"], "async_schedule(void (*fn)(void *, async_cookie_t), void *arg)")
    attach = body(src["native"], "i915drmkms_attach_real(device_t self)")
    detach = body(src["native"], "i915drmkms_detach(device_t self, int flags)")
    child = body(src["intelfb"], "intelfb_attach(device_t parent, device_t self, void *aux)")
    creator = body(src["fbdev"], "static int intelfb_create(")
    initial = body(src["fbdev"], "static void intel_fbdev_initial_config(")
    a = drv.index("ret = i915_driver_modeset_probe(dev_priv);")
    b = drv.index("i915_driver_register(dev_priv);")
    return {
        "modeset_before_register": a < b,
        "failure_exits_before_register": "goto out_cleanup_hw;" in drv[a:b],
        "registration_returns_void": "static void i915_driver_register(" in src["drv"],
        "registration_schedules_initial_fb": "intel_fbdev_initial_config_async(dev);" in registration,
        "netbsd_async_schedule_is_inline": "(*fn)(arg, 1);" in async_fn and "return 1;" in async_fn,
        "fb_initial_config_reaches_helper": "drm_fb_helper_initial_config(" in initial,
        "fb_create_attaches_intelfb": "config_found(" in creator,
        "native_owner_set_before_probe": attach.index("sc->sc_task_thread = curlwp;") < attach.index("i915_driver_probe("),
        "probe_failure_leaves_owner_dirty": failure_branch_dirty(attach),
        "detach_asserts_owner_null": "KASSERT(sc->sc_task_thread == NULL);" in detach,
        "normal_queue_drain_before_owner_clear": attach.index("SIMPLEQ_REMOVE_HEAD") < attach.rindex("atomic_store_relaxed(&sc->sc_task_thread, NULL);"),
        "intelfb_schedules_and_increments_pending": "i915drmkms_task_schedule(parent" in child and "config_pending_incr(self);" in child,
    }


def self_test():
    # The tests deliberately distinguish bug detection from a hypothetical fix.
    dirty = "if (error) { log(); return; } sc->sc_drm_dev = ptr;"
    fixed = "if (error) { sc->sc_task_thread = NULL; return; } sc->sc_drm_dev = ptr;"
    assert failure_branch_dirty(dirty)
    assert not failure_branch_dirty(fixed)
    assert body("int fn(void) { if (x) { y(); } return 1; }", "int fn(void)") == " if (x) { y(); } return 1; "
    assert git_blob_sha(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"
    print(json.dumps({"self_test": "PASS", "fixtures": 4, "kind": "SOURCE_ORACLE_ONLY"}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-src", type=Path, help="Full, pinned NetBSD/src checkout root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.netbsd_src is None:
        parser.error("provide --netbsd-src or --self-test")
    source = {}
    for name, (path, expected_sha) in FILES.items():
        data = (args.netbsd_src / path).read_bytes()
        actual = git_blob_sha(data)
        if actual != expected_sha:
            print(json.dumps({"status": "PIN_MISMATCH", "source": name, "expected": expected_sha, "actual": actual}))
            return 2
        source[name] = data.decode("utf-8")
    checks = assess(source)
    passed = sum(checks.values())
    result = {
        "pin": PIN,
        "status": "PINNED_SOURCE_BUG_DETECTED" if passed == len(checks) else "CONTRACT_CHANGED_OR_UNVERIFIED",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "native_compile": "NOT_RUN",
        "HP_runtime": "NOT_RUN",
        "production_fix": "NOT_IMPLEMENTED",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed == len(checks) else 3


if __name__ == "__main__":
    raise SystemExit(main())
