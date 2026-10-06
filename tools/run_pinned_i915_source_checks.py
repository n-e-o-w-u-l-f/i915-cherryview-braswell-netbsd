#!/usr/bin/env python3
"""Run pinned, isolated i915 error-path regressions on the permitted build host.

Accept a clean frozen NetBSD git checkout and a clean pinned Linux checkout.
Optionally check a separate *real* six-edit NetBSD port overlay. Never pass
the frozen checkout again as the overlay: it would be misleading evidence.
Only source/patched-function host C and patch application are checked;
this is not a native NetBSD kernel build or hardware verification.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"


def git_head(tree: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], text=True
    ).strip()


def invoke(script: str, *arguments: str) -> None:
    print("RUN", script, flush=True)
    subprocess.run([sys.executable, str(ROOT / "tests" / script),
                    *arguments], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", type=Path, required=True)
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--overlay-tree", type=Path, default=None,
                    help="optional actual unpublished six-edit port overlay")
    args = ap.parse_args()

    netbsd = args.netbsd_tree.resolve(strict=True)
    linux = args.linux_tree.resolve(strict=True)
    if netbsd == linux:
        raise RuntimeError("Linux and NetBSD reference paths must differ")
    if git_head(netbsd) != NETBSD_PIN or git_head(linux) != LINUX_PIN:
        raise RuntimeError("wrong frozen NetBSD/Linux reference revision")
    overlay = None
    if args.overlay_tree is not None:
        overlay = args.overlay_tree.resolve(strict=True)
        if overlay in (netbsd, linux):
            raise RuntimeError("real unpublished overlay must be distinct")
        if git_head(overlay) != NETBSD_PIN:
            raise RuntimeError("unpublished overlay has wrong NetBSD base")
    p3 = (ROOT / "patches/0003-vlv-chv-pipe-msa-misc-linux-c931ef00-netbsd11.patch").resolve(strict=True)
    p7 = (ROOT / "patches/0007-i915-early-probe-resource-unwind-netbsd11.patch").resolve(strict=True)
    p8 = (ROOT / "candidates/0008-i915-drm-registration-unwind-netbsd11.patch").resolve(strict=True)
    p9 = (ROOT / "candidates/0009-netbsd-opregion-optional-asle-cleanup.patch").resolve(strict=True)
    p10 = (ROOT / "candidates/0010-netbsd-opregion-rvda-map-failure-unwind.patch").resolve(strict=True)
    p11 = (ROOT / "candidates/0011-i915-edp-reject-missing-fixed-mode-netbsd11.patch").resolve(strict=True)
    p12 = (ROOT / "candidates/0012-i915-edp-dpcd-rates-failed-aux-read-netbsd11.patch").resolve(strict=True)
    p13 = (ROOT / "candidates/0013-i915-edp-aux-poll-when-irqs-disabled-netbsd11.patch").resolve(strict=True)
    p14 = (ROOT / "candidates/0014-i915-chv-aux-precharge-linux-parity-netbsd11.patch").resolve(strict=True)
    p15 = (ROOT / "candidates/0015-i915-chv-phy-control-powerwell-sync-netbsd11.patch").resolve(strict=True)
    p16 = (ROOT / "candidates/0016-i915-gen8-ppgtt-vm-init-error-unwind-netbsd11.patch").resolve(strict=True)
    p17 = (ROOT / "candidates/0017-i915-gen6-ppgtt-vm-flush-error-unwind-netbsd11.patch").resolve(strict=True)

    overlay_args = ["--overlay-tree", str(overlay)] if overlay else []
    invoke("test_materialize_linux_i915.py")
    invoke("test_linux_memory_ordering.py", "--netbsd-tree", str(netbsd), "--apply-candidate")
    invoke("test_linux_kconfig.py", "--netbsd-tree", str(netbsd))
    invoke("test_linux_posix_types.py", "--netbsd-tree", str(netbsd), "--apply-candidate")
    invoke("test_linux_rbtree.py", "--netbsd-tree", str(netbsd), "--apply-candidate")
    invoke("test_linux_wordsize.py", "--netbsd-tree", str(netbsd), "--apply-candidate")
    invoke("test_linux_raw_spinlock.py")
    invoke("test_linux_instruction_pointer.py", "--netbsd-tree", "/root/hp-driver-port-20261005/netbsd-full-linux")
    invoke("test_hp_shared_kconfig.py")
    invoke("test_linux_compiler_math.py")
    invoke("test_linux_math64.py")
    invoke("test_linux_completion.py")
    invoke("test_linux_typecheck_wordpart.py")
    invoke("test_linux_container.py")
    invoke("test_linux_typed_alloc.py")
    invoke("test_linux_task_wait_worker.py")
    invoke("test_linux_uuid.py")
    invoke("test_linux_pwm.py")
    invoke("test_linux_fatal_wait.py")
    invoke("test_linux_bit_wait.py")
    invoke("test_vlv_chv_audio_phase.py", "--netbsd-tree", str(netbsd))
    invoke("test_early_probe_unwind.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p7),
           *overlay_args)
    invoke("test_opregion_optional_asle.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p9))
    invoke("test_opregion_rvda_map_failure.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p10),
           "--opregion-patch", str(p9), *overlay_args)
    invoke("test_register_failure.py",
           "--netbsd-tree", str(netbsd), "--patch", str(p8),
           "--previous-patch", str(p7),
           "--opregion-patch", str(p9), *overlay_args)
    invoke("test_drm_registration_source_contract.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux))
    invoke("test_chv_dpio_routing_source_contract.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux))
    invoke("test_chv_pipe_msa_misc_reference.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p3), *overlay_args)
    invoke("test_chv_full_ppgtt_source_contract.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           *overlay_args)
    invoke("test_gen8_ppgtt_vm_init_unwind.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p16), *overlay_args)
    invoke("test_gen6_ppgtt_vm_flush_unwind.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p17), *overlay_args)
    invoke("test_ppgtt_terminal_ownership_contract.py",
           "--netbsd-tree", str(netbsd), *overlay_args)
    invoke("test_edp_aux_irq_fallback.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p13), *overlay_args)
    invoke("test_edp_fixed_mode.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p11), *overlay_args)
    invoke("test_edp_dpcd_rates.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p12), *overlay_args)
    invoke("test_chv_aux_precharge_reference.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p14), *overlay_args)
    invoke("test_chv_phy_powerwell_sync_reference.py",
           "--netbsd-tree", str(netbsd), "--linux-tree", str(linux),
           "--patch", str(p15), *overlay_args)

    # Four disjoint eDP changes may compose in any order on the frozen
    # NetBSD source. The real unpublished Legion overlay *already has*
    # precharge 0014: apply only 0011/0012/0013 to its disposable copy.
    dp_rel = Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c")
    dp_original = (netbsd / dp_rel).read_bytes()
    combined = []
    with tempfile.TemporaryDirectory() as name:
        scratch = Path(name)
        target = scratch / dp_rel
        target.parent.mkdir(parents=True)
        for pair in itertools.permutations((p11, p12, p13, p14)):
            target.write_bytes(dp_original)
            for patch in pair:
                subprocess.run(["git", "-C", str(scratch),
                                "apply", str(patch)], check=True)
            combined.append(target.read_bytes())
    if len(set(combined)) != 1 or combined[0] == dp_original:
        raise AssertionError("0011/0012/0013/0014 full permutation drift")
    print("I915_0011_TO_0014_COMBINED_REAL_GIT_APPLY_24_ORDERS_OK",
          flush=True)

    if overlay is not None:
        original_overlay_dp = (overlay / dp_rel).read_bytes()
        with tempfile.TemporaryDirectory() as name:
            scratch = Path(name)
            target = scratch / dp_rel
            target.parent.mkdir(parents=True)
            for pair in itertools.permutations((p11, p12, p13)):
                target.write_bytes(original_overlay_dp)
                for patch in pair:
                    subprocess.run(["git", "-C", str(scratch),
                                    "apply", str(patch)], check=True)
                if target.read_bytes() != combined[0]:
                    raise AssertionError(
                        "genuine six-edit overlay's eDP result diverges "
                        "from frozen NetBSD + 0011/0012/0013/0014"
                    )
        print("I915_EXISTING_0014_OVERLAY_0011_TO_0013_6_ORDERS_OK",
              flush=True)

    # Individual new changes must apply to untouched frozen input. The
    # real Legion overlay already has both 0014 AUX precharge and 0015
    # PHY power-well sync; verify their reverse applicability separately.
    for tree in ([netbsd, overlay] if overlay else [netbsd]):
        assert tree is not None
        changes = (p7, p8, p9, p10, p11, p12, p13, p16, p17)
        if tree == netbsd:
            changes += (p14, p15)
        for patch in changes:
            subprocess.run(["git", "-C", str(tree), "apply",
                            "--check", str(patch)], check=True)

    # Integration gate: apply 0007-0013 + 0014/0015 + 0016/0017 to frozen
    # files; apply 0007-0013 + 0016/0017 to genuine overlay (which already
    # contains 0014 and 0015).
    # Include the *real* overlay files only if the
    # caller supplied a distinct checkout. Never mutate the reference,
    # published patch artifacts, or the user's unpublished overlay.
    sources = (
        Path("sys/external/bsd/drm2/dist/drm/i915/i915_drv.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_opregion.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/display/intel_display_power.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/gt/gen8_ppgtt.c"),
        Path("sys/external/bsd/drm2/dist/drm/i915/gt/gen6_ppgtt.c"),
    )
    new_stack = (p7, p8, p9, p10, p11, p12, p13, p16, p17)
    fingerprints = {}
    for tree in ([netbsd, overlay] if overlay else [netbsd]):
        assert tree is not None
        originals = {relative: (tree / relative).read_bytes()
                     for relative in sources}
        with tempfile.TemporaryDirectory() as name:
            scratch = Path(name)
            for relative, content in originals.items():
                dest = scratch / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            patches = new_stack + ((p14, p15) if tree == netbsd else ())
            for patch in patches:
                subprocess.run(
                    ["git", "-C", str(scratch), "apply", str(patch)],
                    check=True,
                )
            changed = {relative: (scratch / relative).read_bytes()
                       for relative in sources}
            # The overlay already has 0015 in intel_display_power.c:
            # its power file must remain unchanged after the seven NEW
            # patches. Frozen NetBSD must instead receive 0015 here.
            expected_mutated = sources if tree == netbsd else (
                sources[0], sources[1], sources[2], sources[4], sources[5]
            )
            if any(changed[relative] == originals[relative]
                   for relative in expected_mutated):
                raise AssertionError(
                    "complete patch stack left a target source unchanged"
                )
            if tree == overlay and changed[sources[3]] != originals[sources[3]]:
                raise AssertionError("existing staged power-well source changed")
            driver = changed[sources[0]].decode("utf-8")
            opregion = changed[sources[1]].decode("utf-8")
            dp = changed[sources[2]].decode("utf-8")
            power = changed[sources[3]].decode("utf-8")
            ppgtt = changed[sources[4]].decode("utf-8")
            gen6_ppgtt = changed[sources[5]].decode("utf-8")
            required = (
                (driver, "out_cleanup_registration:"),
                (driver, "err_early:"),
                (opregion, "opregion->rvda ? opregion->asle->rvds : 0;"),
                (opregion, "if (opregion->rvda)\n"
                 "\t\t\t\tAcpiOsUnmapMemory(opregion->rvda,"),
                (dp, 'DRM_INFO("failed to find fixed mode for eDP,'),
                (dp, "(ssize_t)sizeof(sink_rates)) {"),
                (dp, "if (!cold && i915->drm.irq_enabled &&"),
                (dp, "(3 << DP_AUX_CH_CTL_PRECHARGE_2US_SHIFT) |"),
                (power, ".sync_hw = chv_pipe_power_well_sync_hw,"),
                (power, "Defer application of initial phy_control to enabling the powerwell"),
                (ppgtt, "i915_address_space_fini(&ppgtt->vm);"),
                (gen6_ppgtt, "i915_address_space_fini(&ppgtt->base.vm);"),
                (gen6_ppgtt, "mutex_destroy(&ppgtt->flush);"),
            )
            for content, anchor in required:
                if anchor not in content:
                    raise AssertionError(
                        "complete stack lost required change: " + anchor
                    )
            fingerprint = hashlib.sha256(
                b"".join(changed[relative] for relative in sources)
            ).hexdigest()
        scope = "OVERLAY" if overlay is not None and tree == overlay else "FROZEN"
        fingerprints[scope] = fingerprint
        print("I915_0007_TO_0017_PARITY_COMBINED_REAL_GIT_APPLY_" +
              scope + "_OK sha256=" + fingerprint, flush=True)

    if overlay is not None:
        if fingerprints["FROZEN"] != fingerprints["OVERLAY"]:
            raise AssertionError("real overlay + new patches differs from "
                                 "frozen NetBSD + all nine patches")
        print("I915_FROZEN_9_PATCH_VS_EXISTING_0014_0015_OVERLAY_PARITY_OK",
              flush=True)

    print("I915_PINNED_SOURCE_CHECKS_PASS_" +
          ("FROZEN_AND_OVERLAY" if overlay else "FROZEN_ONLY"),
          flush=True)
    print("LIMITATION: host C/source and patch applicability only; "
          "NetBSD object/kernel build and HP display runtime NOT TESTED",
          flush=True)


if __name__ == "__main__":
    main()
