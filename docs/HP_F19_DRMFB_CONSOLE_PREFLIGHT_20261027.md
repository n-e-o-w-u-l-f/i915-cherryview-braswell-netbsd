# F19 — NetBSD DRM framebuffer console preflight

Date: 2026-10-27
State: FUNCTIONAL SOURCE FIX CANDIDATE; not native-compiled, not installed, not booted.
The HP menu-option-5 vpanic is still undiagnosed pending exact panic text,
non-vpanic stack frame and tested kernel-image identity.

## Original NetBSD source proof

Pin: NetBSD/src 03d918f6d0e81fa05b8f1160eca0628ad39988a6.

- sys/external/bsd/drm2/drm/drmfb.c: Git blob
  f71bee4c525b4199dc4e3eb52ad3f321787e5905.
- sys/dev/wscons/wsdisplay.c: Git blob
  64f1d2ed2113b6f16c86565dd4780be954dd2a35.
- sys/external/bsd/drm2/i915drm/files.i915drmkms:
  23d352b64eb1799caf3e9b2770f78795accc8439.
- sys/dev/wsfb/genfb.c: Git blob
  cb9094da52262743df52d20b2bf0b2c320886fa1.

The original intelfb device exposes wsemuldisplaydev, and the native
wsdisplay_emul_match callback inspects only ap->console. A matching
console child can therefore be preflighted before VGA ownership changes.

The original genfb_attach invokes wsdisplay_cnattach and subsequently
config_found(..., .iattr="wsemuldisplaydev"), but discards the returned
device_t and unconditionally returns zero. Until wsdisplay_emul_attach
runs, cn_tab can point to wsdisplay_cons with cn_dev still NODEV.
The original intelfb_attach_task already handles a nonzero drmfb_attach
return by logging an error, skipping sc_attached=true, and balancing
the config_pending counter.

## Implemented functional C patch

patches/candidates/netbsd11-f19-drmfb-wsdisplay-preflight-20261027.patch

Changes exactly one function in one native NetBSD file: drmfb_attach
in sys/external/bsd/drm2/drm/drmfb.c.

1. Calculate VGA console ownership as before, but defer VGA console
   detach and VGA disable until after a child-device preflight.
2. When the DRM device would own the console, run config_search on
   the intelfb device with aa.console=1 and interface wsemuldisplaydev,
   under KERNEL_LOCK / KERNEL_UNLOCK_ONE.
3. No matching child: report a precise error and return ENXIO before
   disconnecting the legacy VGA console.
4. Matching child: retain old VGA detach, disable, console flag,
   property assignment and subsequent genfb attach order.
5. Non-console devices: no additional configuration search.

Scope limitation: a matched child may still fail a later attach.
Already broken preattached consoles, unrelated i915 no-CRTC/AUX failures,
and other vpanic sites are NOT corrected. This does not establish that
the observed HP menu-5 panic is a cnopen failure. Do not patch generic
sys/dev/cons.c to hide cnopen symptoms.

## Actual executed tests

The exact NetBSD Git checkout pin above was used on Legion.

tests/test_f19_drmfb_console_preflight.py:
- Three original Git blobs checked, plus native intelfb interface
  and actual wsdisplay matcher source.
- Real git apply --whitespace=error --check and git apply in a
  disposable full-original source tree.
- Verified exactly one native function modified, no unrelated edits.
- Exact patched native code block extracted and compiled with host GCC
  and Clang; GNU99 and GNU11; NVGA=0 and NVGA=1;
  Wall/Wextra/Werror and UBSan.
- 8 test cases in each of 8 compiler configurations: 64/64 PASS.
- Mutant with inverted child-null check correctly rejected.
- Result:
  F19_PINNED_GIT_APPLY_EXACT_C_BLOCK_64_CASES_GCC_CLANG_UBSAN_PASS

tests/test_f18_f19_console_source_composition.py:
- Four original Git blobs checked; real git apply both F18 -> F19
  and F19 -> F18, byte-identical results, with all diagnostic
  markers and F19 preflight retained. PASS.

The common pinned-source runner now invokes these tests together with
the F18 diagnostics and menu-5 read-only configuration checks.
Manual-only CI sparse checkout covers all four source files plus
the intelfb device configuration. CI itself remains NOT_RUN.

## Unresolved gates

Native NetBSD compiler object drmfb.o and complete i915/RTL kernel
link are NOT_RUN. The existing HP kernel loaded by boot-menu item 5
has not been identified; its panic message and stack trace have
not been captured. There has been NO firmware, kernel image,
boot.cfg, recovery F77 or physical HP system modification.

Do not install or boot this candidate on the evidence above.

NetBSD original console ownership references:
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/drm/drmfb.c
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/wsfb/genfb.c
https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/wscons/wsdisplay.c


## 2026-10-27 full-native-function host regression

A stricter independent test was published and actually executed against
the real pinned NetBSD Git checkout:

tests/test_f19_complete_drmfb_attach_host.py --netbsd-tree <pinned source>

Unlike the earlier F19 precheck-block fixture, it extracts the COMPLETE
unaltered F19-patched native drmfb_attach() function from the entire
original NetBSD drmfb.c after real git apply. Only its external system,
autoconf, DRM, console and property API dependencies are mocked.
All other bytes of drmfb.c must match the original. The function body
itself is not rewritten or emulated.

Eight compiler setups ran (GCC/Clang x GNU99/GNU11 x NVGA=0/1),
all with -Wall -Wextra -Werror and -fsanitize=undefined. In each
build the actual function was executed across 32 console property,
legacy VGA, firmware console and child-availability scenarios.

RESULT: F19_REAL_DRMFB_COMPLETE_FUNCTION_256_HOST_CASES_GCC_CLANG_UBSAN_PASS.

The mock invariants assert no genfb initialization or property install
on the ENXIO rejection path, no removal of an old VGA console on that
path, proper match search, balanced kernel-lock spans, and unchanged
successful attach semantics. The same test is now included in the
project's pinned-source runner.

A separate read of the pinned Linux-imported
drm_fb_helper_single_fb_probe implementation confirms the no-CRTC/
no-sizes path returns -EAGAIN before invoking the framebuffer fb_probe
callback. A second speculative dimension guard was therefore not
added to F19.

Limits remain unchanged: the C translation unit was NOT compiled with
real NetBSD kernel headers/ABI; host compilation uses mocks for its
external dependencies, and no HP image was built/installed/booted.
The owner's menu-5 vpanic still lacks an actual cause/stack.
