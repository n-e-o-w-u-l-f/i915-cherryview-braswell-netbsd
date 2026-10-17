#!/usr/bin/env python3
"""Pinned Linux->NetBSD IOSF port/opcode/error/lock contract; host-C only."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BRIDGE=ROOT/"compat/native-runtime/vlv-iosf/include"
STAGE=Path("/opt/ChatGPT/hp-driver-port")
LINUX=STAGE/"i915-reference-stage-20261001/drivers/gpu/drm/i915"
NETBSD=STAGE/"netbsd-src-03d918f6-full/sys/external/bsd/drm2/dist/drm/i915"

for path,sha in (
    (LINUX/"vlv_iosf_sb.c","ce076e147edc00599df16641cf9f1587ee24277f858c7df4aff00f8d690b2e65"),
    (NETBSD/"intel_sideband.c","ae1aefbd0683cb031a0bc9b20a9c16c1438d391f51b4158fddfc0e1555a05807"),
    (LINUX/"i915_reg.h","4378b821119b67119ed3b7d218c3563d481271e1a16dcd59c1fd258306140a85"),
    (NETBSD/"i915_reg.h","759a4ee5f6583e805b52bc917758860d1a29c548ebe098367b76875bb400b387")
):
    assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==sha,path

expected={"BUNIT":0x03,"CCK":0x14,"CCU":0xa9,"DPIO":0x12,
          "DPIO_2":0x1a,"FLISDSI":0x1b,"NC":0x11,"PUNIT":0x04}
route=(BRIDGE/"nb_i915_vlv_iosf_transaction.h").read_text()
for name,value in expected.items():
    for old in (LINUX,NETBSD):
        m=re.search(r"(?m)^#define\s+IOSF_PORT_"+name+r"\s+0x([0-9a-fA-F]+)\b",
                    (old/"i915_reg.h").read_text())
        assert m and int(m[1],16)==value,(old,name)
    assert f"case NB_I915_MOD_{name}: r.port = 0x{value:02x}U;" in route
assert "if (unit == NB_I915_MOD_DPIO || unit == NB_I915_MOD_DPIO_2)" in route
assert "locked_unit_mask" in (LINUX/"vlv_iosf_sb.c").read_text()
assert "locked_unit_mask" not in (NETBSD/"intel_sideband.c").read_text()
print("I915_IOSF_PINNED_LINUX_NETBSD_PORT_AND_OPCODE_MATCH_PASS")
C=r"""
#include <linux/types.h>
#include <sys/errno.h>
#include <stdio.h>
#include "nb_i915_vlv_iosf_transaction.h"
struct state {
 unsigned int calls;
 u32 devfn,port,opcode,addr,written;
 int outcome;
} s;
static int transport(void *unused,u32 devfn,u32 port,u32 opcode,u32 addr,u32 *val){
 (void)unused;
 s.calls++;s.devfn=devfn;s.port=port;s.opcode=opcode;s.addr=addr;s.written=*val;
 if(s.outcome)return s.outcome;
 if(opcode==0x00 || opcode==0x06)*val=0xdeadbeefU;
 return 0;
}
static int ok(int yes,int n){if(!yes)printf("FAILED %d\n",n);return yes?0:1;}
int main(void){
 const u32 ports[9]={0x03,0x14,0xa9,0x12,0,0x1b,0,0x11,0x04};
 unsigned int u,mode;
 u32 value,old;
 int rc;
 struct nb_i915_vlv_iosf_route route;
 for(u=0;u<9;u++)for(mode=0;mode<2;mode++){
  s.calls=0;s.outcome=0;value=0x12345678U;
  rc=nb_i915_vlv_iosf_transact(u,mode,0x55,&value,1UL<<u,transport,0);
  if(u==4||u==6){if(ok(rc==-EOPNOTSUPP&&s.calls==0,1))return 1;continue;}
  if(ok(rc==0&&s.calls==1&&s.devfn==0&&s.port==ports[u]&&s.addr==0x55,2))return 2;
  if(ok(s.opcode==((u==3)?(mode?1U:0U):(mode?7U:6U)),3))return 3;
  if(ok(value==(mode?0x12345678U:0xdeadbeefU),4))return 4;
 }
 s.calls=0;value=0x77;
 if(ok(nb_i915_vlv_iosf_transact(8,1,0,&value,1UL<<7,transport,0)==-EPERM&&s.calls==0,5))return 5;
 s.outcome=-EAGAIN;value=0xaabbU;
 if(ok(nb_i915_vlv_iosf_transact(8,0,0,&value,1UL<<8,transport,0)==-EAGAIN&&value==0xaabbU,6))return 6;
 s.outcome=-ETIMEDOUT;value=0xccddU;
 if(ok(nb_i915_vlv_iosf_transact(8,1,0,&value,1UL<<8,transport,0)==-ETIMEDOUT&&value==0xccddU,7))return 7;
 s.outcome=0;s.calls=0;
 if(ok(nb_i915_vlv_iosf_transact(12,0,0,&value,~0UL,transport,0)==-EINVAL&&s.calls==0,8))return 8;
 if(ok(nb_i915_vlv_iosf_route(4,0,&route)==0&&route.port==0x1a&&route.opcode==0,9))return 9;
 old=value;
 if(ok(nb_i915_vlv_iosf_transact(8,0,0,0,1UL<<8,transport,0)==-EINVAL&&value==old,10))return 10;
 if(ok(nb_i915_vlv_iosf_route(6,0,&route)==-EOPNOTSUPP,11))return 11;
 puts("I915_IOSF_ROUTE_LOCK_GUARD_AND_ERROR_PROPAGATION_PASS");
 return 0;
}
"""
cc=shutil.which("cc")
assert cc
with tempfile.TemporaryDirectory(prefix="i915-iosf-c-") as td:
    root=Path(td)
    (root/"linux").mkdir()
    (root/"sys").mkdir()
    (root/"linux/types.h").write_text("#include <stdint.h>\ntypedef uint32_t u32;\n")
    (root/"sys/errno.h").write_text("#include <errno.h>\n")
    srcfile=root/"probe.c";srcfile.write_text(C)
    exe=root/"probe"
    subprocess.run([cc,"-std=gnu11","-O0","-Wall","-Wextra","-Werror",
                    "-I",str(root),"-I",str(BRIDGE),str(srcfile),"-o",str(exe)],
                   timeout=25,check=True)
    ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
    assert ran.returncode==0,(ran.returncode,ran.stdout,ran.stderr)
    print(ran.stdout.strip())
print("LIMITATION: no real NetBSD sb_lock, driver lifecycle, MMIO or native kernel build")
