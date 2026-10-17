#!/usr/bin/env python3
"""Run native HP C tests against the exact patched NetBSD LSPCON provider."""
import argparse
import hashlib
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tempfile

PIN = "d5d0a707c04923026d8aa132db04173c3652dd0ccb430087cfde08cf031dcaff"

def extract(source, name):
    matches = list(re.finditer(r"(?m)^int\s*\n?" + re.escape(name) + r"\(", source))
    assert len(matches) == 1, (name, len(matches))
    start = matches[0].start()
    begin = source.index("{", matches[0].end())
    depth = 0
    for i in range(begin, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError("unclosed C function " + name)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--patched-c", required=True, type=Path)
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp"):
        p.error("native C execution is reserved for the HP NetBSD target")
    source = a.patched_c.read_bytes()
    assert hashlib.sha256(source).hexdigest() == PIN, "DRM provider SHA drift"
    body = source.decode()
    fixture = r"""
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
typedef uint8_t u8;
struct drm_device { int dummy; };
struct i2c_adapter { int dummy; };
enum drm_lspcon_mode { DRM_LSPCON_MODE_INVALID, DRM_LSPCON_MODE_LS,
                       DRM_LSPCON_MODE_PCON };
#define DP_DUAL_MODE_LSPCON_MODE_PCON 0x1
#define DP_DUAL_MODE_LSPCON_MODE_CHANGE 0x40
#define DRM_ERROR(...) ((void)0)
#define DRM_DEBUG_KMS(...) ((void)0)
static int write_error, get_error, reads, sleeping_ms, threshold;
static u8 last_written;
static int drm_dp_dual_mode_write(struct i2c_adapter *a, u8 offset,
                                  const void *buffer, size_t count)
{
 (void)a;
 if (offset != DP_DUAL_MODE_LSPCON_MODE_CHANGE || count != 1) return -EINVAL;
 if (write_error) return write_error;
 last_written = *(const u8 *)buffer;
 return 0;
}
static int drm_lspcon_get_mode(struct i2c_adapter *a, enum drm_lspcon_mode *v)
{
 (void)a;
 if (get_error) return get_error;
 reads++;
 *v = reads >= threshold ? DRM_LSPCON_MODE_PCON : DRM_LSPCON_MODE_LS;
 return 0;
}
static void msleep(unsigned int ms) { sleeping_ms += (int)ms; }
""" + extract(body, "nb_i915_drm_lspcon_set_mode") + "\n" + extract(body, "drm_lspcon_set_mode") + r"""
static void reset(int pcon_after) {
 write_error=0;get_error=0;reads=0;sleeping_ms=0;threshold=pcon_after;
 last_written=0;
}
int main(void) {
 struct drm_device d = {0};
 struct i2c_adapter a = {0};
 reset(1);
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,37)!=0 ||
     reads!=1 || sleeping_ms!=0 || last_written!=1) return 1;
 reset(3);
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,37)!=0 ||
     reads!=3 || sleeping_ms!=20) return 2;
 reset(1000);
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,37)!=-ETIMEDOUT ||
     sleeping_ms!=37 || reads!=4) return 3;
 reset(1000);
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,0)!=-ETIMEDOUT ||
     sleeping_ms!=0 || reads!=1) return 4;
 reset(1000);write_error=-EIO;
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,40)!=-EIO ||
     sleeping_ms!=0 || reads!=0) return 5;
 reset(1000);get_error=-EFAULT;
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,40)!=-EFAULT ||
     sleeping_ms!=0 || reads!=0) return 6;
 reset(1000);
 if (drm_lspcon_set_mode(&a,DRM_LSPCON_MODE_PCON)!=-ETIMEDOUT ||
     sleeping_ms!=200 || reads!=20) return 7;
 reset(1000);
 if (nb_i915_drm_lspcon_set_mode(&d,&a,DRM_LSPCON_MODE_PCON,-5)!=-ETIMEDOUT ||
     sleeping_ms!=0) return 8;
 puts("I915_NETBSD_REAL_LSPCON_TIMEOUT_AND_LEGACY_8_CASES_PASS");
 return 0;
}
"""
    cc = shutil.which("cc")
    assert cc, "HP native compiler absent"
    with tempfile.TemporaryDirectory(prefix="i915-lspcon-native-") as d:
        src = Path(d) / "probe.c"
        exe = Path(d) / "probe"
        src.write_text(fixture)
        build = subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                               "-O0", str(src), "-o", str(exe)],
                               capture_output=True, text=True, timeout=30)
        assert build.returncode == 0, build.stderr
        test = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        assert test.returncode == 0, (test.returncode, test.stdout, test.stderr)
        print(test.stdout.strip())

if __name__ == "__main__":
    main()
