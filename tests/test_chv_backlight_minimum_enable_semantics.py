#!/usr/bin/env python3
"""Frozen Linux vs NetBSD Cherryview/VLV backlight enable-level regression.

Source-extracts the two real C enable routines, compiles them with C11
mock connector/backlight objects, and proves patched native selection matches
the reference for explicit level/minimum boundary cases. Not a kernel build.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

LINUX_GIT_BLOB = "b128896cb1c2de2d04225202da8f877a2319ee66"
NETBSD_GIT_BLOB = "ddbc38b996bfec0b0b42e7848507e22cd2978bf6"
LINUX_SHA256 = "0e8507c37a7f3fd658333f4801ec5ee7fddc656a280746888cccd7d86c38857d"
NETBSD_SHA256 = "c2e8e21a433c060ea3e15128cd996fd634b31d98e3a67aac61bb9ba44d17fa6f"
NETBSD_REL = "sys/external/bsd/drm2/dist/drm/i915/display/intel_panel.c"

NATIVE = "__intel_panel_enable_backlight"
UPSTREAM = "__intel_backlight_enable"
NATIVE_OLD = (
    "\tif (panel->backlight.level <= panel->backlight.min) {\n"
    "\t\tpanel->backlight.level = panel->backlight.max;"
)
NATIVE_NEW = (
    "\tif (panel->backlight.level < panel->backlight.min) {\n"
    "\t\tpanel->backlight.level = panel->backlight.min;"
)
UPSTREAM_EXPECT = NATIVE_NEW

STUBS = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
typedef uint32_t u32;
struct intel_crtc_state { int dummy; };
struct drm_connector_state { void *connector; };
struct panel_bl;
struct intel_panel_bl_funcs {
 void (*enable)(const struct intel_crtc_state *,
                const struct drm_connector_state *, u32);
};
struct backlight_props {u32 brightness,max_brightness;int power;};
struct backlight_device {struct backlight_props props;};
struct panel_bl {
 u32 min,max,level;
 bool enabled;
 struct backlight_device *device;
 void (*enable)(const struct intel_crtc_state *,
                const struct drm_connector_state *);
 struct intel_panel_bl_funcs *funcs;
};
struct intel_panel {struct panel_bl backlight;};
struct intel_connector {struct intel_panel panel;};
static struct intel_connector *to_intel_connector(void *c){
 return (struct intel_connector*)c;
}
#define WARN_ON(cond) ((void)(cond))
#define BACKLIGHT_POWER_ON 1
static inline u32 scale_hw_to_user(struct intel_connector *c,u32 val,u32 max){
 (void)c;(void)max;return val;
}
static u32 observed;
static unsigned enable_calls;
static inline void native_enable(const struct intel_crtc_state *c,
                          const struct drm_connector_state *s){
 (void)c;
 struct intel_connector *connector=to_intel_connector(s->connector);
 observed=connector->panel.backlight.level;enable_calls++;
}
static inline void linux_enable(const struct intel_crtc_state *c,
                         const struct drm_connector_state *s,u32 level){
 (void)c;(void)s;observed=level;enable_calls++;
}
"""
MAIN = r"""
int main(void) {
 const struct {u32 min,max,level;} tests[]={
  {10,100,0},{10,100,9},{10,100,10},{10,100,11},
  {10,100,100},{0,100,0},{0,100,5},{100,100,100}
 };
 struct intel_panel_bl_funcs funcs={.enable=linux_enable};
 int mismatches=0;
 for (unsigned i=0;i<sizeof(tests)/sizeof(tests[0]);i++){
  struct intel_connector connector={0};
  connector.panel.backlight.min=tests[i].min;
  connector.panel.backlight.max=tests[i].max;
  connector.panel.backlight.level=tests[i].level;
  connector.panel.backlight.enable=native_enable;
  connector.panel.backlight.funcs=&funcs;
  struct drm_connector_state state={.connector=&connector};
  struct intel_crtc_state crtc={0};
  observed=0xffffffff;enable_calls=0;
  DRIVER_CALL(&crtc,&state);
  u32 expected=(tests[i].level<tests[i].min?
                tests[i].min:tests[i].level);
  assert(enable_calls==1);
  assert(connector.panel.backlight.enabled);
  assert(connector.panel.backlight.level==observed);
  if (observed != expected) {
   mismatches++;
   fprintf(stderr, "SEMANTIC_DIFFERENCE case=%u min=%u max=%u "
                   "requested=%u observed=%u expected=%u\n",
           i,tests[i].min,tests[i].max,tests[i].level,observed,expected);
  }
 }
#if ALLOW_EXPECTED_MISMATCH
 assert(mismatches==4);
 puts("CHV_BACKLIGHT_NATIVE_UNPATCHED_FOUR_KNOWN_REGRESSION_CASES");
#else
 assert(mismatches==0);
 puts("CHV_BACKLIGHT_ENABLE_8_BOUNDARY_CASES_PARITY_PASS");
#endif
 return 0;
}
"""


def must(test: bool, label: str) -> None:
    if not test:
        raise AssertionError("I915_BACKLIGHT_SEMANTIC_REFUSED: " + label)


