#!/usr/bin/env python3
"""Test actual display helper shim with native NetBSD C ABI and fault injection."""
import argparse
from pathlib import Path
import hashlib
import platform
import socket
import subprocess
import tempfile

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--shim",required=True,type=Path)
    ap.add_argument("--native-header",required=True,type=Path)
    a=ap.parse_args()
    assert platform.system()=="NetBSD" and socket.gethostname().startswith("hp")
    sh=a.shim.read_text()
    native=a.native_header.read_text()
    for needle in ("ssize_t drm_dp_dpcd_read(", "ssize_t drm_dp_dpcd_write(",
                   "void drm_dp_link_train_clock_recovery_delay(const u8",
                   "void drm_dp_link_train_channel_eq_delay(const u8"):
        assert needle in native,needle
    assert "#include <drm/drm_dp_helper.h>" in sh
    with tempfile.TemporaryDirectory(prefix="i915-native-dpcd-contract-") as temp:
        t=Path(temp)
        (t/"include/drm/display").mkdir(parents=True)
        (t/"include/drm").mkdir(parents=True,exist_ok=True)
        (t/"include/linux").mkdir(parents=True,exist_ok=True)
        (t/"include/drm/display/drm_dp_helper.h").write_text(sh)
        (t/"include/linux/errno.h").write_text("#include <errno.h>\n")
        (t/"include/drm/drm_dp_helper.h").write_text("""
#ifndef _NETBSD_DRM_DP_HELPER_ABI_FIXTURE_
#define _NETBSD_DRM_DP_HELPER_ABI_FIXTURE_
#include <sys/types.h>
#include <stdint.h>
typedef uint8_t u8;
#define DP_RECEIVER_CAP_SIZE 16
struct drm_dp_aux { int stub; };
ssize_t drm_dp_dpcd_read(struct drm_dp_aux *, unsigned int, void *, size_t);
ssize_t drm_dp_dpcd_write(struct drm_dp_aux *, unsigned int, void *, size_t);
void drm_dp_link_train_clock_recovery_delay(const u8 *);
void drm_dp_link_train_channel_eq_delay(const u8 *);
#endif
""")
        source=r"""
#include <errno.h>
#include <string.h>
#include <drm/display/drm_dp_helper.h>
static int rmode,wmode,rcount,wcount;
static unsigned int last_offset;
static int clock_calls,eq_calls;
static const u8 *last_dpcd;
ssize_t drm_dp_dpcd_read(struct drm_dp_aux *aux,unsigned int offset,
                         void *buffer,size_t size)
{
 (void)aux; rcount++; last_offset=offset;
 if(rmode==1) return 0;
 if(rmode==2) return -EIO;
 if(rmode==3) {if(rcount==1)return -EIO;if(rcount==3)return -EFAULT;}
 if(rmode==4) {if(rcount==1)return -EIO;if(rcount==3)return 0;}
 memset(buffer,0x42,size); return (ssize_t)size;
}
ssize_t drm_dp_dpcd_write(struct drm_dp_aux *aux,unsigned int offset,
                          void *buffer,size_t size)
{
 (void)aux;(void)buffer;wcount++;last_offset=offset;
 if(wmode==1)return 0;
 if(wmode==2)return -EIO;
 return (ssize_t)size;
}
#undef drm_dp_link_train_clock_recovery_delay
#undef drm_dp_link_train_channel_eq_delay
void drm_dp_link_train_clock_recovery_delay(const u8 *dpcd)
{clock_calls++;last_dpcd=dpcd;}
void drm_dp_link_train_channel_eq_delay(const u8 *dpcd)
{eq_calls++;last_dpcd=dpcd;}
#define drm_dp_link_train_clock_recovery_delay(aux,dpcd) nb_i915_dp_link_train_clock_recovery_delay((aux),(dpcd))
#define drm_dp_link_train_channel_eq_delay(aux,dpcd) nb_i915_dp_link_train_channel_eq_delay((aux),(dpcd))
int main(void)
{
 struct drm_dp_aux aux={0};
 u8 value=0,buffer[4]={0},caps[DP_RECEIVER_CAP_SIZE]={0};
 int result=0;
 if(drm_dp_dpcd_read_byte(&aux,0x101,&value)!=0||value!=0x42||rcount!=1||last_offset!=0x101)return 1;
 rmode=1;if(drm_dp_dpcd_read_byte(&aux,0x101,&value)!=-EPROTO)return 2;
 rmode=0;rcount=0;if(drm_dp_dpcd_read_data(&aux,0x200,buffer,4)!=0||rcount!=1)return 3;
 rmode=2;rcount=0;if(drm_dp_dpcd_read_data(&aux,0x200,buffer,4)!=-EIO||rcount!=2)return 4;
 rmode=3;rcount=0;if(drm_dp_dpcd_read_data(&aux,0x200,buffer,4)!=-EFAULT||rcount!=3)return 5;
 rmode=4;rcount=0;if(drm_dp_dpcd_read_data(&aux,0x200,buffer,4)!=-EPROTO||rcount!=3)return 6;
 wmode=0;if(drm_dp_dpcd_write_byte(&aux,0x111,0x50)!=0||wcount!=1||last_offset!=0x111)return 7;
 wmode=1;if(drm_dp_dpcd_write_data(&aux,0x300,buffer,4)!=-EPROTO)return 8;
 wmode=2;if(drm_dp_dpcd_write_byte(&aux,0x300,0)!=-EIO)return 9;
 drm_dp_link_train_clock_recovery_delay(&aux,caps);
 drm_dp_link_train_channel_eq_delay(&aux,caps);
 if(clock_calls!=1||eq_calls!=1||last_dpcd!=caps)return 10;
 if(result)return 11;
 return 0;
}
"""
        c=t/"contract.c";c.write_text(source)
        exe=t/"contract"
        proc=subprocess.run(["cc","-std=gnu11","-Wall","-Wextra","-Werror",
                             "-I",str(t/"include"),str(c),"-o",str(exe)],
                            capture_output=True,text=True,timeout=30)
        assert proc.returncode==0,proc.stderr
        outcome=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        assert outcome.returncode==0,(outcome.returncode,outcome.stderr)
        print("NETBSD_MODERN_DPCD_BYTE_FULL_SHORT_ERR_FALLBACK_DELAY_10_CASES_PASS")
        print("SHIM_SHA256",hashlib.sha256(a.shim.read_bytes()).hexdigest())

if __name__=="__main__":
    main()
