#!/usr/bin/env python3
"""Fail-closed source-only Intel i915 parent/display callback provider audit."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PREFIX = "external/bsd/drm2/dist/drm/i915/"
PIN = "bf203599dde029eca7dade66c70ea3f00754e49da00f47a8d7b05c0bffee8cbe"
DIRECT = {"fence_priority_display", "has_auxccs", "has_fenced_regions", "vgpu_active"}
ORDER = ("pci_enable_device", "i915_driver_create", "intel_display_device_probe",
         "i915_driver_early_probe", "intel_gt_probe_all", "i915_driver_mmio_probe",
         "i915_driver_hw_probe", "intel_display_driver_probe_noirq",
         "intel_irq_install", "intel_display_driver_probe_nogem",
         "i915_gem_init", "intel_display_driver_probe", "i915_driver_register")


def read_units(root: Path, manifest: Path, expected: int = 323) -> dict[str, str]:
    root = root.resolve(strict=True)
    result = {}
    for line in manifest.read_text().splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[0] != "file" or not fields[1].startswith(PREFIX) or fields[2] != "i915drmkms":
            raise ValueError("invalid pinned active filelist")
        name = fields[1][len(PREFIX):]
        if name in result or Path(name).is_absolute() or ".." in Path(name).parts or not name.endswith(".c"):
            raise ValueError("duplicate/unsafe translation unit")
        source = (root / name).resolve(strict=True)
        if not source.is_relative_to(root):
            raise ValueError("source outside frozen Linux tree")
        result[name] = source.read_text(errors="replace")
    if len(result) != expected:
        raise ValueError("incomplete active translation units")
    return result


def body(header: str, struct: str) -> str:
    pat = r"\bstruct\s+" + re.escape(struct) + r"\s*\{([\s\S]*?)\n\};"
    matches = re.findall(pat, header)
    if len(matches) != 1:
        raise ValueError("struct missing/ambiguous: " + struct)
    return matches[0]


def members(struct_content: str) -> set[str]:
    cleaned = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", struct_content)
    cleaned = re.sub(r"(?m)^\s*#.*$", "", cleaned)
    out = []
    for piece in cleaned.split(";"):
        # Only the first declarator in each struct member, not (*tiling)
        # nested as a parameter to the panic setup() method.
        match = re.search(r"\(\*\s*([a-z_]\w*)\s*\)\s*\(", piece)
        if match:
            out.append(match.group(1))
    if len(out) != len(set(out)):
        raise ValueError("duplicate struct method")
    return set(out)


def audit(units: dict[str, str], header: str, check_pin: bool = True) -> dict:
    sha = hashlib.sha256(header.encode()).hexdigest()
    if check_pin and sha != PIN:
        raise ValueError("reference interface SHA256 mismatch")
    if len(units) != 323:
        raise ValueError("all 323 selected Linux C units are required")
    for essential in ("i915_driver.c", "display/intel_parent.c",
                      "display/intel_display_device.c"):
        if essential not in units:
            raise ValueError("missing essential driver source: " + essential)
    parent = body(header, "intel_display_parent_interface")
    fields = re.findall(
        r"\bconst\s+struct\s+intel_display_([a-z_][a-z0-9_]*)_interface"
        r"\s*\*\s*([a-z_][a-z0-9_]*)\s*;", parent)
    if len(fields) != 16 or any(t != n for t, n in fields):
        raise ValueError("16 top-level callback interfaces expected")
    driver = units["i915_driver.c"]
    init = re.search(
        r"static\s+const\s+struct\s+intel_display_parent_interface\s+"
        r"parent\s*=\s*\{([\s\S]*?)\n\};", driver)
    if not init:
        raise ValueError("parent initializer missing")
    entries = re.findall(r"\.([a-z_][a-z0-9_]*)\s*=\s*(&?)([a-z_][a-z0-9_]*)\s*,", init[1])
    if len(entries) != 20 or len({f for f, _, _ in entries}) != 20:
        raise ValueError("16 provider and four direct assignments expected")
    assignments = {field: (amp, symbol) for field, amp, symbol in entries}
    if set(assignments) != set(n for _, n in fields) | DIRECT:
        raise ValueError("unexpected/missing parent assignment")
    if any(assignments[k][0] for k in DIRECT) or any(
        assignments[k][0] != "&" for _, k in fields):
        raise ValueError("function vs struct-provider assignment mismatch")
    if not re.search(r"if\s*\(\s*!display->parent->fb_pin->reuse_vma\s*\)",
                     units["display/intel_parent.c"]):
        raise ValueError("fb_pin reuse_vma NULL-check lost")
    report = {}
    for kind, field in fields:
        symbol = assignments[field][1]
        typ = "intel_display_" + kind + "_interface"
        declared = members(body(header, typ))
        if symbol != "i915_display_" + kind + "_interface":
            raise ValueError("provider symbol unexpected")
        matcher = re.compile(
            r"\bconst\s+struct\s+" + re.escape(typ) + r"\s+" +
            re.escape(symbol) + r"\s*=\s*\{([\s\S]*?)\n\};")
        owner = [(name, match[1]) for name, text in units.items()
                 for match in matcher.finditer(text)]
        if len(owner) != 1:
            raise ValueError("provider missing/ambiguous: " + symbol)
        path, declaration = owner[0]
        assigned_methods = re.findall(r"\.([a-z_][a-z0-9_]*)\s*=", declaration)
        if len(assigned_methods) != len(set(assigned_methods)):
            raise ValueError("duplicate provider method")
        missing = declared - set(assigned_methods)
        extra = set(assigned_methods) - declared
        allowed = {"reuse_vma"} if field == "fb_pin" else set()
        if missing - allowed or extra:
            raise ValueError("provider missing/unknown methods: " + field +
                             " " + str(sorted(missing)) + " " + str(sorted(extra)))
        report[field] = {
            "owner": path, "symbol": symbol, "members": len(declared),
            "bound": len(assigned_methods),
            "guarded_optional_unbound": sorted(missing),
            "owner_source_sha256": hashlib.sha256(units[path].encode()).hexdigest(),
        }
    if report["vlv_iosf"]["bound"] != 4 or report["panic"]["members"] != 3:
        raise ValueError("CHV IOSF or nested panic parameter miscount")
    a = driver.index("int i915_driver_probe(")
    b = driver.index("\nvoid i915_driver_remove(", a)
    region = driver[a:b]
    positions = [region.find(item + "(") for item in ORDER]
    if -1 in positions or positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ValueError("Linux initialization order not established")
    disp = units["display/intel_display_device.c"]
    a = disp.index("struct intel_display *intel_display_device_probe(")
    b = disp.index("\nvoid intel_display_device_remove(", a)
    section = disp[a:b]
    if "display->parent = parent;" not in section or section.index("display->parent = parent;") >= section.index("find_platform_desc("):
        raise ValueError("parent pointer not assigned before platform discovery")
    return {
        "schema": "i915-parent-provider-audit/v1",
        "source_units": len(units), "provider_count": len(report),
        "declared_methods": sum(v["members"] for v in report.values()),
        "bound_methods": sum(v["bound"] for v in report.values()),
        "optional_unbound": {k:v["guarded_optional_unbound"] for k,v in report.items()
                             if v["guarded_optional_unbound"]},
        "generic_callbacks": sorted(DIRECT), "header_sha256": sha,
        "probe_order": list(ORDER), "providers": report,
        "native_netbsd_abi_verified": False,
        "limits": "source-only lexical audit; no CPP/Kconfig, runtime binding, C ABI, NetBSD kernel linkage or hardware KMS",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-i915", type=Path, required=True)
    parser.add_argument("--filelist", type=Path, required=True)
    parser.add_argument("--interface", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    state = audit(read_units(args.linux_i915,args.filelist),
                  args.interface.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    print("I915_ALL_16_PARENT_PROVIDER_SOURCE_AUDIT_PASS")
    print(json.dumps({k:state[k] for k in
                      ("source_units","provider_count","declared_methods",
                       "bound_methods","optional_unbound")}, sort_keys=True))


if __name__ == "__main__":
    main()
