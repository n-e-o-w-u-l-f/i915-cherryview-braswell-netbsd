#!/usr/bin/env python3
"""Source-only acceptance for isolated NetBSD i915 0045 eDP short HPD guard.

Includes 16 negative mutants, including fail-closed wakeref/PM-domain and
strict panel-power OR semantics. Source-only, not a concurrency proof.

Reads byte-exact pinned C and NetBSD's PM shim. Runs git apply/check/reverse
ONLY in a temporary directory. This does not compile NetBSD, touch a live HP,
validate real PM races or establish physical display acceptance.

Do not execute via a provider-denied equivalent route; retain NOT_RUN until
the user/tool/host actually authorizes this source regression.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

PATH_DP = "sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c"
BLOB_DP = "1dd8858b2d331906190258c8602af55966ff986c"
BLOB_PM = "01d2e138590ff25d549a135545e3b68c39d9205c"
BLOB_POWER = "b11bfb6dfc8d67877770c0820c23d6541188cd10"
BLOB_HOTPLUG = "722edbed2be6b1c4b2d06269572a977e6ca7adef"


def fail(message: str) -> None:
    raise AssertionError("CHV_EDP_HPD0045_REFUSED: " + message)


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()


def exact(path: Path, sha: str) -> str:
    raw = path.read_bytes()
    if blob(raw) != sha:
        fail("wrong frozen source blob " + path.name)
    return raw.decode("utf-8")


def function(source: str, name: str) -> str:
    pattern = (r"(?m)^(?:static\s+)?(?:inline\s+)?(?:bool|int|enum irqreturn|intel_wakeref_t|void)\s+"
               + re.escape(name) + r"\([^;]*?\)\s*\{")
    hit = re.search(pattern, source, flags=re.DOTALL)
    if not hit:
        fail("missing function " + name)
    end = source.find("\n}\n", hit.end())
    if end == -1:
        fail("unterminated source function " + name)
    return source[hit.start():end + 3]


def require_order(source: str, expressions: tuple[str, ...]) -> None:
    found = [source.find(item) for item in expressions]
    if -1 in found or any(a >= b for a, b in zip(found, found[1:])):
        fail("missing or reordered source ownership " + repr(expressions))


def audit(dp: str, pm: str, power: str, hotplug: str) -> None:
    shim = function(pm, "pm_runtime_get_if_in_use")
    if not re.search(r"return\s+1\s*;", shim):
        fail("NetBSD non-discriminating runtime PM shim baseline changed")
    if re.search(r"return\s+[02]\s*;", shim):
        fail("NetBSD runtime PM shim baseline unexpectedly changed")
    has_power = function(power, "intel_display_power_get_if_enabled")
    if ("intel_runtime_pm_get_if_in_use" not in has_power or
            "__intel_display_power_is_enabled" not in has_power):
        fail("display power conditional acquisition lost its two prerequisites")
    worker = function(hotplug, "intel_hpd_cancel_work")
    if "cancel_work_sync(&dev_priv->hotplug.dig_port_work)" not in worker:
        fail("system suspend no longer drains digport worker")
    power_check = function(dp, "intel_dp_edp_hpd_panel_powered")
    require_order(power_check, (
        "if (!dev_priv->runtime_pm.irqs_enabled ||",
        "dev_priv->power_domains.display_core_suspended)",
        "intel_display_power_get_if_enabled(dev_priv, domain)",
        "if (!wakeref)",
        "mutex_lock(&dev_priv->pps_mutex)",
        "powered = dev_priv->runtime_pm.irqs_enabled &&",
        "!dev_priv->power_domains.display_core_suspended &&",
        "edp_have_panel_power(intel_dp)",
        "edp_have_panel_vdd(intel_dp)",
        "mutex_unlock(&dev_priv->pps_mutex)",
        "intel_display_power_put(dev_priv, domain, wakeref)",
        "return powered;",
    ))
    # Check boolean/branch semantics, not just presence/order of operands.
    # Otherwise simple &&/|| or return-value mutations evade the old test.
    if power_check.count("intel_aux_power_domain(dp_to_dig_port(intel_dp))") != 1:
        fail("guard no longer acquires the exact eDP AUX power domain")
    if not re.search(
        r"if\s*\(!dev_priv->runtime_pm\.irqs_enabled\s*\|\|\s*"
        r"dev_priv->power_domains\.display_core_suspended\)\s*return false;",
        power_check,
    ):
        fail("early suspend gate no longer returns false")
    if not re.search(r"if\s*\(!wakeref\)\s*return false;", power_check):
        fail("failed conditional wakeref acquisition not safely rejected")
    if not re.search(
        r"powered\s*=\s*dev_priv->runtime_pm\.irqs_enabled\s*&&\s*"
        r"!dev_priv->power_domains\.display_core_suspended\s*&&\s*"
        r"\(\s*edp_have_panel_power\(intel_dp\)\s*\|\|\s*"
        r"edp_have_panel_vdd\(intel_dp\)\s*\);",
        power_check,
    ):
        fail("locked panel/VDD OR predicate or suspend gating changed")
    if power_check.count("intel_display_power_get_if_enabled(dev_priv, domain)") != 1:
        fail("conditional domain acquisition missing or duplicated")
    if power_check.count("intel_display_power_put(dev_priv, domain, wakeref);") != 1:
        fail("wakeref/domain must be released exactly once")

    if "edp_panel_vdd_on" in power_check or "intel_display_power_get(dev_priv" in power_check:
        fail("guard itself resumes or forces VDD")
    hp = function(dp, "intel_dp_hpd_pulse")
    if ("if (intel_dig_port->base.type == INTEL_OUTPUT_EDP &&\n"
            "\t    (long_hpd || !intel_dp_edp_hpd_panel_powered(intel_dp)))" not in hp):
        fail("guard widened beyond eDP, removed long HPD or lost short guard")
    if 'long_hpd ? "long" : "short"' not in hp:
        fail("incorrect short/long hotplug diagnostic")


def run(args: list[str], cwd: Path) -> None:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        fail("git apply scratch failed: " + proc.stderr[-600:])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-dp", type=Path, required=True)
    p.add_argument("--netbsd-pm-shim", type=Path, required=True)
    p.add_argument("--netbsd-power", type=Path, required=True)
    p.add_argument("--netbsd-hotplug", type=Path, required=True)
    p.add_argument("--patch", type=Path, required=True)
    a = p.parse_args()
    frozen = a.netbsd_dp.read_bytes()
    if blob(frozen) != BLOB_DP:
        fail("pinned NetBSD DP file mismatch")
    pm = exact(a.netbsd_pm_shim, BLOB_PM)
    power = exact(a.netbsd_power, BLOB_POWER)
    hotplug = exact(a.netbsd_hotplug, BLOB_HOTPLUG)

    if "intel_dp_edp_hpd_panel_powered" in frozen.decode("utf-8"):
        fail("0045 already present in frozen baseline")
    with tempfile.TemporaryDirectory(prefix="chv-edp-hpd0045-") as d:
        root = Path(d)
        dest = root / PATH_DP
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(frozen)
        patch = str(a.patch.resolve(strict=True))
        run(["git", "apply", "--check", patch], root)
        run(["git", "apply", patch], root)
        accepted = dest.read_text(encoding="utf-8")
        audit(accepted, pm, power, hotplug)
        print("CHV_EDP_HPD0045_PINNED_SOURCE_GUARD_PASS")

        helper = function(accepted, "intel_dp_edp_hpd_panel_powered")
        hp = function(accepted, "intel_dp_hpd_pulse")
        mutations = (
            ("wrong_aux_domain", helper,
             "intel_aux_power_domain(dp_to_dig_port(intel_dp))",
             "POWER_DOMAIN_INIT"),
            ("failed_wakeref_returns_true", helper,
             "if (!wakeref)\n\t\treturn false;",
             "if (!wakeref)\n\t\treturn true;"),
            ("early_suspend_gate_returns_true", helper,
             "dev_priv->power_domains.display_core_suspended)\n\t\treturn false;",
             "dev_priv->power_domains.display_core_suspended)\n\t\treturn true;"),
            ("panel_power_and_instead_of_or", helper,
             "edp_have_panel_power(intel_dp) ||",
             "edp_have_panel_power(intel_dp) &&"),
            ("duplicate_power_put", helper,
             "intel_display_power_put(dev_priv, domain, wakeref);",
             "intel_display_power_put(dev_priv, domain, wakeref);\n"
             "\tintel_display_power_put(dev_priv, domain, wakeref);"),
            ("powered_predicate_or_instead_of_and", helper,
             "powered = dev_priv->runtime_pm.irqs_enabled &&",
             "powered = dev_priv->runtime_pm.irqs_enabled ||"),
            ("irq_gate_missing", helper,
             "if (!dev_priv->runtime_pm.irqs_enabled ||",
             "if (false ||"),
            ("display_suspend_gate_missing", helper,
             "dev_priv->power_domains.display_core_suspended)",
             "false)"),
            ("unconditional_power_get", helper,
             "intel_display_power_get_if_enabled(dev_priv, domain)",
             "intel_display_power_get(dev_priv, domain)"),
            ("pps_mutex_missing", helper,
             "mutex_lock(&dev_priv->pps_mutex);",
             "/* mutex lock removed */"),
            ("pps_unlock_missing", helper,
             "mutex_unlock(&dev_priv->pps_mutex);",
             "/* mutex unlock removed */"),
            ("wakeref_leak", helper,
             "intel_display_power_put(dev_priv, domain, wakeref);",
             "/* no put */"),
            ("vdd_test_removed", helper,
             "edp_have_panel_vdd(intel_dp)",
             "false"),
            ("locked_second_suspend_check_removed", helper,
             "!dev_priv->power_domains.display_core_suspended &&",
             "true &&"),
            ("external_dp_affected", hp,
             "intel_dig_port->base.type == INTEL_OUTPUT_EDP",
             "true"),
            ("long_edp_no_suppression", hp,
             "(long_hpd || !intel_dp_edp_hpd_panel_powered(intel_dp))",
             "(!long_hpd && !intel_dp_edp_hpd_panel_powered(intel_dp))"),
        )
        for label, scope, old, new in mutations:
            if scope.count(old) != 1:
                fail("nonunique test mutation: " + label)
            altered = accepted.replace(scope, scope.replace(old, new, 1), 1)
            try:
                audit(altered, pm, power, hotplug)
            except AssertionError as exc:
                if not str(exc).startswith("CHV_EDP_HPD0045_REFUSED:"):
                    raise
            else:
                fail("dangerous mutation accepted: " + label)
        print("CHV_EDP_HPD0045_SIXTEEN_MUTATIONS_REFUSED")
        run(["git", "apply", "--reverse", patch], root)
        if dest.read_bytes() != frozen:
            fail("failed to restore exact frozen source on reverse")
        print("CHV_EDP_HPD0045_BYTE_EXACT_REVERSE_PASS")
        print("LIMIT: source model only; no native compile, real PM lifecycle, race"
              " resolution, physical HP KMS or boot acceptance.")


if __name__ == "__main__":
    main()
