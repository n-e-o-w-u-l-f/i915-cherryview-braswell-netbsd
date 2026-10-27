# F20 — x86 UEFI GOP framebuffer console failure handling and i915 early failure

Date: 2026-10-27. Evidence class: **pinned source proof + host C execution only**.
The real HP test kernel selected at boot menu option 5 has reported
vpanic, but its exact panic string, non-vpanic frame and kernel image
identity are still unknown. It is not legitimate to label this a fix
of that physical boot failure.

## Unexpected early console vulnerability, pre-dating F19

Exact NetBSD/src Git HEAD:
03d918f6d0e81fa05b8f1160eca0628ad39988a6.

1. x86/x86/consinit.c invokes x86_genfb_cnattach() during "pc"
   console selection if bootinfo provides a physical GOP framebuffer.
2. x86/x86/genfb_machdep.c specifies THREE distinct results from
   x86_genfb_cnattach():
   - -1: wait for UVM; defer initialization;
   - 0: failure (no address, mapping failure, no virtual address);
   - 1: successfully initialized early framebuffer and called
     wsdisplay_preattach().
3. Original consinit.c checks only for -1. For result 0 it STILL
   calls genfb_cnattach() and jumps past all VGA/text fallback logic.
   This advertises a firmware framebuffer console not actually
   initialized by wsdisplay_preattach().
4. Separately, i915drmkms_match returns 6 while pci_genfb_match
   assigns firmware genfb priority at most 5. Once i915 has won
   the PCI device and its deferred mountroot i915_driver_probe()
   fails before draining intelfb tasks, the F19 guard in
   drmfb_attach() is never reached.
5. In a successful early GOP preattach, wsdisplay_cons.cn_dev is
   initially NODEV; wsdisplay_emul_attach later assigns a valid
   device number. NetBSD's cnopen() panics on NODEV unless NULLCONS
   support changes that handling. It is therefore plausible for
   failed i915 attach to leave an unusable console. **This is an
   established source failure route, not proof of the specific
   unobserved HP menu-5 panic cause.**

The early i915 path is more consequential for the HP than F19 alone:
the machine has an EFI GOP recovery route. The physical F77 boot
works, which makes an initial GOP map failure less obviously relevant
to the observed *different* test kernel than later i915 probe failure.

## Actual separate F20 kernel source fix

File: patches/candidates/netbsd11-f20-x86-genfb-early-fallback-20261027.patch

One original NetBSD source file: sys/arch/x86/x86/consinit.c
Git blob: 9ef384c2c07a2202040d0fe672fdfa58a5c07a78.

The change captures the x86_genfb_cnattach return once. -1 still
defers initialization, +1 still calls genfb_cnattach and jumps to
the keyboard attach, but return 0 now falls through genfb_disable
and the existing VGA/text fallback sequence.

The normal successful UEFI/GOP path, deferred UVM initialization,
console selection for serial / non-"pc", and all other source remain
unchanged. The fallback cannot guarantee a usable VGA text mode
on a UEFI-only machine; it only avoids falsely treating a failed
GOP mapping as a successfully preattached wsdisplay console.

F20 does NOT repair an i915_driver_probe failure after the early
GOP preattach. That failure needs a distinct, source-grounded
console lifetime/ownership strategy, not a call to
wsdisplay_predetach() on speculation (which itself can remove
the last available console) and not a generic cnopen panic
suppression.

## Actual executed gates

tests/test_f20_x86_genfb_console_fallback.py --netbsd-tree
<unmodified NetBSD/src pinned Git checkout> (Legion).

- Seven exact native original blobs verified: x86 consinit,
  genfb_machdep, deferred i915 PCI autoconf, genfb PCI match,
  wsdisplay, cons, genfb core.
- Native C match and deferred-probe source order checked; i915
  priority 6 > firmware genfb priority 5; cn_dev starts as NODEV.
- Real git apply --whitespace=error --check and actual git apply
  to original complete x86 consinit.c in a throwaway source directory.
- Verified changes are confined to the exact console attach
  decision block; no code outside it changed.
- The **actual, unmodified patched source block** is compiled with
  GCC+Clang and GNU99+GNU11, -Wall -Wextra -Werror and UBSan,
  each for nine firmware-bootinfo/status combinations:
  **36/36 PASS**.
- The original unfixed source **fails the SAME executable test**
  for result 0; an inverted/broadened return guard mutant
  is also rejected.
- Result:
  F20_PINNED_GIT_APPLY_36_GCC_CLANG_UBSAN_CASES_TWO_MUTANTS_PASS.
- F19 64-case and 256-case exact native function source fixtures
  remain separate and were previously PASS. CI runner is extended
  to invoke F20 with its original source requirements.

### NOT_RUN / no physical authorization

Native NetBSD kernel object compile or kernel link, GitHub hosted
workflow (manual-only CI infrastructure quarantine), installation,
HP boot, panic trace/image readback and G01-G09 graphics tests
remain NOT_RUN.

Do not replace F77, edit boot.cfg or boot another test kernel just
because this source fix passes host-side tests.

Sources:
- https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/consinit.c
- https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/arch/x86/x86/genfb_machdep.c
- https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c
- https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/dev/pci/genfb_pci.c
