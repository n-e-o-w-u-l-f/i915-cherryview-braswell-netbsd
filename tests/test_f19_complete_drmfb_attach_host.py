#!/usr/bin/env python3
"""C-compile the *complete* exact F19-patched NetBSD drmfb_attach().

A disposable mock of external kernel, DRM, property, and autoconf APIs lets
host GCC/Clang execute all function paths. No handwritten replacement for
the native drmfb_attach() implementation is used. This is NOT an ABI compile.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
PATH = Path("sys/external/bsd/drm2/drm/drmfb.c")
SHA = "f71bee4c525b4199dc4e3eb52ad3f321787e5905"
PATCH = ROOT / "patches/candidates/netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch"

PREAMBLE = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void *device_t;
typedef void *cfdata_t;
typedef struct mock_dict *prop_dictionary_t;
struct mock_dict {
    bool is_console;
    uint32_t width, height;
    bool has_console_property;
};
static struct mock_dict parent_dict, child_dict;
static int parent_token, device_token;
static struct drmfb_softc *current_softc;

static int child_present, vga_present, genfb_console, genfb_enabled;
static int searches, vga_detaches, vga_disables, searched_console;
static int genfb_inits, genfb_attaches, locked, locks, unlocks;
static int error_reports, is_console_sets;

struct drm_device { int unused; };
struct drm_fb_helper { struct drm_device *dev; };
struct drm_fb_helper_surface_size {
    uint32_t surface_width, surface_height, surface_bpp;
};
struct drm_property_blob { size_t length; void *data; };
struct drm_connector { struct drm_property_blob *edid_blob_ptr; };
struct drm_connector_list_iter { int unused; };
struct drmfb_params {
    bool (*dp_is_vga_console)(struct drm_device *);
    void (*dp_disable_vga)(struct drm_device *);
};
struct drmfb_attach_args {
    device_t da_dev;
    struct drm_fb_helper *da_fb_helper;
    struct drm_fb_helper_surface_size *da_fb_sizes;
    void *da_fb_vaddr;
    uint16_t da_fb_linebytes;
    const struct drmfb_params *da_params;
};
struct genfb_softc { device_t sc_dev; };
struct genfb_ops {
    void (*genfb_ioctl)(void);
    void (*genfb_mmap)(void);
    void (*genfb_enable_polling)(void);
    void (*genfb_disable_polling)(void);
};
struct drmfb_softc {
    struct genfb_softc sc_genfb;
    struct drmfb_attach_args sc_da;
};
struct wsemuldisplaydev_attach_args { int console; };

static void drmfb_genfb_ioctl(void) {}
static void drmfb_genfb_mmap(void) {}
static void drmfb_genfb_enable_polling(void) {}
static void drmfb_genfb_disable_polling(void) {}
static int drmfb_genfb_mode_callback;

#define __diagused __attribute__((unused))
#define CFARGS(...) NULL
#define CTASSERT(x) _Static_assert((x), "CTASSERT")
#define KASSERTMSG(expr, ...) assert(expr)
#define KERNEL_LOCK(n,arg) do { \
    assert((n) == 1); assert(!locked); locked=1; locks++; \
} while (0)
#define KERNEL_UNLOCK_ONE(arg) do { \
    assert(locked); locked=0; unlocks++; \
} while (0)

static device_t device_parent(device_t dev)
{ assert(dev == &device_token); return &parent_token; }
static void *device_private(device_t dev)
{ assert(dev == &device_token); return current_softc; }
static const char *device_xname(device_t dev)
{ (void)dev; return "intelfb0"; }
static prop_dictionary_t device_properties(device_t dev)
{
    if (dev == &parent_token) return &parent_dict;
    assert(dev == &device_token);
    return &child_dict;
}
static bool prop_dictionary_get_bool(prop_dictionary_t d,
                                     const char *key, bool *out)
{
    assert(strcmp(key, "is_console") == 0);
    if (!d->has_console_property) return false;
    *out = d->is_console;
    return true;
}
static void prop_dictionary_set_bool(prop_dictionary_t d,
                                     const char *key, bool value)
{
    assert(d == &child_dict);
    assert(strcmp(key, "is_console") == 0);
    is_console_sets++;
    d->is_console = value;
}
static void prop_dictionary_set_uint32(prop_dictionary_t d,
                                       const char *key, uint32_t value)
{
    assert(d == &child_dict);
    if (strcmp(key,"width") == 0) d->width = value;
    if (strcmp(key,"height") == 0) d->height = value;
}
static void prop_dictionary_set_uint8(prop_dictionary_t d,
                                      const char *key, uint8_t value)
{ (void)d; (void)key; (void)value; }
static void prop_dictionary_set_uint16(prop_dictionary_t d,
                                       const char *key, uint16_t value)
{ (void)d; (void)key; (void)value; }
static void prop_dictionary_set_uint64(prop_dictionary_t d,
                                       const char *key, uint64_t value)
{ (void)d; (void)key; (void)value; }
static void prop_dictionary_set_data(prop_dictionary_t d, const char *key,
                                     const void *data, size_t length)
{ (void)d; (void)key; (void)data; (void)length; }
static void drm_connector_list_iter_begin(struct drm_device *dev,
                                           struct drm_connector_list_iter *it)
{ (void)dev; (void)it; }
static void drm_connector_list_iter_end(struct drm_connector_list_iter *it)
{ (void)it; }
#define drm_client_for_each_connector_iter(connector, it) \
    for ((connector)=NULL; (connector)!=NULL;)
static bool genfb_is_console(void) { return genfb_console != 0; }
static bool genfb_is_enabled(void) { return genfb_enabled != 0; }
#if NVGA > 0
static void vga_cndetach(void) { assert(!locked); vga_detaches++; }
#endif
static bool is_vga_console(struct drm_device *dev)
{ (void)dev; return vga_present != 0; }
static void disable_vga(struct drm_device *dev)
{ (void)dev; vga_disables++; }
static cfdata_t config_search(device_t dev,
                    struct wsemuldisplaydev_attach_args *args,
                    const void *cfargs)
{
    (void)dev; (void)cfargs;
    assert(locked);
    searches++;
    searched_console = args->console;
    return child_present ? (cfdata_t)&searches : NULL;
}
static void aprint_error_dev(device_t dev, const char *format, ...)
{
    (void)device_xname(dev);
    assert(strstr(format, "no wsdisplay child configured") != NULL);
    error_reports++;
}
static void genfb_init(struct genfb_softc *sc)
{ assert(sc->sc_dev == &device_token); genfb_inits++; }
static int genfb_attach(struct genfb_softc *sc, struct genfb_ops *ops)
{ (void)sc; (void)ops; assert(locked); genfb_attaches++; return 0; }
"""

