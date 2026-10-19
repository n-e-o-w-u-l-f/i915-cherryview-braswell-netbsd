#!/usr/bin/env python3
"""Pinned CHV PUNIT/PMIC shared-I2C boundary audit (source-only).

This records the frozen NetBSD gap; passing its BASELINE checks means
the missing Intel ACPI IDs + missing _SEM arbitration remain UNFIXED.
Tests deliberately reject enabling the Intel controller without safe
kernel-global PUNIT/PMIC I2C arbitration. Never run an HP kernel here.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

PINS = {
    "linux_platform": "447af5523c2e4fc74e93f3cd22f8f0b380617e9c",
    "linux_baytrail": "45774aa47c28c65c510b523eddc08348de30cfd4",
    "linux_mbi": "40ae94db20d8e31d6812a119095e079e9a627d8",
    "netbsd_acpi": "6c8b32c817022f34d4f36b24c1cf94b8e7d5a9b7",
    "netbsd_core": "258490c8ac6a67e0715640047f86acd1fe44525f",
    "netbsd_var": "2e3f9682c1b6067028abf984675d3b16663c3e32",
    "netbsd_i2c": "eb2c009b3fb7153c68a62d5cc7d659ba949e5117",
    "netbsd_mbi": "b72c89aed5d1e0ad258c0dd8a6561eafe6398089",
}
INTEL_HIDS = ("80860F41", "808622C1")


def refuse(reason: str):
    raise ValueError("CHV_PUNIT_DWIIC_BOUNDARY_REFUSED: " + reason)


def blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def no_op(src: str, symbol: str) -> bool:
    m = re.search(r"\b" + re.escape(symbol) +
                  r"\s*\([^;{}]{0,250}\)\s*\{\s*\}", src)
    return bool(m)


def audit(base: dict[str, str]) -> None:
    lp, lb, lm = (base[k] for k in ("linux_platform", "linux_baytrail", "linux_mbi"))
    na, nc, nv, ni, nm = (base[k] for k in (
        "netbsd_acpi", "netbsd_core", "netbsd_var",
        "netbsd_i2c", "netbsd_mbi"
    ))
    # Linux's Intel controllers are eligible only when ACPI matches;
    # Bay Trail _SEM is an additional, conditional lock requirement.
    for hid in INTEL_HIDS:
        if not re.search(r'\{\s*"' + hid + r'"\s*,', lp):
            refuse("pinned Linux Intel ACPI support changed " + hid)
    for seq in (
        'acpi_evaluate_integer(handle, "_SEM", NULL, &shared_host)',
        "if (!shared_host)",
        "if (!iosf_mbi_available())",
        "dev->acquire_lock = iosf_mbi_block_punit_i2c_access;",
        "dev->release_lock = iosf_mbi_unblock_punit_i2c_access;",
        "dev->shared_with_punit = true;",
    ):
        if seq not in lb:
            refuse("upstream conditional Bay Trail PMIC arbiter missing " + seq)
    for seq in (
        "iosf_mbi_pmic_access_mutex",
        "iosf_mbi_pmic_punit_access_count",
        "iosf_mbi_pmic_i2c_access_count",
        "wait_event(iosf_mbi_pmic_access_waitq",
        "iosf_mbi_block_punit_i2c_access(void)",
        "iosf_mbi_unblock_punit_i2c_access(void)",
    ):
        if seq not in lm:
            refuse("upstream shared cross-driver PMIC/PUNIT logic missing " + seq)

    # Frozen NetBSD has a real ACPI DesignWare controller and an I2C
    # bus hook mechanism, but does not attach Intel CHV HIDs.
    for seq in (
        'DEVICE_COMPAT_EOL',
        'dwiic_acpi_match(',
        'dwiic_acpi_attach(',
        'acpi_resource_parse(',
        'dwiic_acpi_configure(sc, aa->aa_node->ad_handle);',
    ):
        if seq not in na:
            refuse("native ACPI driver shape changed " + seq)
    for hid in INTEL_HIDS:
        if hid in na:
            refuse("Intel HID enabled without separately reviewed _SEM arbiter " + hid)

    if '"_SEM"' in na or "iosf_mbi_block_punit_i2c_access(" in na:
        refuse("NetBSD ACPI arbiter changed; requires full new semantics review")
    if ('sc->sc_i2c_tag.ic_exec = dwiic_i2c_exec;' not in nc or
            'iic_tag_init(&sc->sc_i2c_tag);' not in nc):
        refuse("NetBSD I2C transport owner changed")
    if ("ic_acquire_bus" in nc or "ic_release_bus" in nc):
        refuse("Native core bus acquire/release wiring changed; re-audit")
    if "struct i2c_controller" not in nv:
        refuse("Native DesignWare I2C tag ownership changed")
    if "ic_acquire_bus" not in ni or "ic_release_bus" not in ni:
        refuse("NetBSD I2C framework hook support changed")
    for symbol in ("iosf_mbi_punit_acquire", "iosf_mbi_punit_release"):
        if not no_op(nm, symbol):
            refuse("NetBSD no-op MBI shim changed; requires implementation review")

    # This baseline is intentionally BLOCKED, not an accepted bridge.


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in PINS:
        parser.add_argument("--" + name.replace("_", "-"),
                            type=Path, required=True)
    x = parser.parse_args()
    actual = {}
    for name, digest in PINS.items():
        p = getattr(x, name)
        raw = p.read_bytes()
        if blob(raw) != digest:
            refuse("source identity mismatch " + name)
        actual[name] = raw.decode("utf-8")
    audit(actual)
    print("CHV_PUNIT_DWIIC_PINNED_SOURCE_GAP_IDENTIFIED")
    print("NETBSD_INTEL_ACPI_ATTACH_AND_SEM_ARBITRATION_NOT_IMPLEMENTED")
    mutation_cases = (
        ("intel_chv_hid_enabled_unprotected", "netbsd_acpi",
         "DEVICE_COMPAT_EOL", '{ .compat = "808622C1" },\n\tDEVICE_COMPAT_EOL'),
        ("intel_byt_hid_enabled_unprotected", "netbsd_acpi",
         "DEVICE_COMPAT_EOL", '{ .compat = "80860F41" },\n\tDEVICE_COMPAT_EOL'),
        ("fake_sem_marker_only", "netbsd_acpi",
         'dwiic_acpi_configure(sc, aa->aa_node->ad_handle);',
         '/* _SEM */\n\tdwiic_acpi_configure(sc, aa->aa_node->ad_handle);'),
        ("punit_stubs_changed", "netbsd_mbi",
         "iosf_mbi_punit_acquire(void)\n{\n}",
         "iosf_mbi_punit_acquire(void)\n{\n\t/* new code; review required */\n}"),
        ("linux_sem_missing", "linux_baytrail",
         '"_SEM"', '"_SXM"'),
        ("linux_i2c_callback_missing", "linux_baytrail",
         "dev->release_lock = iosf_mbi_unblock_punit_i2c_access;",
         "dev->release_lock = NULL;"),
        ("netbsd_i2c_hook_missing", "netbsd_i2c",
         "ic_release_bus", "ic_no_release_bus"),
    )
    for label, name, old, new in mutation_cases:
        if actual[name].count(old) != 1:
            refuse("nonunique mutation anchor " + label)
        changed = dict(actual)
        changed[name] = changed[name].replace(old, new, 1)
        try:
            audit(changed)
        except ValueError as exc:
            if "CHV_PUNIT_DWIIC_BOUNDARY_REFUSED" not in str(exc):
                raise
        else:
            raise AssertionError("mutated unsafe state accepted: " + label)
    print("CHV_PUNIT_DWIIC_SEVEN_UNSAFE_SOURCE_CHANGES_REFUSED")
    print("STATUS: BLOCKED_KERNEL_INTEGRATION; NO NATIVE COMPILE OR HP ACPI PROOF")


if __name__ == "__main__":
    main()
