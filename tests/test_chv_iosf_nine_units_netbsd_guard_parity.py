#!/usr/bin/env python3
"""Source-compare all 9 Linux VLV/CHV IOSF routes against NetBSD guard patch.

Never asserts the modern guard patch is integrated/compiled on HP; it is
a candidate overlay, not a native kernel. Verifies the pinned Linux C
backend, NetBSD register macros and pinned i915 owner patch before parsing.
"""
import argparse
import hashlib
from pathlib import Path
import re

LINUX_GIT_BLOB = "1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758"
NETBSD_REG_GIT_BLOB = "a070913dc965ebfb467b99da599e75dd03df61de"
EXPECTED = {
    "BUNIT": ("IOSF_PORT_BUNIT", 0x03),
    "CCK": ("IOSF_PORT_CCK", 0x14),
    "CCU": ("IOSF_PORT_CCU", 0xa9),
    "DPIO": ("IOSF_PORT_DPIO", 0x12),
    "DPIO2": ("IOSF_PORT_DPIO_2", 0x1a),
    "FLISDSI": ("IOSF_PORT_FLISDSI", 0x1b),
    "GPIO": (None, None),
    "NC": ("IOSF_PORT_NC", 0x11),
    "PUNIT": ("IOSF_PORT_PUNIT", 0x04),
}
LINUX_NAMES = {
    "BUNIT":"BUNIT", "CCK":"CCK", "CCU":"CCU",
    "DPIO":"DPIO", "DPIO2":"DPIO_2", "FLISDSI":"FLISDSI",
    "GPIO":"GPIO", "NC":"NC", "PUNIT":"PUNIT"
}

def need(test, reason):
    if not test:
        raise AssertionError("IOSF_NINE_UNITS_REFUSED: " + reason)

def gitblob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def body(src, name):
    hits=list(re.finditer(r"\b"+re.escape(name)+r"\s*\([^;{}]{0,500}\)\s*\{",src))
    need(len(hits)==1,"function identity "+name)
    start=src.index("{",hits[0].start())
    depth=0
    for pos in range(start,len(src)):
        if src[pos]=="{":depth+=1
        if src[pos]=="}":
            depth-=1
            if depth==0:return src[start+1:pos]
    raise AssertionError("unclosed C routine "+name)

def case_expr(src, label):
    marker=r"\bcase\s+"+re.escape(label)+r"\s*:\s*"
    hits=list(re.finditer(marker,src))
    need(len(hits)==1,"unique case "+label)
    pos=hits[0].end()
    next_case=re.search(r"\b(?:case\s+\w+\s*:|default\s*:)",src[pos:])
    return src[pos:pos+next_case.start()] if next_case else src[pos:]

def port_value(reg, token, expected):
    hit=re.findall(r"(?m)^[ \t]*#define[ \t]+"+re.escape(token)+
                   r"[ \t]+(0x[0-9a-fA-F]+)\b",reg)
    need(len(hit)==1 and int(hit[0],16)==expected,
         "unverified NetBSD physical port macro "+token)

