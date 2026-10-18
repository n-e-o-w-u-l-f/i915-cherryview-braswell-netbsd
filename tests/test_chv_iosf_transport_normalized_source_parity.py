#!/usr/bin/env python3
"""Pinned frozen Linux-vs-NetBSD IOSF transport C function body comparison.

Only 3 named bodies are compared. Explicit differences in field/API names
are normalized without inventing synchronization/runtime equivalence.
No compiler, HP kernel, KMS or actual IRQ/power sequencing acceptance.
"""
import argparse
import hashlib
from pathlib import Path
import re

LINUX_BLOB = "1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758"
NETBSD_BLOB = "1cc6a956b90cc44a85fa153ea1aa9ba58a605eed"
FUNCTIONS = ("vlv_sideband_rw", "__vlv_punit_get", "__vlv_punit_put")
REWRITES = (
    ("i915->vlv_iosf_sb.lock", "i915->sb_lock"),
    ("i915->vlv_iosf_sb.qos", "i915->sb_qos"),
    ("cpu_latency_qos_", "pm_qos_"),
)

def need(condition, reason):
    if not condition:
        raise ValueError("CHV_IOSF_TRANSPORT_PARITY_REFUSED: " + reason)

def gitblob(raw):
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw
    ).hexdigest()

def extract(src, name):
    match=re.search(r"\b"+re.escape(name)+r"\s*\([^{};]{0,450}\)\s*\{",src)
    need(match is not None, "missing routine "+name)
    start=src.index("{",match.start())
    d=0
    for i in range(start,len(src)):
        if src[i]=="{":d+=1
        if src[i]=="}":
            d-=1
            if d==0:return src[start+1:i]
    raise AssertionError("unbalanced routine "+name)

def normal(src, linux):
    if linux:
        for before,after in REWRITES:
            src=src.replace(before,after)
    # The reference bodies match after removing whitespace and a single
    # commentary block. The test compares all remaining C tokens.
    src=re.sub(r"/\*[\s\S]*?\*/","",src)
    src=re.sub(r"\s+","",src)
    return src

def validate(linux,netbsd):
    for name in FUNCTIONS:
        a=normal(extract(linux,name),True)
        b=normal(extract(netbsd,name),False)
        need(a==b,"non-identical source C body "+name)
    for check in (
        "i915->vlv_iosf_sb.lock", "i915->vlv_iosf_sb.qos",
        "cpu_latency_qos_",
    ):
        need(check in linux,"missing actual Linux compatibility field "+check)
    for check in ("i915->sb_lock","i915->sb_qos","pm_qos_"):
        need(check in netbsd,"missing native NetBSD field "+check)
    # The modern explicit per-unit tracking and mask checking are extra:
    # this test does not normalize them away or assert full owner parity.
    need("locked_unit_mask" in linux and
         "locked_unit_mask" not in netbsd,
         "per-unit ownership tracking difference changed")
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--linux-iosf",type=Path,required=True)
    ap.add_argument("--netbsd-iosf",type=Path,required=True)
    a=ap.parse_args()
    b1=a.linux_iosf.read_bytes()
    b2=a.netbsd_iosf.read_bytes()
    need(gitblob(b1)==LINUX_BLOB,"wrong frozen Linux source")
    need(gitblob(b2)==NETBSD_BLOB,"wrong frozen NetBSD source")
    linux,netbsd=b1.decode(),b2.decode()
    validate(linux,netbsd)
    print("CHV_IOSF_THREE_REAL_C_BODIES_NORMALIZED_TOKEN_PARITY_PASS")
    mutation_cases=(
      ("idle_timeout","vlv_sideband_rw","return -EAGAIN;","return -EBUSY;"),
      ("finish_timeout","vlv_sideband_rw","10000, 0, NULL","9000, 0, NULL"),
      ("lost_preemption","vlv_sideband_rw","preempt_disable();","/*removed*/"),
      ("wrong_opcode","vlv_sideband_rw","SB_MWR_NP","SB_MRD_NP"),
      ("lost_valleyview_qos","__vlv_punit_get",
       "pm_qos_update_request(&i915->sb_qos, 0);","/*removed*/"),
      ("lost_cpu_ping","__vlv_punit_get","on_each_cpu(ping, NULL, 1);","/*removed*/"),
      ("lost_punit_release","__vlv_punit_put",
       "iosf_mbi_punit_release();","/*removed*/"),
    )
    for label,name,before,after in mutation_cases:
        original_func=extract(netbsd,name)
        need(original_func.count(before)==1,"nonunique mutation "+label)
        modified=netbsd.replace(original_func,original_func.replace(before,after,1),1)
        try:
            validate(linux,modified)
        except ValueError as e:
            need("non-identical source C body" in str(e),
                 "incorrect negative failure "+label)
        else:
            raise AssertionError("dangerous mutant not detected "+label)
    print("CHV_IOSF_SEVEN_TRANSPORT_SOURCE_MUTATIONS_REFUSED")
    print("LIMIT: 3 bodies token-identical only after explicit API renames;"
          " lock/QoS ABI and remaining owner functions still unverified")

if __name__=="__main__":
    main()