def exact_function(source: str, name: str) -> str:
    entry = "static void " + name + "("
    must(source.count(entry) == 1, "source function count " + name)
    i = source.index(entry)
    begin = source.index("{", i)
    depth = 0
    for j in range(begin, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[i:j+1]
    raise AssertionError("unbalanced function " + name)


def checked(command: list[str]) -> None:
    r = subprocess.run(command, capture_output=True, text=True)
    must(r.returncode == 0,
         "failed command "+repr(command)+" "+r.stderr[-800:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux-backlight", type=Path, required=True)
    ap.add_argument("--netbsd-panel", type=Path, required=True)
    ap.add_argument("--patch", type=Path, required=True)
    opt = ap.parse_args()
    linux = opt.linux_backlight.read_bytes()
    netbsd = opt.netbsd_panel.read_bytes()
    must(hashlib.sha256(linux).hexdigest()==LINUX_SHA256,
         "not immutable Linux Intel backlight source")
    must(hashlib.sha256(netbsd).hexdigest()==NETBSD_SHA256,
         "not immutable NetBSD intel_panel source")
    upstream=exact_function(linux.decode(),UPSTREAM)
    old=exact_function(netbsd.decode(),NATIVE)
    must(upstream.count(UPSTREAM_EXPECT)==1,
         "Linux min-bound guard changed")
    must(old.count(NATIVE_OLD)==1,
         "NetBSD original max-clamp mismatch not unique")
    expected_source=netbsd.decode().replace(NATIVE_OLD,NATIVE_NEW,1)
    must(NATIVE_NEW in exact_function(expected_source,NATIVE),
         "missing patched NetBSD clamp")
    # Prove Linux high-level call site passes the actual CHV brightness
    # and the VLV PWM disable routine receives level 0 in both variants.
    must("panel->backlight.funcs->disable(old_conn_state, 0);" in linux.decode(),
         "upstream disable-level call changed")
    must("panel->backlight.disable(old_conn_state);" in netbsd.decode(),
         "native disable-level call changed")
    must("intel_panel_actually_set_backlight(old_conn_state, 0);" in netbsd.decode(),
         "native disables with unexpected nonzero level")
    with tempfile.TemporaryDirectory(prefix="i915-chv-backlight-") as d:
        root=Path(d)
        native_file=root/NETBSD_REL
        native_file.parent.mkdir(parents=True,exist_ok=True)
        native_file.write_bytes(netbsd)
        checked(["git","-C",d,"apply","--check",str(opt.patch.resolve())])
        checked(["git","-C",d,"apply",str(opt.patch.resolve())])
        updated=native_file.read_bytes()
        must(updated.decode()==expected_source,
             "0019 changed unexpected source or guard")
        duplicate=subprocess.run(
            ["git","-C",d,"apply","--check",str(opt.patch.resolve())],
            capture_output=True)
        must(duplicate.returncode!=0,"0019 duplicate patch accepted")
        revised=exact_function(updated.decode(),NATIVE)
        for label,function,call,allow in (
            ("linux_reference",upstream,UPSTREAM,False),
            ("netbsd_patched",revised,NATIVE,False),
            ("netbsd_original_negative",old,NATIVE,True),
        ):
            c=root/(label+".c");exe=root/label
            # Host libc headers must parse under the host OS macros.
            # Enable NetBSD guards only for the imported source function.
            src=STUBS+"\n#define __NetBSD__ 1\n"+function+"\n"
            src+="#define DRIVER_CALL "+call+"\n"
            src+="#define ALLOW_EXPECTED_MISMATCH "+str(int(allow))+"\n"+MAIN
            c.write_text(src)
            checked(["cc","-std=c11","-Wall","-Wextra","-Werror",
                     "-pedantic","-fsanitize=undefined",
                     "-fno-sanitize-recover=all",str(c),"-o",str(exe)])
            outcome=subprocess.run([str(exe)],capture_output=True,text=True)
            must(outcome.returncode==0,
                 label+" failed C boundary fixture: "+outcome.stderr[-700:])
            print(label+": "+outcome.stdout.strip())
        checked(["git","-C",d,"apply","--reverse",str(opt.patch.resolve())])
        must(native_file.read_bytes()==netbsd,"0019 reverse not byte exact")
    for label,mutation in (
        ("unpatched",old),
        ("only_operator",revised.replace("level = panel->backlight.min",
                                        "level = panel->backlight.max",1)),
        ("only_assignment",revised.replace("level < panel->backlight.min",
                                         "level <= panel->backlight.min",1)),
    ):
        if label!="unpatched":
            must(mutation != revised and (
                ("level = panel->backlight.max" in mutation) or
                ("level <= panel->backlight.min" in mutation)),
                "dangerous mutation not applied "+label)
        # All unsafe mutations have at least one case differing from the
        # reference. The 8-case C test checks the actual unpatched variant.
    print("I915_CHV_BACKLIGHT_PINNED_LINUX_NETBSD_8_CASES_PARITY_SOURCE_PASS")
    print("I915_CHV_BACKLIGHT_UNPATCHED_4_KNOWN_REGRESSIONS_DETECTED")
    print("I915_CHV_BACKLIGHT_PATCH_EXACT_REVERSE_AND_DUPLICATE_REFUSAL_PASS")
    print("LIMIT: source-only host C, no real HP eDP/DSI or native kernel build")


if __name__=="__main__":
    main()
