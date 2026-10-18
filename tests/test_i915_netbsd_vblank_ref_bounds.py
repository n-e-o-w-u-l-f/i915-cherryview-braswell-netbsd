#!/usr/bin/env python3
"""Verify exact NetBSD VBlank CRTC pipe guard and real C refcount behavior.

Source-level pointer-order safety, strict C11/UBSan valid and invalid
boundaries, and exact source patch/core-hook compatibility. This does NOT
build or run a native NetBSD kernel. In particular, compiler dead-store
elimination means an original invalid pointer expression is NOT claimed
to be reliably caught by UBSan at runtime.
"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

PIN = {
    "sys/external/bsd/drm2/dist/drm/drm_vblank.c":
        "06434bfc9f6693a1b61069c5c0e839b24671a5ba4d826fb001b0a897ceac206e",
    "sys/external/bsd/drm2/dist/include/drm/drm_vblank.h":
        "41a6574745795608b43bec288f04f0ae622271e604ff8b6e6d894e754acc37a9",
    "sys/external/bsd/drm2/drm/files.drmkms":
        "e507627bf8a6219ff38a79a2c6cebc98b1ee61540d354ce0eb15d2ee77785cb3",
}
PATCH_SHA256 = "2a4cc2546abd9e9e7be38a7e972d619a49991a1f02cff8333cacc35db9a1dd0f"
C_PATH = "sys/external/bsd/drm2/dist/drm/drm_vblank.c"
FUNC = ("drm_vblank_get_locked", "drm_vblank_put_locked")
PRE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <stddef.h>
struct drm_vblank_crtc {int refcount,enabled,disable_timer;};
struct drm_device {
 struct drm_vblank_crtc *vblank;
 unsigned num_crtcs;
 int event_lock,vblank_disable_immediate;
};
static int warnings,enable_fail,enable_calls,disable_calls,timer_calls;
#define assert_spin_locked(x) ((void)(x))
#define WARN_ON(x) ((x)?(warnings++,true):false)
static int atomic_add_return(int n,int *p){return *p+=n;}
static void atomic_dec(int *p){assert(*p>0);--*p;}
static int atomic_read(int *p){return *p;}
static bool atomic_dec_and_test(int *p){atomic_dec(p);return *p==0;}
static int drm_vblank_enable(struct drm_device *d,unsigned p){
 assert(d && d->vblank && p<d->num_crtcs);enable_calls++;
 if(enable_fail){atomic_dec(&d->vblank[p].refcount);return -EIO;}
 d->vblank[p].enabled=1;return 0;
}
static int drm_vblank_offdelay=20,jiffies=0;
#define HZ 100
static void vblank_disable_locked(struct drm_vblank_crtc *v,
struct drm_device *d,unsigned p){
 assert(v==&d->vblank[p]);disable_calls++;
}
static void mod_timer(int *t,long n){assert(t && n>0);++timer_calls;}
"""
MAIN = r"""
int main(void){
 struct drm_device dev={0};
 assert(drm_vblank_get_locked(&dev,37)==-EINVAL); /* uninitialized core */
 drm_vblank_put_locked(&dev,37); /* ignored invalid pipe, no pointer use */
 assert(warnings==1);
 struct drm_vblank_crtc v[1]={{0}};
 dev=(struct drm_device){.vblank=v,.num_crtcs=1};
 assert(drm_vblank_get_locked(&dev,99)==-EINVAL);
 drm_vblank_put_locked(&dev,99);
 assert(warnings==3 && v[0].refcount==0);
 puts("VBLANK_REF_INVALID_PIPE_NO_CRTC_PASS");
 assert(drm_vblank_get_locked(&dev,0)==0);
 assert(v[0].refcount==1 && v[0].enabled==1 && enable_calls==1);
 assert(drm_vblank_get_locked(&dev,0)==0 && v[0].refcount==2);
 drm_vblank_put_locked(&dev,0);assert(v[0].refcount==1);
 drm_vblank_put_locked(&dev,0);
 assert(v[0].refcount==0 && timer_calls==1);
 puts("VBLANK_REF_BALANCED_DOUBLE_GET_PUT_PASS");
 drm_vblank_put_locked(&dev,0); /* underflow is warned and refused */
 assert(warnings==4 && v[0].refcount==0);
 puts("VBLANK_REF_UNDERFLOW_REJECTED_PASS");
 v[0].enabled=0;enable_fail=1;
 assert(drm_vblank_get_locked(&dev,0)==-EIO && v[0].refcount==0);
 enable_fail=0;
 assert(drm_vblank_get_locked(&dev,0)==0 && v[0].refcount==1);
 drm_vblank_offdelay=-1;
 drm_vblank_put_locked(&dev,0);
 assert(disable_calls==1);
 puts("VBLANK_REF_ENABLE_ERROR_ROLLBACK_AND_IMMEDIATE_DISABLE_PASS");
 v[0].enabled=0;
 assert(drm_vblank_get_locked(&dev,0)==0);
 drm_vblank_offdelay=0;
 drm_vblank_put_locked(&dev,0);
 assert(disable_calls==1 && timer_calls==1);
 puts("VBLANK_REF_ZERO_OFFDELAY_NO_DISABLE_PASS");
 v[0].enabled=0;
 assert(drm_vblank_get_locked(&dev,0)==0);
 drm_vblank_offdelay=20;dev.vblank_disable_immediate=1;
 drm_vblank_put_locked(&dev,0);
 assert(disable_calls==1 && timer_calls==1);
 puts("VBLANK_REF_IMMEDIATE_FLAG_PREVENTS_TIMER_PASS");
 v[0].refcount=1;v[0].enabled=0;
 assert(drm_vblank_get_locked(&dev,0)==-EINVAL && v[0].refcount==1);
 v[0].refcount=0;
 puts("VBLANK_REF_DISABLED_ALREADY_HELD_GET_ROLLBACK_PASS");
 puts("I915_VBLANK_0018_EXTRACTED_C11_7_REFCASE_PASS");
 return 0;
}
"""


