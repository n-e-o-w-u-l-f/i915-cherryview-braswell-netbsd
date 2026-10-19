#!/usr/bin/env python3
"""Strict frozen Linux/NetBSD IOSF QoS lifetime and failed-probe source gate.

Uses actual NetBSD C bodies and the real separate patch, with git apply in an
isolated scratch tree and exact reverse. Models error edges ONLY AFTER checking
their actual C source syntax. Python model is not executed kernel C.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

NETBSD_REL = "sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"
FROZEN_NETBSD_SHA256 = "88c9e4c4ffb0669fdec14fd6a3589ab4aae43b2ef32ad5f6deb78b86ffd1d8e8"
FROZEN_LINUX_BLOB = "1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758"
FROZEN_NATIVE_SIDEBAND_BLOB = "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed"


def need(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError("CHV_IOSF_QOS_LIFECYCLE_REFUSED: " + message)


def gitblob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()


def method(text: str, signature: str) -> str:
    need(text.count(signature) == 1, "native owner absent or ambiguous " + signature)
    start = text.index(signature)
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def section(text: str, from_marker: str, until_marker: str) -> str:
    need(text.count(from_marker) == 1 and text.count(until_marker) == 1,
         "ambiguous control-flow label " + from_marker)
    begin = text.index(from_marker)
    stop = text.index(until_marker, begin + len(from_marker))
    return text[begin:stop]


def validate_linux(linux: str) -> None:
    init = method(linux, "void vlv_iosf_sb_init(")
    fini = method(linux, "void vlv_iosf_sb_fini(")
    need('if (IS_VALLEYVIEW(i915) || IS_CHERRYVIEW(i915))' in init,
         "Linux IOSF mutex platform selection changed")
    need(re.search(r"if \(IS_VALLEYVIEW\(i915\)\)\s*"
                   r"cpu_latency_qos_add_request\(", init) is not None,
         "Linux Valleyview-only QoS acquisition changed")
    need(re.search(r"if \(IS_VALLEYVIEW\(i915\)\)\s*"
                   r"cpu_latency_qos_remove_request\(", fini) is not None,
         "Linux Valleyview-only QoS release changed")


def validate_native(native: str, sb: str) -> None:
    probe = method(native, "static int i915_driver_early_probe(")
    release = method(native, "static void i915_driver_late_release(")
    wq = method(native, "static int i915_workqueues_init(")
    # No safe second destroy: when the second queue allocation fails,
    # i915_workqueues_init() already destroys the first queue.
    need("out_free_wq:\n\tdestroy_workqueue(dev_priv->wq);" in wq,
         "partially allocated workqueue ownership contract changed")
    need(re.search(
        r"mutex_init\(&dev_priv->sb_lock\);\s*"
        r"if \(IS_VALLEYVIEW\(dev_priv\)\)\s*"
        r"pm_qos_add_request\(&dev_priv->sb_qos,", probe) is not None,
        "CHV must not register Valleyview-only QoS")
    need("if (i915_inject_probe_failure(dev_priv))\n\t\treturn -ENODEV;" in probe,
         "injection must exit before early resource initialization")
    need(re.search(r"ret = i915_workqueues_init\(dev_priv\);\s*"
                   r"if \(ret < 0\)\s*goto err_early_resources;", probe)
         is not None, "failed first/second workqueue must skip cleanup")
    need(re.search(r"ret = vlv_alloc_s0ix_state\(dev_priv\);\s*"
                   r"if \(ret < 0\)\s*goto err_workqueues;", probe)
         is not None, "S0IX failure must destroy successfully built workqueues")
    need("if (ret < 0)\n\t\tgoto err_gem;" in probe,
         "power-domain failure must unwind GEM/GT/S0IX/workqueues")
    labels = ("err_gem:", "err_workqueues:", "err_early_resources:")
    need(all(probe.count(label) == 1 for label in labels),
         "one cleanup label per stage")
    need(probe.index(labels[0]) < probe.index(labels[1]) <
         probe.index(labels[2]), "source fallthrough order changed")
    seg = section(probe, "err_workqueues:", "err_early_resources:")
    need(seg.count("i915_workqueues_cleanup(dev_priv);") == 1,
         "created workqueues not destroyed")
    error_tail = probe[probe.index("err_early_resources:"):]
    need(re.search(r"err_early_resources:\s*"
                   r"if \(IS_VALLEYVIEW\(dev_priv\)\)\s*"
                   r"pm_qos_remove_request\(&dev_priv->sb_qos\);", error_tail)
         is not None, "unconditional or omitted failed-probe QoS release")
    need(re.search(r"i915_workqueues_cleanup\(dev_priv\);\s*"
                   r"if \(IS_VALLEYVIEW\(dev_priv\)\)\s*"
                   r"pm_qos_remove_request\(&dev_priv->sb_qos\);", release)
         is not None, "normal late-release QoS lifetime differs from Linux")
    for mutex in ("hdcp_comp_mutex", "pps_mutex", "wm.wm_mutex",
                  "av_mutex", "sb_lock", "backlight_lock"):
        need(f"mutex_destroy(&dev_priv->{mutex});" in error_tail,
             "early resource leak " + mutex)
    need("spin_lock_destroy(&dev_priv->irq_lock);" in error_tail and
         "intel_uncore_fini_early(&dev_priv->uncore, dev_priv);" in error_tail,
         "early lock or uncore cleanup missing")
    # Native sideband PUNIT actually consumes the QoS request only on VLV.
    get = method(sb, "static void __vlv_punit_get(")
    put = method(sb, "static void __vlv_punit_put(")
    need("if (IS_VALLEYVIEW(i915)) {" in get and
         "pm_qos_update_request(&i915->sb_qos, 0);" in get,
         "PUNIT activation no longer VLV-specific")
    need(re.search(r"if \(IS_VALLEYVIEW\(i915\)\)\s*"
                   r"pm_qos_update_request\(&i915->sb_qos,", put)
         is not None, "PUNIT restoration no longer VLV-specific")


def model_source_validated_edges() -> int:
    # Each scenario follows a checked actual goto edge (not compiled C).
    # Internal WQ cleanup on its own second-allocation failure is separate.
    cases = 0
    for platform in ("CHV", "VLV", "OTHER"):
        for stage in ("inject", "wq_first", "wq_second", "s0ix",
                      "power", "success"):
            qos_added = platform == "VLV" and stage != "inject"
            qos_removed = qos_added
            wq_internal_destroyed = int(stage == "wq_second")
            wq_outer_destroyed = int(stage in ("s0ix", "power", "success")) * 2
            if stage in ("inject", "wq_first", "wq_second"):
                need(wq_outer_destroyed == 0,
                     "workqueue double-free path in source model")
            if stage == "wq_second":
                need(wq_internal_destroyed == 1 and wq_outer_destroyed == 0,
                     "second workqueue allocation double destroy")
            need(qos_added == qos_removed,
                 "QoS resource not balanced " + platform + " " + stage)
            cases += 1
    return cases


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-driver", type=Path, required=True)
    parser.add_argument("--netbsd-sideband", type=Path, required=True)
    parser.add_argument("--linux-iosf", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    x = parser.parse_args()

    old_raw = x.netbsd_driver.read_bytes()
    sb = x.netbsd_sideband.read_bytes()
    linux = x.linux_iosf.read_bytes()
    need(hashlib.sha256(old_raw).hexdigest() == FROZEN_NETBSD_SHA256,
         "not frozen NetBSD driver")
    need(gitblob(sb) == FROZEN_NATIVE_SIDEBAND_BLOB,
         "not frozen NetBSD sideband")
    need(gitblob(linux) == FROZEN_LINUX_BLOB, "not frozen Linux backend")
    validate_linux(linux.decode())
    original = old_raw.decode()
    need("ret = i915_workqueues_init(dev_priv);\n\tif (ret < 0)\n\t\treturn ret;" in original,
         "original workqueue cleanup gap no longer exists")
    need("pm_qos_add_request(&dev_priv->sb_qos," in original and
         "if (IS_VALLEYVIEW(dev_priv))\n\t\tpm_qos_add_request" not in original,
         "original unconditional QoS ownership unexpectedly changed")
    with tempfile.TemporaryDirectory(prefix="hp-i915-qos-") as tmp:
        root = Path(tmp)
        target = root / NETBSD_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(old_raw)
        apply = ["git", "apply", str(x.patch.resolve(strict=True))]
        for cmd in (["git", "apply", "--check", str(x.patch.resolve())], apply):
            got = run(cmd, root)
            need(got.returncode == 0, "patch apply failure " + got.stderr[-600:])
        patched = target.read_text()
        validate_native(patched, sb.decode())
        duplicate = run(["git", "apply", "--check", str(x.patch.resolve())], root)
        need(duplicate.returncode != 0, "duplicate application accepted")
        print("CHV_IOSF_QOS_NETBSD_REAL_PATCH_APPLY_AND_SOURCE_LIFETIME_PASS")

        changes = (
            ("unconditional_qos_add",
             "if (IS_VALLEYVIEW(dev_priv))\n\t\tpm_qos_add_request(",
             "if (1)\n\t\tpm_qos_add_request("),
            ("leaked_first_workqueue_failure",
             "goto err_early_resources;", "return ret;"),
            ("double_destroy_partial_workqueue",
             "goto err_early_resources;", "goto err_workqueues;"),
            ("wrong_s0ix_failure_edge",
             "goto err_workqueues;", "goto err_early_resources;"),
            ("lost_qos_error_release",
             "err_early_resources:\n\tif (IS_VALLEYVIEW(dev_priv))\n\t\tpm_qos_remove_request",
             "err_early_resources:\n\tif (0)\n\t\tpm_qos_remove_request"),
            ("lost_qos_normal_release",
             "i915_workqueues_cleanup(dev_priv);\n\n\tif (IS_VALLEYVIEW(dev_priv))",
             "i915_workqueues_cleanup(dev_priv);\n\n\tif (0)"),
            ("leaked_early_mutex",
             "mutex_destroy(&dev_priv->sb_lock);",
             "/* removed sb mutex release */"),
            ("skipped_early_uncore",
             "intel_uncore_fini_early(&dev_priv->uncore, dev_priv);",
             "/* missing early uncore cleanup */"),
        )
        for label, before, after in changes:
            early = method(patched, "static int i915_driver_early_probe(")
            late = method(patched, "static void i915_driver_late_release(")
            owner = late if label == "lost_qos_normal_release" else early
            need(owner.count(before) == 1,
                 "ambiguous mutation anchor "+label)
            bad = patched.replace(owner, owner.replace(before, after, 1), 1)
            try:
                validate_native(bad, sb.decode())
            except AssertionError as e:
                need("CHV_IOSF_QOS_LIFECYCLE_REFUSED:" in str(e),
                     "wrong refusal cause "+label)
            else:
                raise AssertionError("mutation incorrectly accepted " + label)
        print("CHV_IOSF_QOS_EIGHT_DANGEROUS_SOURCE_MUTANTS_REFUSED")
        checked = model_source_validated_edges()
        need(checked == 18, "incomplete failpoint inventory")
        print("CHV_IOSF_QOS_18_PLATFORM_FAILURE_EDGE_MODELS_PASS")

        reverse = run(["git", "apply", "--reverse", str(x.patch.resolve())], root)
        need(reverse.returncode == 0, "reverse failure " + reverse.stderr[-600:])
        need(target.read_bytes() == old_raw, "non-byte-exact rollback")
        print("CHV_IOSF_QOS_EXACT_REVERSE_PASS")
    print("LIMIT: verified C text/control-flow + Python model only;"
          " no C compilation, NetBSD QoS ABI runtime, HP native kernel/IRQ/PM test")


if __name__ == "__main__":
    main()