POSTAMBLE = r"""
int main(void)
{
    int cases = 0;
    for (int pmode=0; pmode<4; pmode++) {
        for (int vga=0; vga<=1; vga++) {
            for (int has_child=0; has_child<=1; has_child++) {
                for (int fwgen=0; fwgen<=1; fwgen++) {
                    struct drm_device dev = {0};
                    struct drm_fb_helper helper = {.dev = &dev};
                    struct drm_fb_helper_surface_size sizes = {
                        .surface_width=1280,.surface_height=800,.surface_bpp=32
                    };
                    static uint32_t pixels[4];
                    struct drmfb_params params = {
                        .dp_is_vga_console=is_vga_console,
                        .dp_disable_vga=disable_vga
                    };
                    struct drmfb_attach_args args = {
                        .da_dev=&device_token, .da_fb_helper=&helper,
                        .da_fb_sizes=&sizes, .da_fb_vaddr=pixels,
                        .da_fb_linebytes=5120, .da_params=&params
                    };
                    struct drmfb_softc sc = {0};
                    current_softc = &sc;
                    parent_dict = (struct mock_dict){0};
                    child_dict = (struct mock_dict){0};
                    // pmode: no property, explicit false, explicit true,
                    // no property with genfb firmware eligibility.
                    parent_dict.has_console_property = (pmode==1 || pmode==2);
                    parent_dict.is_console = pmode==2;
                    genfb_console = fwgen;
                    genfb_enabled = pmode==3;
                    vga_present = vga;
                    child_present = has_child;
                    searches=searched_console=vga_detaches=vga_disables=0;
                    genfb_inits=genfb_attaches=locked=locks=unlocks=0;
                    error_reports=is_console_sets=0;

                    const int owns_console =
                        (pmode==2) ||
                        ((pmode==0 || pmode==3) && fwgen && genfb_enabled) ||
                        (NVGA > 0 && vga);
                    const int expected_error = owns_console && !has_child;
                    const int expected_vga = NVGA > 0 && vga && !expected_error;
                    int result = drmfb_attach(&sc, &args);

                    assert(result == (expected_error ? ENXIO : 0));
                    assert(searches == owns_console);
                    assert(searched_console == owns_console);
                    assert(locks == (owns_console + !expected_error));
                    assert(unlocks == locks && !locked);
                    assert(error_reports == expected_error);
                    assert(vga_detaches == expected_vga);
                    assert(vga_disables == expected_vga);
                    assert(genfb_inits == !expected_error);
                    assert(genfb_attaches == !expected_error);
                    assert(is_console_sets == !expected_error);
                    if (!expected_error) {
                        assert(child_dict.is_console == (owns_console != 0));
                        assert(child_dict.width == 1280);
                        assert(child_dict.height == 800);
                    }
                    cases++;
                }
            }
        }
    }
    assert(cases == 32);
    printf("F19_COMPLETE_ACTUAL_DRMFB_ATTACH_32_CASES_PASS_NVGA_%d\n",NVGA);
    return 0;
}
"""


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def checked(ok: bool, why: str) -> None:
    if not ok:
        raise AssertionError(why)


