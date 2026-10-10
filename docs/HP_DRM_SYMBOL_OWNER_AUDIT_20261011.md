# HP native DRM/KMS source-owner closure diagnostic — 2026-10-11

STATE: **PARTIAL / MODERN DRM-KMS NOT FUNCTIONAL**. Actual execution on `hp-tpnw121.fritz.box` under NetBSD 11.0, unprivileged user. This does not supersede the full i915 Cherryview/Braswell (8086:22b1) source reference, acceptance contract, or F77 safe recovery kernel.

## Actual verified native symbol-owner audit

The current published tool `tools/audit_hp_native_drm_symbol_owners.py` ran on HP after a clean fast-forward of the i915 project checkout to `df32f33914140e88742e1f6bc6d2edea3a804983`. Input: the preexisting **three-object** ELF `/home/andreas/projects/driver-port-20261010/i915-native-drm-20261010/modern_drm_three.o` compiled from the modern NetBSD file/task adapter. Pinned source: Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`, NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

Output on HP: `/home/andreas/projects/driver-port-20261010/i915-drm-owners-20261011/status.json`, `SOURCE_OWNER_CANDIDATE_AUDIT_COMPLETE`.

- **121 unique unresolved symbols** in the limited three-object DRM relocatable link, **not** the final 323-unit selected-kernel link.
- **25 symbols** found as definitions in existing HP NetBSD native ELF objects (notably `cv_*`, `linux_kthread_*`, `linux_wait_*`, `linux_tasklets_*`, `sleepq_fatal_pending`). These are already legitimate native object providers but need selection/ABI integration.
- **47 symbols** have text-matched C definition candidates in the staged NetBSD DRM subtree. Candidates need compilation/ownership checks and may be conditionally excluded; a lexical hit is not a linked definition.
- **74 symbols** lack an obvious definition *within scanned DRM-only C source*. This class includes normal NetBSD kernel facilities (e.g., `copyout`, `kmem_alloc`, `fd_allocfile`, `cdevsw_lookup_major`), **not** necessarily 74 missing ported providers.
- Concrete reviewed mappings: `drm_minor_acquire` -> `dist/drm/drm_drv.c`; `drm_guarantee_initialized` -> `drm/drm_module.c`; `drm_ioctl` -> `dist/drm/drm_ioctl.c` and legacy `drm/drm_stub.c` (requires mutually exclusive owner/ABI review); `linux_pid_system_init` -> `linux/linux_pid.c`; `linux_file_native_view` -> `linux/linux_file.c`. No compiled providers were proven for these five at this stage.

## Distinct older i915 F84 diagnostic kernel

The HP i915 experiment is a *different* source/kernel lineage from the modern DRM 323-unit work. At 2026-10-11 01:13 CEST the F84 kernel artifact `/usr/obj/sys/arch/amd64/compile/RTWN8723BE-F84-I915-ASYNC-PARITY/netbsd` was identified as a static NetBSD 11 amd64 executable, `NetBSD 11.0 (RTWN8723BE-F84-I915-ASYNC-PARITY) #0: Sun Oct 11 01:07:15 CEST 2026`. SHA-256 `5762792d2dc686dd5dae96f8bc547306887013d680791485ce2adf022281ec56`. The earlier F84 `make` PID was gone when checked; the original process exit code was not retained. Kernel image link identity is verified; **no boot, i915 attach, eDP/HDMI KMS, backlight, 3D, PM or stability success was observed**.

F83 was previously booted once and black-screened despite lit backlight; source analysis identified an i915 fbdev/VGA handoff timing divergence, but this is **not a proven unique cause**. F84's NetBSD `intel_fbdev_initial_config_async` uses i915 taskqueue handling while frozen `linux/async.h:async_synchronize_cookie` is a no-op; error/unregister task lifetime needs source-backed verification before any new boot. F77 is still running and has not been replaced.

## Next mandatory implementation/validation

1. Bind every DRM native symbol group to an actual NetBSD C/kernel provider, fixing ABI ownership conflicts such as `drm_ioctl`, with compile/link evidence and no placeholder/stub pretending semantic parity.
2. Extend selected *complete* modern DRM/TTM/folio/GEM/UVM/Linux task/IRQ/VM and **323 i915-unit** configuration to a successful HP native-kernel link and validate all function-level lifecycle semantics; the existing three-object partial link does not close this graph.
3. Implement robust NetBSD fbdev task completion/cancel semantics and phase-labelled persistent graphics handoff diagnostics; isolate F83's black-screen phase. Do not install/boot F84 merely because it linked; maintain F77 rollback.
4. Only after source/build/recovery gates and an explicitly controlled candidate boot, verify physical 8086:22b1 modeset, panel, brightness, eDP/HDMI, GEM/GTT/IRQ, suspend/resume and recovery.

No modifications to NetBSD live kernel, production graphics driver, boot menu, or display were made by the audit.
