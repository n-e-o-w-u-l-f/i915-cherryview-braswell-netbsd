#!/usr/bin/env python3
"""F20 source/host-C oracle for x86 UEFI GOP console initialization status.

Uses actual NetBSD/src pinned original C, real git apply of proposed fix,
extracts the *unmodified patched* branch and runs GCC/Clang fixture variants.
Also proves F19 is downstream from probe and cannot cover early i915 failure.

No native NetBSD object, installed kernel, or HP boot is produced.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
FILES = {
    Path("sys/arch/x86/x86/consinit.c"): "9ef384c2c07a2202040d0fe672fdfa58a5c07a78",
    Path("sys/arch/x86/x86/genfb_machdep.c"): "61cbebad88025df44159f2b8fc05279c836e341f",
    Path("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c"): "9798385b02f247c08db9b16624d5ddc9d11a8ca5",
    Path("sys/dev/pci/genfb_pci.c"): "effc88cf3160d92b7a0aa8ef6af80da84e5a963b",
    Path("sys/dev/wscons/wsdisplay.c"): "64f1d2ed2113b6f16c86565dd4780be954dd2a35",
    Path("sys/dev/cons.c"): "f3a2387fbceb9c493517ca69600f669d626750e3",
    Path("sys/dev/wsfb/genfb.c"): "cb9094da52262743df52d20b2bf0b2c320886fa1",
}
CONSINIT = Path("sys/arch/x86/x86/consinit.c")
PATCH = ROOT / "patches/candidates/netbsd11-f20-x86-genfb-early-fallback-20261027.patch"
HEADER = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

struct btinfo_framebuffer { unsigned long physaddr; };
static struct btinfo_framebuffer fb_inst;
static struct btinfo_framebuffer *fbinfo;
static int initted, init_result;
static int early_calls, preattach_wins, fallback_attempts, keyboard_attach;

static int x86_genfb_cnattach(void)
{
    early_calls++;
    return init_result;
}
static void genfb_cnattach(void) { preattach_wins++; }
static void genfb_disable(void) { fallback_attempts++; }

static void test_kernel_early_console(void)
{
"""
FOOTER = r"""
    goto end;
dokbd:
    keyboard_attach++;
end:
    return;
}

int main(void)
{
    int cases=0;
    for (int mapping=0; mapping<3; mapping++) {
        for (int result=-1; result<=1; result++) {
            fb_inst.physaddr = (mapping == 2) ? 0x100000UL : 0;
            fbinfo = (mapping == 0) ? NULL : &fb_inst;
            init_result = result;
            initted = 1;
            early_calls = preattach_wins = fallback_attempts = keyboard_attach = 0;
            test_kernel_early_console();
            const int have_fb = mapping == 2;
            const int deferred = have_fb && result == -1;
            const int success = have_fb && result == 1;
            assert(early_calls == have_fb);
            assert(initted == (deferred ? 0 : 1));
            assert(preattach_wins == success);
            assert(fallback_attempts == (!deferred && !success));
            assert(keyboard_attach == success);
            cases++;
        }
    }
    assert(cases==9);
    puts("F20_ACTUAL_PATCHED_CONSINIT_9_CASES_PASS");
    return 0;
}
"""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def oid(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def segment(s: str, anchor: str, after: str) -> str:
    start = s.index(anchor)
    end = s.index(after, start)
    return s[start:end]


def check_source_flow(src: dict[Path, str]) -> None:
    genfb_mach = src[Path("sys/arch/x86/x86/genfb_machdep.c")]
    early = segment(genfb_mach, "x86_genfb_cnattach(void)", "\n#else",)
    require("if (ncalls < 3)\n\t\treturn -1;" in early,
            "early firmware preattach deferral disappeared")
    require("if (!x86_genfb_init())\n\t\treturn 0;" in early,
            "original framebuffer map failure result changed")
    require("wsdisplay_preattach(" in early and "return 1;" in early,
            "real preattach success return changed")

    ws = src[Path("sys/dev/wscons/wsdisplay.c")]
    require(".cn_dev = NODEV" in ws, "initial wsdisplay console is no longer NODEV")
    pre = segment(ws, "wsdisplay_preattach(", "\nvoid\nwsdisplay_predetach(")
    require("cn_tab = &wsdisplay_cons;" in pre and
            "wsdisplay_console_initted = 1;" in pre,
            "early console state changed")
    attach = segment(ws, "wsdisplay_emul_attach(", "\n/* Print function")
    require("cn_tab->cn_dev = makedev(" in attach,
            "native wsdisplay late console number assignment changed")

    drm = src[Path("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c")]
    match = segment(drm, "i915drmkms_match(device_t parent, cfdata_t match, void *aux)\n{",
                    "\nstatic void\ni915drmkms_attach(")
    require("return 6;" in match, "i915 priority no longer six")
    require("config_mountroot(self, &i915drmkms_attach_real);" in drm,
            "i915 probe no longer deferred")
    real = segment(drm, "i915drmkms_attach_real(device_t self)\n{",
                   "\nstatic int\ni915drmkms_detach(")
    require(real.index("error = -i915_driver_probe(") <
            real.index("if (error) {") <
            real.index("while (!SIMPLEQ_EMPTY(&sc->sc_tasks))"),
            "probe-error early return no longer before framebuffer task drain")
    require('aprint_error_dev(self, "unable to register drm: %d\\n", error);\n\t\treturn;' in real,
            "failed i915 probe no longer early-exits")
    require("sc->sc_task_thread = curlwp;" in real,
            "original deferred-task lifetime contract has changed")

    gpci = src[Path("sys/dev/pci/genfb_pci.c")]
    find_match = segment(gpci, "pci_genfb_match(device_t parent, cfdata_t match, void *aux)\n{",
                         "\nstatic void\npci_genfb_attach(")
    require("matchlvl = 5;" in find_match and
            "if (genfb_is_console())" in find_match,
            "genfb PCI console priority no longer five")
    require("if (!genfb_is_enabled())\n\t\treturn 0;" in find_match,
            "genfb disable semantics changed")
    core = src[Path("sys/dev/cons.c")]
    require('panic("cnopen: no console device");' in core and
            "if (cndev == NODEV)" in core,
            "NetBSD console panic condition disappeared")
    gen = src[Path("sys/dev/wsfb/genfb.c")]
    require("genfb_cnattach_called = 1;" in gen,
            "firmware genfb console selection changed")
    print("F20_UEFI_PREATEACH_PRIORITY_6_GT_5_EARLY_PROBE_BYPASSES_F19_SOURCE_PROVEN")


def get_actual_branch(s: str) -> str:
    # Do not rewrite this segment: it is spliced into a host harness verbatim.
    start = s.index("\t\tif (fbinfo && fbinfo->physaddr > 0) {")
    end = s.index("\t\tgenfb_disable();", start)
    return s[start:end] + "\t\tgenfb_disable();\n"


def compile_run(code: str, wd: Path, name: str, cc: str, std: str) -> int:
    path = wd / (name + ".c")
    executable = wd / (name + ".out")
    path.write_text(code)
    cp = subprocess.run([cc, "-std=" + std, "-Wall", "-Wextra", "-Werror",
                         "-fsanitize=undefined", "-fno-sanitize-recover=all",
                         str(path), "-o", str(executable)],
                        capture_output=True, text=True)
    require(cp.returncode == 0, f"{name} compile: {cp.stderr}")
    run = subprocess.run([str(executable)], capture_output=True, text=True)
    return run.returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--netbsd-tree", type=Path)
    mode.add_argument("--verified-blob-dir", type=Path)
    args = ap.parse_args()
    src_root = (args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree:
        head = subprocess.check_output(
            ["git", "-C", str(src_root), "rev-parse", "HEAD"], text=True).strip()
        require(head == NETBSD, "wrong frozen NetBSD revision")
    original = {}
    for path, sha in FILES.items():
        data = (src_root / path).read_bytes()
        require(oid(data) == sha, f"NetBSD pinned source drift in {path}")
        original[path] = data.decode()
    check_source_flow(original)

    with tempfile.TemporaryDirectory(prefix="f20-gop-fallback-") as temp:
        wd = Path(temp)
        orig_c = original[CONSINIT]
        target = wd / CONSINIT
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(orig_c)
        stats = subprocess.check_output(["git", "apply", "--numstat", str(PATCH)],
                                        text=True).splitlines()
        require(len(stats) == 1 and stats[0].split("\t")[-1] == str(CONSINIT),
                "F20 patch altered unexpected files")
        for flag in ("--check", ""):
            cmd = ["git", "-C", str(wd), "apply", "--whitespace=error"]
            if flag:
                cmd.append(flag)
            cmd.append(str(PATCH))
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        patched = target.read_text()
        before = get_actual_branch(orig_c)
        after = get_actual_branch(patched)
        require(patched.replace(after, before, 1) == orig_c,
                "F20 unexpectedly edits code outside early firmware branch")
        require("if (fb_result == -1)" in after and
                "if (fb_result > 0)" in after,
                "F20 must preserve defer and confirm success explicitly")
        require(after.index("if (fb_result > 0)") <
                after.index("genfb_cnattach();"),
                "F20 must not report failed framebuffer map as success")
        require(after.index("genfb_disable();") >
                after.index("if (fb_result > 0)"),
                "failed firmware framebuffer must reach VGA fallback")

        for cc in ("gcc", "clang"):
            for std in ("gnu99", "gnu11"):
                run = compile_run(HEADER + after + FOOTER, wd,
                                  f"F20_{cc}_{std}", cc, std)
                require(run == 0, f"F20 exact patched C failed {cc}/{std}")
                print("F20_EXACT_GOP_BRANCH_9_CASES_PASS", cc, std)

        # Verify the OLD source is really defective: it accepts return 0
        # as success; our positive harness must reject its behavior.
        old_rc = compile_run(HEADER + before + FOOTER, wd,
                             "F20_old_bug", "gcc", "gnu11")
        require(old_rc != 0, "pinned broken original unexpectedly accepted zero")
        print("F20_ORIGINAL_GOP_RETURN_ZERO_DEFECT_REPRODUCED")

        # Mutation: positive return check turned into broad non-deferred check.
        modified = after.replace("if (fb_result > 0)", "if (fb_result >= 0)")
        require(modified != after, "positive guard not found")
        mutant_rc = compile_run(HEADER + modified + FOOTER, wd,
                                "F20_mutant", "clang", "gnu11")
        require(mutant_rc != 0, "negative mutation wrongly accepts failed GOP map")
        print("F20_BROKEN_POSITIVE_GUARD_MUTANT_REJECTED")

    print("F20_PINNED_GIT_APPLY_36_GCC_CLANG_UBSAN_CASES_TWO_MUTANTS_PASS")
    print("F20_NOT_NATIVE_NETBSD_KERNEL_BUILD_OR_HP_BOOT")


if __name__ == "__main__":
    main()