def check(linux, native, reg):
    lp=body(linux,"unit_to_port")
    ld=body(linux,"unit_to_devfn")
    lo=body(linux,"unit_to_opcode")
    np=body(native,"nb_i915_iosf_route")
    access=body(native,"nb_i915_iosf_access")
    need(re.search(r"(?m)^#define\s+DPIO_DEVFN\s+0\b",reg) is not None,
         "DPIO_DEVFN != zero")
    need("PCI_DEVFN(0, 0)" in access,
         "NetBSD modern guard devfn changed")
    need("unit == NB_I915_IOSF_DPIO || unit == NB_I915_IOSF_DPIO2" in np,
         "DPIO-only opcode mapping changed")
    need("write ? SB_MWR_NP : SB_MRD_NP" in np and
         "write ? SB_CRWRDA_NP : SB_CRRDDA_NP" in np,
         "DPIO/other read/write opcode selection changed")
    need("unit == VLV_IOSF_SB_DPIO || unit == VLV_IOSF_SB_DPIO_2" in lo and
         "write ? SB_MWR_NP : SB_MRD_NP" in lo and
         "write ? SB_CRWRDA_NP : SB_CRRDDA_NP" in lo,
         "actual Linux opcode selector changed")
    need("return DPIO_DEVFN;" in ld and "return PCI_DEVFN(0, 0);" in ld,
         "actual Linux devfn discriminator changed")
    observed=[]
    for name,(physical,number) in EXPECTED.items():
        linuxunit="VLV_IOSF_SB_"+LINUX_NAMES[name]
        nativeunit="NB_I915_IOSF_"+name
        lcase=case_expr(lp,linuxunit)
        ncase=case_expr(np,nativeunit)
        if name=="GPIO":
            need("return 0;" in lcase and "return -EOPNOTSUPP;" in ncase,
                 "GPIO unsupported-port must fail closed")
            observed.append({"unit":name,"port":None,"read":None,"write":None,
                             "candidate_status":"EOPNOTSUPP"})
            continue
        need(re.search(r"\breturn\s+"+re.escape(physical)+r"\s*;",lcase) is not None,
             "actual upstream Linux port mismatch "+name)
        need(re.search(r"\*port\s*=\s*"+re.escape(physical)+r"\s*;",ncase) is not None,
             "NetBSD guard source port mismatch "+name)
        port_value(reg,physical,number)
        read=0 if name in ("DPIO","DPIO2") else 6
        write=1 if name in ("DPIO","DPIO2") else 7
        observed.append({"unit":name,"port":number,"read":read,"write":write,
                         "devfn":0,"candidate_status":"SOURCE_EQUAL"})
    need("if ((guard->units & BIT(unit)) == 0)" in access,
         "per-unit guard access check removed")
    need("return -EPERM;" in access,
         "unowned unit no longer refused")
    need("if (unit > NB_I915_IOSF_PUNIT)" in access,
         "unit upper-bound missing")
    return observed

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--linux-iosf",type=Path,required=True)
    parser.add_argument("--netbsd-reg",type=Path,required=True)
    parser.add_argument("--candidate-patch",type=Path,required=True)
    x=parser.parse_args()
    raw=x.linux_iosf.read_bytes()
    native_reg=x.netbsd_reg.read_bytes()
    need(gitblob(raw)==LINUX_GIT_BLOB,"frozen upstream source drift")
    need(gitblob(native_reg)==NETBSD_REG_GIT_BLOB,"frozen NetBSD register source drift")
    full_patch=x.candidate_patch.read_text()
    need(full_patch.count("+nb_i915_iosf_route(")==1 and
         full_patch.count("+nb_i915_iosf_access(")==1,
         "IOSF guard patch missing ownership")
    # Only new C lines are extracted; this is a patch candidate, not a
    # runtime NetBSD source overlay.
    added="\n".join(line[1:] for line in full_patch.splitlines()
                    if line.startswith("+") and not line.startswith("+++"))
    linux=raw.decode()
    reg=native_reg.decode()
    rows=check(linux,added,reg)
    need(len(rows)==9,"unit count")
    need(sum(row["candidate_status"]=="SOURCE_EQUAL" for row in rows)==8,
         "eight supported units")
    print("CHV_IOSF_NINE_UNITS_18_R_W_PATHS_SOURCE_VERIFIED")
    cases=(
        ("CHV_PHY1_SWAPPED","NB_I915_IOSF_DPIO2: *port = IOSF_PORT_DPIO_2",
         "NB_I915_IOSF_DPIO2: *port = IOSF_PORT_DPIO"),
        ("PUNIT_PORT_SWAPPED","NB_I915_IOSF_PUNIT: *port = IOSF_PORT_PUNIT",
         "NB_I915_IOSF_PUNIT: *port = IOSF_PORT_NC"),
        ("CCU_PORT_SWAPPED","NB_I915_IOSF_CCU: *port = IOSF_PORT_CCU",
         "NB_I915_IOSF_CCU: *port = IOSF_PORT_CCK"),
        ("DPIO_READ_OPCODE_SWAPPED","write ? SB_MWR_NP : SB_MRD_NP",
         "write ? SB_MWR_NP : SB_CRRDDA_NP"),
        ("DPIO_WRITE_OPCODE_SWAPPED","write ? SB_MWR_NP : SB_MRD_NP",
         "write ? SB_CRWRDA_NP : SB_MRD_NP"),
        ("OTHER_READ_OPCODE_SWAPPED","write ? SB_CRWRDA_NP : SB_CRRDDA_NP",
         "write ? SB_CRWRDA_NP : SB_MRD_NP"),
        ("UNKNOWN_GPIO_ACCEPTED","NB_I915_IOSF_GPIO: return -EOPNOTSUPP;",
         "NB_I915_IOSF_GPIO: *port = IOSF_PORT_DPIO; break;"),
        ("UNIT_OWNERSHIP_BYPASS","if ((guard->units & BIT(unit)) == 0)",
         "if (false)"),
        ("UNSAFE_DEVFN","PCI_DEVFN(0, 0),\n", "PCI_DEVFN(0, 1),\n"),
    )
    for label,original,changed in cases:
        need(added.count(original)==1,"mutation not unique "+label)
        mutation=added.replace(original,changed,1)
        try:
            check(linux,mutation,reg)
        except AssertionError as e:
            need("IOSF_NINE_UNITS_REFUSED:" in str(e),
                 "wrong source rejection "+label)
        else:
            raise AssertionError("unsafe IOSF source mutation accepted "+label)
    print("CHV_IOSF_NINE_SOURCE_MUTATIONS_REFUSED")
    print("LIMIT: owner patch only; no native HP compile, lock, IRQ or PM parity")
    for row in rows:print(row)

if __name__=="__main__":
    main()
