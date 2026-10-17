#!/usr/bin/env python3
"""Pin NetBSD legacy sideband, apply status patch in a scratch tree, test C."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/"compat/native-runtime/vlv-iosf/patches/netbsd-intel-sideband-checked-status.patch"
FILES="sys/external/bsd/drm2/dist/drm/i915"
PINS={
 "intel_sideband.c":"ae1aefbd0683cb031a0bc9b20a9c16c1438d391f51b4158fddfc0e1555a05807",
 "intel_sideband.h":"498168f1ac94396e5e25aabd8f10e39e64f513f19e378d24b4f2b7b64110d612",
}
parser=argparse.ArgumentParser()
parser.add_argument("--netbsd-src",type=Path,default=Path(
 "/opt/ChatGPT/hp-driver-port/netbsd-src-03d918f6-full"))
args=parser.parse_args()
assert PATCH.is_file()
cc=shutil.which("cc")
patch=shutil.which("patch")
assert cc and patch
sources={}
for name,pin in PINS.items():
 f=args.netbsd_src/FILES/name
 content=f.read_bytes()
 assert hashlib.sha256(content).hexdigest()==pin,(name,"not pinned source")
 sources[name]=content.decode()
with tempfile.TemporaryDirectory(prefix="i915-native-iosf-patch-") as td:
 temp=Path(td)
 for name,content in sources.items():
  f=temp/FILES/name
  f.parent.mkdir(parents=True,exist_ok=True)
  f.write_text(content)
 run=subprocess.run([patch,"--batch","-p1","-d",str(temp),"-i",str(PATCH)],
                    capture_output=True,text=True,timeout=25)
 assert run.returncode==0,(run.returncode,run.stdout,run.stderr)
 c=(temp/FILES/"intel_sideband.c").read_text()
 h=(temp/FILES/"intel_sideband.h").read_text()
 assert c.count("nb_i915_vlv_iosf_rw_checked(")==1
 assert h.count("nb_i915_vlv_iosf_rw_checked(")==1
 assert "void vlv_iosf_sb_write(struct drm_i915_private *i915" in c
 assert "void vlv_iosf_sb_write(struct drm_i915_private *i915" in h
 start=c.index("int\nnb_i915_vlv_iosf_rw_checked(")
 end=c.index("\nvoid vlv_iosf_sb_write(",start)
 func=c[start:end]
 mock=r"""
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
typedef uint32_t u32;
struct drm_i915_private { int unused; };
#define SB_MRD_NP 0x00
#define SB_MWR_NP 0x01
#define SB_CRRDDA_NP 0x06
#define SB_CRWRDA_NP 0x07
static int transport_status;
static int called;
static int vlv_sideband_rw(struct drm_i915_private *i915,
    u32 devfn,u32 port,u32 opcode,u32 addr,u32 *value)
{
 (void)i915;(void)devfn;(void)port;(void)opcode;(void)addr;
 ++called;
 if(!transport_status)*value=0xdeadbeefU;
 return transport_status;
}
""" + func + r"""
int main(void)
{
 struct drm_i915_private i915={0};
 u32 val=0xcafeU;
 int status;
 status=nb_i915_vlv_iosf_rw_checked(&i915,0,4,7,0,&val);
 if(status || val!=0xdeadbeefU || called!=1) return 1;
 transport_status=-EAGAIN;called=0;val=0xcafeU;
 status=nb_i915_vlv_iosf_rw_checked(&i915,0,4,7,0,&val);
 if(status!=-EAGAIN || called!=1 || val!=0xcafeU) return 2;
 transport_status=-ETIMEDOUT;called=0;
 status=nb_i915_vlv_iosf_rw_checked(&i915,0,4,6,0,&val);
 if(status!=-ETIMEDOUT || called!=1 || val!=0xcafeU) return 3;
 called=0;
 if(nb_i915_vlv_iosf_rw_checked(&i915,0,0,6,0,&val)!=-EINVAL || called) return 4;
 if(nb_i915_vlv_iosf_rw_checked(&i915,0,4,9,0,&val)!=-EINVAL || called) return 5;
 if(nb_i915_vlv_iosf_rw_checked(&i915,0,4,7,0,NULL)!=-EINVAL || called) return 6;
 return 0;
}
"""
 probe=temp/"iosf_probe.c";probe.write_text(mock)
 exe=temp/"iosf_probe"
 build=subprocess.run([cc,"-std=gnu11","-O0","-Wall","-Wextra",
                       "-Werror",str(probe),"-o",str(exe)],
                       capture_output=True,text=True,timeout=25)
 assert build.returncode==0,build.stderr
 run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
 assert run.returncode==0,(run.returncode,run.stderr)
print("I915_PINNED_NETBSD_IOSF_PATCH_APPLY_AND_C_STATUS_ERRORS_PASS")
print("LIMITATION: no native NetBSD kernel compile, real sb_lock or physical MMIO")