def extract_function(text: str) -> str:
    needle = "int\ndrmfb_attach(struct drmfb_softc *sc, const struct drmfb_attach_args *da)\n"
    checked(text.count(needle) == 1, "not unique native drmfb_attach")
    start = text.index(needle)
    end = text.index("\nint\ndrmfb_detach(", start)
    return text[start:end]


def main() -> None:
    argp = argparse.ArgumentParser()
    opts = argp.add_mutually_exclusive_group(required=True)
    opts.add_argument("--netbsd-tree", type=Path)
    opts.add_argument("--verified-blob-dir", type=Path)
    a = argp.parse_args()
    tree = (a.netbsd_tree or a.verified_blob_dir).resolve(strict=True)
    if a.netbsd_tree:
        sha = subprocess.check_output(
            ["git","-C",str(tree),"rev-parse","HEAD"],text=True).strip()
        checked(sha == PIN, "wrong NetBSD HEAD")
    data = (tree / PATH).read_bytes()
    checked(blob_sha(data) == SHA, "wrong actual NetBSD DRMFB original")
    with tempfile.TemporaryDirectory(prefix="f19-complete-func-") as t:
        stage = Path(t)
        target = stage / PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        subprocess.run(["git","-C",str(stage),"apply","--check",str(PATCH)],
                       capture_output=True,check=True)
        subprocess.run(["git","-C",str(stage),"apply",str(PATCH)],
                       capture_output=True,check=True)
        old_fn = extract_function(data.decode())
        new_fn = extract_function(target.read_text())
        checked(target.read_text().replace(new_fn, old_fn) == data.decode(),
                "unexpected non-function changes")
        for cc in ("gcc", "clang"):
            for dialect in ("gnu99", "gnu11"):
                for nvga in (0, 1):
                    name = f"{cc}_{dialect}_{nvga}"
                    source = PREAMBLE + new_fn + POSTAMBLE
                    c = stage / (name + ".c")
                    executable = stage / (name + ".out")
                    c.write_text(source)
                    cp = subprocess.run([
                        cc,"-std="+dialect,"-DNVGA="+str(nvga),
                        "-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined","-fno-sanitize-recover=all",
                        str(c),"-o",str(executable)
                    ],capture_output=True,text=True)
                    checked(cp.returncode == 0, name+" compile: "+cp.stderr)
                    rc = subprocess.run([str(executable)],
                                        capture_output=True,text=True)
                    checked(rc.returncode == 0, name+" run: "+rc.stderr)
                    checked("32_CASES_PASS_NVGA_" in rc.stdout,
                            name+" wrong positive marker")
                    print("F19_FULL_NATIVE_FUNCTION_HOST_TEST_PASS",name)
    print("F19_REAL_DRMFB_COMPLETE_FUNCTION_256_HOST_CASES_GCC_CLANG_UBSAN_PASS")
    print("F19_NATIVE_NETBSD_KERNEL_OBJECT_NOT_RUN")


if __name__ == "__main__":
    main()
