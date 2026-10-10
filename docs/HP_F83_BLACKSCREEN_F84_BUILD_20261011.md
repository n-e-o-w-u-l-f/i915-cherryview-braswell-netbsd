# HP F83 black-display outcome and active F84 build observation — 2026-10-11

Status: DIAGNOSTIC / NOT KMS-VERIFIED. Read-only inspection through the HP NetBSD 11 Remote Desktop Commander device on 2026-10-11 (Europe/Berlin). The source of the prior F83 boot observation is the local owner report `/home/andreas/rtwn-i915-f83-20261010/F77-I915-RTL8723BE-PARITY-AUDIT-20261011.md`; that boot was not repeated during this inspection.

## Verified runtime vs reported historical candidate

- **Live runtime:** NetBSD 11.0 `RTWN8723BE-F77-LINUX-EFUSE-MAP`, HP 17-x037ng / Intel Cherryview/Braswell 8086:22b1; safe F77 is booted. No reboot, kernel replacement, display-driver activation or network reset was performed in this audit.
- **F83 outcome, as reported in the same machine's latest owner audit:** F83 did boot once. After green boot text the built-in panel became black while its backlight stayed on. Desktop agent and syslog did not return, and no preserved i915 trace was found in `/var/log/messages`. This is a failed **physical graphics handoff**, not a functioning KMS driver.
- F83 configuration removed the PCI genfb binding only for that candidate and selected i915drmkms at PCI dev 2/function 0 with intelfb. Its earlier successful dependency build and kernel link prove neither VGA/EFI console handoff nor eDP link training or userspace graphics.
- Linux v5.6-rc3 lineage is present in the HP import; current pinned Linux comparison is `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`. The local source analysis finds the CHV DPIO pre-PLL sequence and Port-C eDP discovery broadly aligned with v5.6. **Unresolved OS-order difference:** Linux disables legacy VGA early and initializes fbdev asynchronously, whereas this NetBSD tree defers probe to mountroot and drains intelfb tasks synchronously in attach.
- **Concurrent actual build:** at 00:45 CEST a root-owned `/usr/bin/make -j4 dependall` (PID 17878) was active, invoked via owner-initiated localhost SSH (PID 17886), in `/usr/obj/sys/arch/amd64/compile/RTWN8723BE-F84-I915-ASYNC-PARITY`. Object files were actively appearing. The inspected F84 configuration inherits the F77 baseline and enables i915drmkms/intelfb; it must be called a *diagnostic candidate*, not a completed port. **No successful F84 link, installation or boot was observed**, and no second build was launched.

## Avoid conflating two code lines

- This repository's modern DRM file-ops bridge `compat/native-drm/drm_cdevsw.c` has three native HP objects and a relocatable partial link, but its remaining 121 partial external imports / complete DRM/TTM/i915 closure are **not** solved by F83's successful link.
- A kernel carrying older NetBSD i915 code with selected Cherryview changes and a partial modern-DRM adapter are distinct implementation/build lineages. Keep their artifact and source identifiers separate; never label either FULL/PARITY from a partial link or black-screen runtime.

## Next gated steps

1. Obtain the *actual exit status* and final object/kernel identity for the in-progress F84 job; inspect failure logs and diff against F77/F83 without restarting the job.
2. Ensure bounded, persistent, phase-labelled diagnostics of early graphics detection, VGA/EFI takeover, i915 PCI attach, GEM/GTT, eDP PPS/AUX, backlight, intelfb task scheduling and fbdev ownership **before** another controlled boot. A backlit black panel alone does not uniquely localize the fault.
3. Compare source-level init ordering with the frozen Linux/NetBSD references, implement one evidence-backed NetBSD adapter correction at a time and perform kernel compilation/installation only on HP after the complete relevant gates.
4. Preserve `/netbsd`, F77 as safe boot default, and pre-existing recovery entries. F16.0 remains excluded. No candidate boot without explicit approval and verified rollback.

The active process is a directly observed independent host job, not a claim that this chat keeps working after termination.
