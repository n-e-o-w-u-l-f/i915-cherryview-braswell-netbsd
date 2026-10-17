#!/usr/bin/env python3
"""Prove both real NetBSD intel_sideband patches apply in order and run C guards.

This is a source-only C fixture, not a native kernel, KMS or physical MMIO.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"compat/native-runtime/vlv-iosf/patches"
ap=argparse.ArgumentParser()
ap.add_argument("--netbsd-drm2",type=Path,default=Path(
 "/opt/ChatGPT/hp-driver-port/netbsd-src-03d918f6-full/sys/external/bsd/drm2"))
opts=ap.parse_args()
base=opts.netbsd_drm2/"dist/drm/i915"
rel=Path("sys/external/bsd/drm2/dist/drm/i915")
pin={
 "intel_sideband.c":"ae1aefbd0683cb031a0bc9b20a9c16c1438d391f51b4158fddfc0e1555a05807",
 "intel_sideband.h":"498168f1ac94396e5e25aabd8f10e39e64f513f19e378d24b4f2b7b64110d612",
}
assert shutil.which("patch") and shutil.which("cc")
with tempfile.TemporaryDirectory(prefix="i915-native-sideband-chain-") as td:
 stage=Path(td)
 for name,expected in pin.items():
  data=(base/name).read_bytes()
  assert hashlib.sha256(data).hexdigest()==expected,name
  path=stage/rel/name
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(data)
 for name in ("netbsd-intel-sideband-checked-status.patch",
              "netbsd-intel-sideband-modern-guard.patch"):
  patch=P/name
  assert patch.is_file()
  proc=subprocess.run(["patch","--batch","-s","-p1","-d",str(stage),
                       "-i",str(patch)],capture_output=True,text=True,timeout=25)
  assert proc.returncode==0,(name,proc.stdout,proc.stderr)
 c=(stage/rel/"intel_sideband.c").read_text()
 h=(stage/rel/"intel_sideband.h").read_text()
 assert c.count("nb_i915_vlv_iosf_rw_checked(")==2
 assert c.count("nb_i915_iosf_acquire(")==1
 assert c.count("nb_i915_iosf_release(")==1
 assert "void vlv_iosf_sb_write(" in c
 assert "void vlv_iosf_sb_write(" in h
 assert "NB_I915_IOSF_PUNIT = 8" in h
 assert "NB_I915_IOSF_DPIO2 = 4" in h
 decl=h[h.index("enum nb_i915_iosf_unit"):h.index("void vlv_iosf_sb_get(")]
 body=c[c.index("int\nnb_i915_vlv_iosf_rw_checked("):
        c.index("\nvoid vlv_iosf_sb_write(")]
 mock=r"""
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
typedef uint32_t u32;
struct drm_i915_private { int sb_lock; };
#define BIT(i) (1UL<<(i))
#define PCI_DEVFN(a,b) 0
#define IOSF_PORT_BUNIT 0x03
#define IOSF_PORT_CCK 0x14
#define IOSF_PORT_CCU 0xa9
#define IOSF_PORT_DPIO 0x12
#define IOSF_PORT_DPIO_2 0x1a
#define IOSF_PORT_FLISDSI 0x1b
#define IOSF_PORT_NC 0x11
#define IOSF_PORT_PUNIT 0x04
#define SB_MRD_NP 0
#define SB_MWR_NP 1
#define SB_CRRDDA_NP 6
#define SB_CRWRDA_NP 7
static int lock_count,unlock_count,punit_get,punit_put,calls,transport_status;
static u32 last_port,last_op;
static void mutex_lock(int *v){(void)v;lock_count++;}
static void mutex_unlock(int *v){(void)v;unlock_count++;}
static void __vlv_punit_get(struct drm_i915_private *v){(void)v;punit_get++;}
static void __vlv_punit_put(struct drm_i915_private *v){(void)v;punit_put++;}
static int vlv_sideband_rw(struct drm_i915_private *d,u32 fn,u32 port,u32 op,
 u32 addr,u32 *value){
 (void)d;(void)fn;(void)addr;
 calls++;last_port=port;last_op=op;
 if(transport_status) return transport_status;
 *value=0xdeadbeefU;
 return 0;
}
"""
 fixture=mock+decl+body+r"""
int main(void){
 struct drm_i915_private dev={0};
 struct nb_i915_iosf_guard g={0};
 u32 value=0x12345678U;
 if(nb_i915_iosf_acquire(&dev,(1UL<<8)|(1UL<<4),&g))return 1;
 if(punit_get!=1||lock_count!=1||g.owner!=&dev)return 2;
 if(nb_i915_iosf_write_checked(&g,4,0,value)||calls!=1||
    last_port!=0x1a||last_op!=1)return 3;
 if(nb_i915_iosf_read_checked(&g,4,0,&value)||value!=0xdeadbeefU||
    last_op!=0)return 4;
 transport_status=-EAGAIN;value=0xaabbU;
 if(nb_i915_iosf_read_checked(&g,4,0,&value)!=-EAGAIN||
    value!=0xaabbU)return 5;
 transport_status=-ETIMEDOUT;
 if(nb_i915_iosf_write_checked(&g,4,0,0)!=-ETIMEDOUT)return 6;
 calls=0;
 if(nb_i915_iosf_write_checked(&g,7,0,0)!=-EPERM||calls)return 7;
 if(nb_i915_iosf_release(&g)||unlock_count!=1||punit_put!=1||g.owner)return 8;
 if(nb_i915_iosf_release(&g)!=-EINVAL)return 9;
 if(nb_i915_iosf_acquire(&dev,1UL<<6,&g)!=-EOPNOTSUPP)return 10;
 if(nb_i915_iosf_acquire(&dev,1UL<<10,&g)!=-EINVAL)return 11;
 if(nb_i915_iosf_acquire(&dev,1UL<<3,&g))return 12;
 if(nb_i915_iosf_acquire(&dev,1UL<<3,&g)!=-EBUSY)return 13;
 transport_status=0;
 if(nb_i915_iosf_write_checked(&g,3,0,0)||last_port!=0x12||last_op!=1)return 14;
 if(nb_i915_iosf_release(&g)||unlock_count!=2||punit_put!=1)return 15;
 return 0;
}
"""
 source=stage/"iosf.c"
 source.write_text(fixture)
 exe=stage/"test"
 compile=subprocess.run(["cc","-std=gnu11","-O0","-Wall","-Wextra","-Werror",
                         str(source),"-o",str(exe)],
                        capture_output=True,text=True,timeout=25)
 assert compile.returncode==0,compile.stderr
 run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
 assert run.returncode==0,(run.returncode,run.stdout,run.stderr)
print("I915_NETBSD_REAL_IOSF_2_PATCH_CHAIN_15_CASES_PASS")
print("LIMITATION: C fixture only, not native HP KMS/kernel compilation")
