#!/usr/bin/env python3
"""F22 real pinned source composition, opt-in configuration and host C regression.

Applies the genuine F21 then F22 patches to full unmodified NetBSD C/config
files, extracts the exact F22 firmware failover helper, and executes it via
host GCC/Clang against independent mocked NetBSD/DRM device APIs. This is
NOT a native NetBSD object build, kernel link, or HP hardware boot.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
DRIVER = Path("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c")
CONFIG = Path("sys/external/bsd/drm2/i915drm/files.i915drmkms")
SHAS = {
    DRIVER: "9798385b02f247c08db9b16624d5ddc9d11a8ca5",
    CONFIG: "23d352b64eb1799caf3e9b2770f78795accc8439",
}
F21 = ROOT / "patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch"
F22 = ROOT / "patches/candidates/netbsd11-f22-i915-uefi-genfb-failover-after-probe-error-20261028.patch"

HOST = r"""
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>

typedef void *device_t;
typedef void *cfdata_t;
#define NODEV (-1)
struct consdev { int cn_dev; };
static struct consdev cons;
static struct consdev *cn_tab;
struct genfb_softc {
    device_t sc_dev;
    void *sc_private;
    void *sc_fbaddr;
};
struct i915drmkms_softc {
    struct genfb_softc sc_fw_genfb;
    int pending;
};
struct wsemuldisplaydev_attach_args { int console; };
struct genfb_ops { int placeholder; };
struct mock_props {
    bool is_console;
    bool has_console, has_width, has_height, has_depth, has_stride;
    bool has_address, has_virtual;
    uint32_t width, height, depth;
    uint16_t stride;
    uint64_t address, virtual_address;
};
typedef struct mock_props *prop_dictionary_t;
static struct mock_props dict;
static struct i915drmkms_softc sc;
static int token;
static int child_available, init_success, attach_error, assign_dev;
static int property_set_ok, searches, init_calls, attach_calls;
static int lock_held, locks, unlocks, errors, successes, set_calls;
static device_t self = &token;
static void *device_private(device_t device) {
    assert(device == self);
    return &sc;
}
static prop_dictionary_t device_properties(device_t device) {
    assert(device == self);
    return &dict;
}
static bool prop_dictionary_get_bool(prop_dictionary_t p,
                                      const char *key, bool *v) {
    assert(p == &dict && strcmp(key, "is_console") == 0);
    if (!p->has_console) return false;
    *v = p->is_console;
    return true;
}
static bool prop_dictionary_get_uint32(prop_dictionary_t p,
                                        const char *key, uint32_t *v) {
    assert(p == &dict);
    if (strcmp(key,"width") == 0) { *v=p->width; return p->has_width; }
    if (strcmp(key,"height") == 0) { *v=p->height; return p->has_height; }
    if (strcmp(key,"depth") == 0) { *v=p->depth; return p->has_depth; }
    assert(0);
    return false;
}
static bool prop_dictionary_get_uint16(prop_dictionary_t p,
                                        const char *key, uint16_t *v) {
    assert(p == &dict && strcmp(key, "linebytes") == 0);
    *v = p->stride;
    return p->has_stride;
}
static bool prop_dictionary_get_uint64(prop_dictionary_t p,
                                        const char *key, uint64_t *v) {
    assert(p == &dict);
    if (strcmp(key,"address")==0) { *v=p->address; return p->has_address; }
    if (strcmp(key,"virtual_address")==0) {
        *v=p->virtual_address; return p->has_virtual;
    }
    assert(0);
    return false;
}
static bool prop_dictionary_set_bool(prop_dictionary_t p, const char *key,
                                      bool value) {
    assert(p == &dict && strcmp(key,"enable_shadowfb")==0 && !value);
    set_calls++;
    return property_set_ok != 0;
}
#define CTASSERT(condition) _Static_assert((condition), "layout contract")
#define CFARGS(...) ((const void *)0)
#define KERNEL_LOCK(n, arg) do { \
    assert((n)==1 && lock_held==0); lock_held=1; locks++; \
} while (0)
#define KERNEL_UNLOCK_ONE(arg) do { \
    assert(lock_held==1); lock_held=0; unlocks++; \
} while (0)
static cfdata_t config_search(device_t device,
                             struct wsemuldisplaydev_attach_args *args,
                             const void *extra) {
    (void)extra;
    assert(device == self && args->console == 1 && lock_held == 1);
    searches++;
    return child_available ? (cfdata_t)&token : NULL;
}
static void genfb_init(struct genfb_softc *fb) {
    assert(fb == &sc.sc_fw_genfb && fb->sc_dev == self);
    init_calls++;
    if (init_success) {
        fb->sc_private = &token;
        fb->sc_fbaddr = (void *)(uintptr_t)dict.virtual_address;
    }
}
static int genfb_attach(struct genfb_softc *fb, struct genfb_ops *ops) {
    assert(fb == &sc.sc_fw_genfb && lock_held == 1 && ops!=NULL);
    attach_calls++;
    if (attach_error) return attach_error;
    if (assign_dev) cn_tab->cn_dev = 42;
    return 0;
}
static void aprint_error_dev(device_t device, const char *fmt, ...) {
    assert(device == self && fmt[0]!=0);
    errors++;
}
static void aprint_normal_dev(device_t device, const char *fmt, ...) {
    assert(device == self && fmt[0]!=0);
    successes++;
}
"""

MAIN = r"""
static void reset(void) {
    sc=(struct i915drmkms_softc){0};
    cons=(struct consdev){.cn_dev=NODEV};
    cn_tab=&cons;
    dict=(struct mock_props){
        .is_console=true, .has_console=true,
        .has_width=true, .has_height=true, .has_depth=true,
        .has_stride=true, .has_address=true, .has_virtual=true,
        .width=1366, .height=768, .depth=32, .stride=5464,
        .address=0xe0000000ULL, .virtual_address=0x10000000ULL
    };
    child_available=init_success=assign_dev=property_set_ok=1;
    attach_error=0;
    searches=init_calls=attach_calls=0;
    lock_held=locks=unlocks=errors=successes=set_calls=0;
}
static void verify_skipped(void) {
    assert(searches == 0 && init_calls == 0 && attach_calls == 0);
    assert(locks == 0 && unlocks == 0 && !lock_held);
    assert(successes == 0 && cons.cn_dev == NODEV);
}
int main(void) {
    int cases=0;
    reset();
    i915drmkms_fwfb_failover(self);
    assert(searches==1 && init_calls==1 && attach_calls==1);
    assert(locks==2 && unlocks==2 && !lock_held);
    assert(successes==1 && errors==0 && cons.cn_dev==42 && set_calls==1);
    cases++;

    reset(); dict.is_console=false;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.has_console=false;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); cn_tab=NULL;
    i915drmkms_fwfb_failover(self);
    assert(searches==0 && init_calls==0 && attach_calls==0); cases++;
    reset(); cons.cn_dev=33;
    i915drmkms_fwfb_failover(self);
    assert(searches==0 && init_calls==0 && attach_calls==0 &&
           cons.cn_dev==33); cases++;

    reset(); dict.width=200;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.height=200;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.width=9000;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.height=9000;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.depth=16;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.stride=1000;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.address=0;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.virtual_address=0;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.has_width=false;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); dict.has_virtual=false;
    i915drmkms_fwfb_failover(self); verify_skipped(); cases++;
    reset(); child_available=0;
    i915drmkms_fwfb_failover(self);
    assert(searches==1 && init_calls==0 && attach_calls==0 &&
           locks==1 && unlocks==1 && errors==1); cases++;
    reset(); property_set_ok=0;
    i915drmkms_fwfb_failover(self);
    assert(searches==1 && init_calls==0 && attach_calls==0 &&
           set_calls==1); cases++;
    reset(); init_success=0;
    i915drmkms_fwfb_failover(self);
    assert(searches==1 && init_calls==1 && attach_calls==0 &&
           errors==1 && successes==0); cases++;
    reset(); attach_error=ENXIO;
    i915drmkms_fwfb_failover(self);
    assert(searches==1 && init_calls==1 && attach_calls==1 &&
           locks==2 && unlocks==2 && errors==1 && successes==0); cases++;
    reset(); assign_dev=0;
    i915drmkms_fwfb_failover(self);
    assert(searches==1 && init_calls==1 && attach_calls==1 &&
           errors==1 && successes==0 && cons.cn_dev==NODEV); cases++;

    assert(cases==20);
    puts("F22_EXACT_FAILOVER_FUNCTION_20_CASES_PASS");
    return 0;
}
"""


def sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def check(ok: bool, why: str) -> None:
    if not ok:
        raise AssertionError(why)


def patch_apply(root: Path, patch: Path) -> None:
    for opts in (["--check"], []):
        proc = subprocess.run(["git","-C",str(root),"apply",
                               "--whitespace=error",*opts,str(patch)],
                              capture_output=True,text=True)
        check(proc.returncode == 0,
              f"{patch.name} git apply {opts} failed: {proc.stderr}")


def source_func(s: str) -> str:
    start=s.index("static void\ni915drmkms_fwfb_failover(device_t self)\n{")
    end=s.index("\n#endif /* HP_I915_FWFB_FAILOVER */",start)
    return s[start:end]


def main() -> None:
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--netbsd-tree",type=Path)
    modes.add_argument("--verified-blob-dir",type=Path)
    a=parser.parse_args()
    tree=(a.netbsd_tree or a.verified_blob_dir).resolve(strict=True)
    if a.netbsd_tree:
        head=subprocess.check_output(["git","-C",str(tree),"rev-parse",
                                      "HEAD"],text=True).strip()
        check(head==PIN,"wrong NetBSD Git HEAD")
    original={}
    for path,expected in SHAS.items():
        data=(tree/path).read_bytes()
        check(sha(data)==expected,f"unpinned NetBSD original file {path}")
        original[path]=data
    with tempfile.TemporaryDirectory(prefix="f22-real-source-") as t:
        root=Path(t)
        for path,data in original.items():
            dest=root/path
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
        patch_apply(root,F21)
        f21=(root/DRIVER).read_text()
        patch_apply(root,F22)
        f22=(root/DRIVER).read_text()
        conf=(root/CONFIG).read_text()
        check('defflag\topt_hp_i915_fwfb_failover.h\tHP_I915_FWFB_FAILOVER'
              in conf, "missing explicitly declared build flag")
        check('firmload, wsemuldisplaydev' in conf,
              "parent device cannot match fallback wsdisplay child")
        check('#include "opt_hp_i915_fwfb_failover.h"' in f22,
              "generated NetBSD option header absent")
        check(f22.count("#ifdef HP_I915_FWFB_FAILOVER")==4,
              "unexpected number of compile-time gated blocks")
        check(f22.count("#endif /* HP_I915_FWFB_FAILOVER */")==1,
              "helper not clearly compile-time guarded")
        check(f22.count("i915drmkms_fwfb_failover(self);")==1,
              "fallback call must only exist on the failure edge")
        check(f22.index("SIMPLEQ_EMPTY(&sc->sc_tasks)") <
              f22.index("i915drmkms_fwfb_failover(self);") <
              f22.index("sc->sc_drm_dev = pci_get_drvdata("),
              "fall back before DRM success, only when queue empty")
        check("struct genfb_softc\tsc_fw_genfb;" in f22,
              "i915 must embed a stable genfb softc")
        check("CTASSERT(offsetof(struct i915drmkms_softc, sc_fw_genfb) == 0)"
              in f22,"device_private-to-genfb poll layout missing")
        check("cn_tab->cn_dev != NODEV" in f22 and
              "child = config_search(self, &aa," in f22,
              "wrong native early-console preflight")
        # With the new option undefined, the helper, extra softc and call
        # must disappear, retaining F21 error-return semantics.
        off=re.sub(
            r"(?ms)^#ifdef HP_I915_FWFB_FAILOVER\n.*?^#endif(?: /\* HP_I915_FWFB_FAILOVER \*/)?\n",
            "",f22)
        off=off.replace('#include "opt_hp_i915_fwfb_failover.h"\n\n',"")
        # F22 braces its F21 one-statement conditional. Normalize only this
        # proven semantic equivalence (do not normalize unrelated C).
        old = ('\t\tif (SIMPLEQ_EMPTY(&sc->sc_tasks)) {\n'
               '\t\t\tatomic_store_relaxed(&sc->sc_task_thread, NULL);\n'
               '\t\t}\n')
        new = ('\t\tif (SIMPLEQ_EMPTY(&sc->sc_tasks))\n'
               '\t\t\tatomic_store_relaxed(&sc->sc_task_thread, NULL);\n')
        check(off.count(old)==1,"disabled branch unexpectedly altered")
        off=off.replace(old,new)
        # The removed standalone helper leaves one separator newline.
        off=off.replace("}\n\n\nstatic void\ni915drmkms_attach_real",
                        "}\n\nstatic void\ni915drmkms_attach_real")
        check(off==f21,"disabled F22 source differs from F21")

        function=source_func(f22)
        src=HOST+function+"\n"+MAIN
        compiled=0
        for cc in ("gcc","clang"):
            for std in ("gnu99","gnu11"):
                name=f"f22_{cc}_{std}"
                file=root/(name+".c")
                out=root/name
                file.write_text(src)
                run=subprocess.run(
                    [cc,"-std="+std,"-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     str(file),"-o",str(out)],
                    capture_output=True,text=True)
                check(run.returncode==0,name+": "+run.stderr)
                finished=subprocess.run([str(out)],capture_output=True,text=True)
                check(finished.returncode==0,name+": "+finished.stderr)
                check("20_CASES_PASS" in finished.stdout,
                      "host regression marker absent")
                compiled+=1
                print("F22_REAL_FUNCTION_GCC_CLANG_20_CASES_PASS",name)
        check(compiled==4,"expected four compilers")
    print("F22_F21_F22_PINNED_GIT_APPLY_OPTION_OFF_EXACT_80_HOST_C_CASES_PASS")
    print("F22_NATIVE_NETBSD_KERNEL_COMPILATION_AND_HP_BOOT_NOT_RUN")


if __name__=="__main__":
    main()