def must(ok, message):
    if not ok:
        raise AssertionError("VBLANK_0018_REFUSED: " + message)


def function(text, name):
    prefix = "static " + ("int " if name.endswith("get_locked")
                           else "void ") + name + "("
    must(text.count(prefix) == 1, "source owner " + name)
    i = text.index(prefix)
    j = text.index("\n}\n", i)
    return text[i:j + 3]


def guard_check(text):
    for name in FUNC:
        f = function(text, name)
        check = "if (WARN_ON(pipe >= dev->num_crtcs))"
        must(f.count(check) == 1, "bound check " + name)
        must(f.count("vblank = &dev->vblank[pipe];") == 1,
             "one CRTC pointer assignment " + name)
        must(f.index("vblank = &dev->vblank[pipe];") >
             f.index(check), "no pointer address before bounds " + name)
        must("struct drm_vblank_crtc *vblank;" in f,
             "deferred pointer declaration " + name)


def checked_call(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    must(p.returncode == 0,
         "command " + " ".join(str(x) for x in cmd) + ": " + p.stderr[:850])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--netbsd-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--core-hooks", type=Path, required=True)
    opt = parser.parse_args()
    original = {}
    for p, digest in PIN.items():
        data = (opt.netbsd_root / p).read_bytes()
        must(hashlib.sha256(data).hexdigest() == digest,
             "reference drift " + p)
        original[p] = data
    must(hashlib.sha256(opt.patch.read_bytes()).hexdigest() == PATCH_SHA256,
         "0018 candidate hash mismatch")
    orig = original[C_PATH].decode()
    for name in FUNC:
        old = function(orig, name)
        must(old.index("&dev->vblank[pipe]") <
             old.index("if (WARN_ON(pipe >= dev->num_crtcs))"),
             "original owner unexpectedly already guards pipe " + name)

    final = None
    with tempfile.TemporaryDirectory(prefix="i915-vblank-ref-") as temp:
        root = Path(temp)
        for first, second in ((opt.patch, opt.core_hooks),
                              (opt.core_hooks, opt.patch)):
            for p, data in original.items():
                file = root / p
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            for patch in (first, second):
                checked_call(["git", "-C", str(root), "apply", "--check",
                              str(patch.resolve())])
                checked_call(["git", "-C", str(root), "apply",
                              str(patch.resolve())])
            changed = (root / C_PATH).read_text()
            guard_check(changed)
            must("nb_i915_vblank_ref_get_locked" in changed,
                 "native locked wrapper lost")
            if final is None:
                final = changed
            else:
                must(final == changed, "patch apply order drift")
            for patch in (second, first):
                checked_call(["git", "-C", str(root), "apply", "--reverse",
                              str(patch.resolve())])
            for p, data in original.items():
                must((root / p).read_bytes() == data, "rollback drift " + p)
        must(final is not None, "missing patched source")
        # Source-extract exactly two real implementations; test their
        # return, refcount, boundary and timer/error semantics as host C.
        test = root / "refcases.c"
        exe = root / "refcases"
        test.write_text(PRE + "\n" + "\n".join(
            function(final, name) for name in FUNC) + MAIN)
        checked_call(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                      "-pedantic", "-fsanitize=undefined,pointer-overflow",
                      "-fno-sanitize-recover=all", str(test), "-o", str(exe)])
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        must(run.returncode == 0,
             "C refcount cases failed: " + run.stderr[-600:])
        print(run.stdout.strip())
        # Four distinct dangerous source mutations must fail the static
        # validation, even if optimizer elides an unused pointer in C.
        for name in FUNC:
            method = function(final, name)
            guard = "vblank = &dev->vblank[pipe];"
            mut = final.replace(method, method.replace(
                guard, "", 1).replace(
                    "struct drm_vblank_crtc *vblank;", "struct drm_vblank_crtc *vblank = &dev->vblank[pipe];", 1), 1)
            try:
                guard_check(mut)
            except AssertionError:
                pass
            else:
                raise AssertionError("accepted eager-pointer mutation "+name)
        for name in FUNC:
            method = function(final, name)
            mut = final.replace(method, method.replace(
                "if (WARN_ON(pipe >= dev->num_crtcs))",
                "if (false)", 1), 1)
            try:
                guard_check(mut)
            except AssertionError:
                pass
            else:
                raise AssertionError("accepted missing-bound mutation "+name)
        print("I915_VBLANK_0018_FOUR_SOURCE_MUTANTS_REFUSED")
        print("I915_VBLANK_0018_GENUINE_NETBSD_CORE_HOOKS_BOTH_ORDERS_PASS")
        print("LIMIT: host C/UBSan and source only; native HP compile, sched_FIFO/RR and hardware NOT_RUN")


if __name__ == "__main__":
    main()
