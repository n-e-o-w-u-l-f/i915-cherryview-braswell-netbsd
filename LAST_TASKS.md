# LAST_TASKS

## 2026-09-29 — CHV KMS recovery

- **STATE:** IN_PROGRESS
- **OBJECTIVE:** Make Intel Cherryview `8086:22b1` KMS usable on HP TPN-W121 without risking the proven F77 recovery kernel.
- **CURRENT:** F77 boots through UEFI and intentionally disables `i915drmkms*`; console is `genfb0` 1024x768. NetBSD's CHV PCI mapping matches Linux 5.6. A known Braswell failure path can tear down RPS after `intel_gt_init()` returns `-EIO` while deliberately keeping KMS alive, then crash when fbdev later calls `intel_rps_mark_interactive()`.
- **NEXT:** Add a narrow guard for `intel_gt_has_init_error()` before touching the RPS mutex, add a source-level regression check, then apply/build as a separate diagnostic kernel on the HP. Do not replace `/netbsd` and do not reboot automatically.
- **PLANNED_FILES:** `tests/test-rps-kms-recovery.sh`, `patches/0001-i915-rps-kms-recovery-guard.patch`, `STATUS.md`.
- **BLOCKERS:** Remote security filter currently blocks the SSH write/build path from `spinnennet`; read-only source research and GitHub work continue independently.
- **DO_NOT_REPEAT:** Do not map CHV to BXT or add BXT firmware; do not remove the F77 fallback; do not blindly enable i915 in the default boot entry.
