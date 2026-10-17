#!/usr/bin/env python3
"""NetBSD native C behavioral regression for real MST HPD ESI/ACK transition."""
import argparse
import hashlib
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tempfile

PIN = "cc051477f435552251282d699afb28a69b307478234d1541cec8c350c2287936"

def extract(body, kind, name):
    matches = list(re.finditer(r"(?m)^"+kind+r"\s*\n?"+re.escape(name)+r"\(",body))
    assert len(matches)==1,(name,len(matches))
    start=matches[0].start()
    open_brace=body.index("{",matches[0].end())
    depth=0
    for idx in range(open_brace,len(body)):
        if body[idx]=="{":depth+=1
        if body[idx]=="}":
            depth-=1
            if not depth:return body[start:idx+1]
    raise AssertionError("missing C function closing brace")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--patched-c",required=True,type=Path)
    options=ap.parse_args()
    if platform.system()!="NetBSD" or not socket.gethostname().startswith("hp"):
        ap.error("native C regression restricted to HP NetBSD")
    content=options.patched_c.read_bytes()
    assert hashlib.sha256(content).hexdigest()==PIN,"MST provider changed"
    body=content.decode()
    functions=[
        extract(body,"int","nb_i915_drm_dp_mst_hpd_irq_handle_event"),
        extract(body,"void","nb_i915_drm_dp_mst_hpd_irq_send_new_request"),
        extract(body,"int","drm_dp_mst_hpd_irq")
    ]
    fixture=r"""
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
typedef uint8_t u8;
#define DP_DOWN_REP_MSG_RDY (1U << 4)
#define DP_UP_REQ_MSG_RDY (1U << 5)
struct drm_dp_mst_topology_mgr { int sink_count; };
static int down_calls,up_calls,kicks,down_status,up_status;
static int drm_dp_mst_handle_down_rep(struct drm_dp_mst_topology_mgr *m)
{ (void)m;down_calls++;return down_status; }
static int drm_dp_mst_handle_up_req(struct drm_dp_mst_topology_mgr *m)
{ (void)m;up_calls++;return up_status; }
static void drm_dp_mst_kick_tx(struct drm_dp_mst_topology_mgr *m)
{ (void)m;kicks++; }
""" + "\n".join(functions) + r"""
static void reset(void){
 down_calls=up_calls=kicks=down_status=up_status=0;
}
int main(void){
 struct drm_dp_mst_topology_mgr mgr={.sink_count=2};
 u8 esi[4]={2,0,0,0},ack[4]={0,0,0,0};
 bool handled=true;
 reset();
 if(nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,ack,&handled)!=0 ||
    handled||kicks||ack[1])return 1;
 reset();esi[0]=3;
 if(nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,ack,&handled)!=0 ||
    !handled||mgr.sink_count!=3||ack[1]||kicks)return 2;
 reset();esi[1]=DP_DOWN_REP_MSG_RDY;down_status=-EIO;
 if(nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,ack,&handled)!=-EIO ||
    !handled||down_calls!=1||up_calls||kicks||
    ack[1]!=DP_DOWN_REP_MSG_RDY)return 3;
 reset();ack[1]=0;esi[1]=DP_UP_REQ_MSG_RDY;up_status=-ETIMEDOUT;
 if(nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,ack,&handled)!=-ETIMEDOUT ||
    !handled||up_calls!=1||down_calls||kicks||
    ack[1]!=DP_UP_REQ_MSG_RDY)return 4;
 reset();ack[1]=0;esi[1]=DP_DOWN_REP_MSG_RDY|DP_UP_REQ_MSG_RDY;
 if(nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,ack,&handled)!=0 ||
    !handled||down_calls!=1||up_calls!=1||
    ack[1]!=(DP_DOWN_REP_MSG_RDY|DP_UP_REQ_MSG_RDY)||kicks)return 5;
 nb_i915_drm_dp_mst_hpd_irq_send_new_request(&mgr);
 if(kicks!=1)return 6;
 reset();
 if(nb_i915_drm_dp_mst_hpd_irq_handle_event(NULL,esi,ack,&handled)!=-EINVAL||
    nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,NULL,&handled)!=-EINVAL||
    nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,NULL,ack,&handled)!=-EINVAL||
    nb_i915_drm_dp_mst_hpd_irq_handle_event(&mgr,esi,ack,NULL)!=-EINVAL||
    kicks||down_calls||up_calls)return 7;
 reset();
 if(drm_dp_mst_hpd_irq(&mgr,esi,&handled)!=0 ||
    !handled||down_calls!=1||up_calls!=1||kicks!=1)return 8;
 puts("NETBSD_REAL_MST_HPD_ACK_SPLIT_AND_LEGACY_8_CASES_PASS");
 return 0;
}
"""
    cc=shutil.which("cc")
    assert cc
    with tempfile.TemporaryDirectory(prefix="hp-mst-behavior-") as td:
        p=Path(td)/"mst.c";out=Path(td)/"mst"
        p.write_text(fixture)
        r=subprocess.run([cc,"-std=gnu11","-O0","-Wall","-Wextra","-Werror",
                          str(p),"-o",str(out)],capture_output=True,text=True,timeout=40)
        assert r.returncode==0,r.stderr
        r=subprocess.run([str(out)],capture_output=True,text=True,timeout=20)
        assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
        print(r.stdout.strip())

if __name__=="__main__":
    main()
