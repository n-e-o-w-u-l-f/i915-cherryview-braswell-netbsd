#!/usr/bin/env python3
"""Pinned source-level CHV/VLV IOSF unit and native DPIO semantic contract.

This tests observed source-level route/locking/error-state invariants,
NOT a native NetBSD kernel C compile, all-function source equivalence,
GPIO/PUNIT lifetime parity or physical PHY behavior.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess

LINUX_PIN = "068f58bd9a2b2229e2792fca06de455c0a1d797f"
NETBSD_SIDEBAND_PIN = "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed"
NETBSD_DRV_PIN = "bf64ff40059fc38188f6f3d7b55bef9793abeb57"
NETBSD_HEADER_PIN = "ce1919f9d0aff7f7c6b4d4534dbc61b7a6ce37ea"

def gitblob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def need(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError("CHV_IOSF_SEMANTIC_REFUSED: " + reason)

def func(src: str, name: str) -> str:
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;{}]{0,350}\)\s*\{", src)
    need(match is not None, "function missing: " + name)
    start = match.start()
    brace = src.index("{", match.start())
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{": depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0: return src[start:i + 1]
    raise ValueError("unbalanced function " + name)

def source_contract(linux: str, native: str, driver: str, header: str,
                    reg: str) -> dict:
    # Real CHV routing: modern Linux uses PHY identity; native NetBSD
    # uses an early-initialized PHY-port array indexed by DPIO_PHY(pipe).
    lphy = func(linux, "vlv_dpio_phy_to_unit")
    init = func(driver, "intel_init_dpio")
    early = func(driver, "i915_driver_early_probe")
    need("if (display->platform.cherryview)" in lphy and
         "return phy == DPIO_PHY0 ? VLV_IOSF_SB_DPIO_2 : VLV_IOSF_SB_DPIO;" in lphy,
         "Linux CHV PHY0 vs PHY1 target mapping changed")
    need("return VLV_IOSF_SB_DPIO;" in lphy,
         "Linux VLV target unit changed")
    need("if (IS_CHERRYVIEW(dev_priv))" in init and
         "DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO_2;" in init and
         "DPIO_PHY_IOSF_PORT(DPIO_PHY1) = IOSF_PORT_DPIO;" in init,
         "NetBSD CHV PHY0 vs PHY1 unit mismatch")
    need("DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO;" in init and
         "IS_VALLEYVIEW(dev_priv)" in init,
         "NetBSD VLV port mismatch")
    need(early.count("intel_init_dpio(dev_priv);") == 1 and
         early.index("intel_init_dpio(dev_priv);") <
         early.index("intel_power_domains_init(dev_priv);"),
         "NetBSD DPIO mapping initialization after power setup or absent")
    need(re.search(r"#define\s+DPIO_PHY\(pipe\)\s+\(\(pipe\)\s*>>\s*1\)", reg)
         is not None, "NetBSD pipe to PHY index changed")
    nums = {}
    for sym in ("IOSF_PORT_DPIO", "IOSF_PORT_DPIO_2"):
        m = re.search(r"#define\s+" + sym + r"\s+(0x[0-9a-fA-F]+)", reg)
        need(m is not None, "native port number missing " + sym)
        nums[sym] = int(m.group(1), 16)
    need(nums == {"IOSF_PORT_DPIO": 0x12, "IOSF_PORT_DPIO_2": 0x1a},
         "physical CHV DPIO unit numbers changed")
    nread = func(native, "vlv_dpio_read")
    nwrite = func(native, "vlv_dpio_write")
    lread = func(linux, "vlv_dpio_read")
    lwrite = func(linux, "vlv_dpio_write")
    for routine in (nread, nwrite):
        need("i915->dpio_phy_iosf_port[DPIO_PHY(pipe)]" in routine,
             "NetBSD DPIO read/write no longer uses initialized port")
    for routine in (lread, lwrite):
        need("vlv_dpio_phy_to_unit(display, phy)" in routine,
             "Linux DPIO read/write not using PHY route")

    # Lock/PM contracts are consciously NOT treated as equivalent.
    get = func(native, "vlv_iosf_sb_get")
    put = func(native, "vlv_iosf_sb_put")
    rw = func(native, "vlv_sideband_rw")
    punit_get = func(native, "__vlv_punit_get")
    punit_put = func(native, "__vlv_punit_put")
    need("mutex_lock(&i915->sb_lock);" in get and
         "mutex_unlock(&i915->sb_lock);" in put and
         "lockdep_assert_held(&i915->sb_lock);" in rw,
         "native global IOSF lock contract missing")
    need(get.index("__vlv_punit_get(i915);") <
         get.index("mutex_lock(&i915->sb_lock);") and
         put.index("mutex_unlock(&i915->sb_lock);") <
         put.index("__vlv_punit_put(i915);"),
         "native PUNIT acquisition/release lock order changed")
    need("iosf_mbi_punit_acquire();" in punit_get and
         "iosf_mbi_punit_release();" in punit_put,
         "native PUNIT power-exclusion lifetime missing")
    need("if (IS_VALLEYVIEW(i915))" in punit_get and
         "pm_qos_update_request(&i915->sb_qos, 0);" in punit_get and
         "on_each_cpu(ping, NULL, 1);" in punit_get,
         "native VLV CPU-PUNIT sequencing changed")
    need("preempt_disable();" in rw and "preempt_enable();" in rw and
         "return -EAGAIN;" in rw and "err = -ETIMEDOUT;" in rw,
         "native IOSF timeout/preemption semantics changed")
    need("u32 val = 0;" in nread and
         "vlv_sideband_rw(" in nread and "return val;" in nread,
         "native read-on-error sentinel behavior changed")
    need("return vlv_sideband_rw(" in func(native, "vlv_punit_write"),
         "native PUNIT write error return lost")
    need("BIT(VLV_IOSF_SB_DPIO) | BIT(VLV_IOSF_SB_DPIO_2)" in
         func(linux, "vlv_dpio_get") and
         "BIT(VLV_IOSF_SB_DPIO));" in func(header, "vlv_dpio_get"),
         "DPIO get mask expectations changed")
    # This mask discrepancy is not automatically a bug: legacy native
    # get/put uses one sb_lock for both DPIO ports; Linux callback may
    # have finer-grained lifetime semantics, requiring separate review.

    cases = [
        {"platform": "CHV", "phy": p, "linux_port": 0x1a if p == 0 else 0x12,
         "netbsd_port": nums["IOSF_PORT_DPIO_2" if p == 0 else "IOSF_PORT_DPIO"]}
        for p in (0, 1)
    ]
    cases += [{"platform": "VLV", "phy": 0,
               "linux_port": 0x12, "netbsd_port": nums["IOSF_PORT_DPIO"]}]
    need(all(c["linux_port"] == c["netbsd_port"] for c in cases),
         "CHV/VLV PHY-to-physical-port disagreement")
    # pipe A/B share index 0 and C maps index 1 in the old native
    # macro; do not confuse display PIPE IDs with output port labels.
    for pipe in (0, 1, 2):
        physical = 0x1a if (pipe >> 1) == 0 else 0x12
        need(physical == cases[0 if pipe < 2 else 1]["linux_port"],
             "native pipe/PHY port route mismatch")
    return {"phy_cases": cases, "netbsd_pipe_to_phy": {"0":0, "1":0, "2":1},
            "native_global_sb_lock_verified": True,
            "native_punit_rollback_and_timeout_source_verified": True,
            "linux_get_mask":"DPIO + DPIO_2",
            "netbsd_get_mask":"DPIO only; protected by global sb_lock",
            "full_iosf_semantic_equivalence":"NOT_VERIFIED",
            "native_irq_power_pm_and_phy_hardware":"NOT_RUN"}

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--linux-sideband",type=Path,required=True)
    ap.add_argument("--netbsd-root",type=Path,required=True)
    opt=ap.parse_args()
    read=lambda p:p.read_bytes()
    base=opt.netbsd_root/"sys/external/bsd/drm2/dist/drm/i915"
    files={
      "linux":(opt.linux_sideband,LINUX_PIN),
      "sideband":(base/"intel_sideband.c",NETBSD_SIDEBAND_PIN),
      "driver":(base/"i915_drv.c",NETBSD_DRV_PIN),
      "header":(base/"intel_sideband.h",NETBSD_HEADER_PIN),
    }
    text={}
    for name,(p,required) in files.items():
        data=read(p)
        need(gitblob(data)==required,"immutable source Git blob drift "+name)
        text[name]=data.decode()
    reg=(base/"i915_reg.h").read_text()
    passed=source_contract(text["linux"],text["sideband"],
                           text["driver"],text["header"],reg)
    print("CHV_IOSF_SOURCE_3_PHY_AND_3_PIPE_ROUTING_CASES_PASS")
    print("CHV_IOSF_NETBSD_LOCK_PUNIT_TIMEOUT_SOURCE_CONTRACT_PASS")
    mutations=(
      ("linux_chv_route_swapped","linux",
       "phy == DPIO_PHY0 ?", "phy != DPIO_PHY0 ?"),
      ("netbsd_phy0_wrong_port","driver",
       "DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO_2;",
       "DPIO_PHY_IOSF_PORT(DPIO_PHY0) = IOSF_PORT_DPIO;"),
      ("netbsd_phy1_wrong_port","driver",
       "DPIO_PHY_IOSF_PORT(DPIO_PHY1) = IOSF_PORT_DPIO;",
       "DPIO_PHY_IOSF_PORT(DPIO_PHY1) = IOSF_PORT_DPIO_2;"),
      ("lost_init_before_power","driver",
       "intel_init_dpio(dev_priv);", "/* eliminated DPIO init */"),
      ("lost_sb_mutex_lock","sideband",
       "mutex_lock(&i915->sb_lock);", "/* eliminated IOSF mutex */"),
      ("lost_punit_acquire","sideband",
       "iosf_mbi_punit_acquire();", "/* lost PUNIT exclusion */"),
      ("lost_timeout_eagain","sideband",
       "return -EAGAIN;", "return -EIO;"),
      ("native_dpio_mask_changed","header",
       "vlv_iosf_sb_get(i915, BIT(VLV_IOSF_SB_DPIO));",
       "vlv_iosf_sb_get(i915, 0);"),
    )
    for label, owner, before, after in mutations:
        mutant=dict(text)
        scoped = {
            "lost_sb_mutex_lock": "vlv_iosf_sb_get",
            "lost_timeout_eagain": "vlv_sideband_rw",
        }
        if label in scoped:
            # Other i915 functions may use the same lock/errno.
            # Mutate the exact reviewed function, never first-match.
            original_func = func(mutant[owner], scoped[label])
            need(original_func.count(before) == 1,
                 "nonunique scoped mutation anchor " + label)
            mutant[owner] = mutant[owner].replace(
                original_func, original_func.replace(before, after, 1), 1)
        else:
            need(text[owner].count(before) == 1,
                 "nonunique mutation anchor "+label)
            mutant[owner]=mutant[owner].replace(before,after,1)
        try:
            source_contract(mutant["linux"],mutant["sideband"],
                            mutant["driver"],mutant["header"],reg)
        except ValueError as err:
            need(str(err).startswith("CHV_IOSF_SEMANTIC_REFUSED"),
                 "wrong rejection signal "+label)
        else:
            raise AssertionError("UNSAFE MUTATION ACCEPTED "+label)
    print("CHV_IOSF_EIGHT_PINNED_SOURCE_MUTANTS_REFUSED")
    print("LIMIT: one SOURCE PARTIAL REVIEW; Linux parent underlying callback,"
          " NetBSD chipset IRQ/PM concurrency, full 300 i915 NOT VERIFIED")
    print(passed)

if __name__=="__main__":
    main()
