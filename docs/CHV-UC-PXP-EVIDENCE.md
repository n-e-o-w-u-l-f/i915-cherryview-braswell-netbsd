# Cherryview uC / GSC / PXP applicability evidence

Pinned Linux reference: `fd179f8a05be3ccae366b9b96e176b51fbe54aab`
NetBSD baseline: `03d918f6d0e81fa05b8f1160eca0628ad39988a6`

## Linux Cherryview predicates

The pinned Linux `chv_info` is Gen8 and does not set `has_gt_uc` or
`has_pxp`. Its platform engine mask contains RCS0, VCS0, BCS0 and VECS0,
but no GSC0.

`intel_uc_fw_init_early()` only selects GuC/HuC/GSC firmware when
`HAS_GT_UC(i915)` is true. Otherwise firmware state becomes
`INTEL_UC_FIRMWARE_NOT_SUPPORTED`.

`intel_gsc_uc_init_early()` marks GSC firmware unsupported when no GSC
engine is present.

`intel_pxp_init()` calls `find_gt_for_required_protected_content()`, which
returns NULL when `HAS_PXP(i915)` is false. The fallback tee-link path is
for HuC/GSC-backed platforms; Cherryview has neither. Therefore
`intel_pxp_init()` returns `-ENODEV`. `i915_driver.c` explicitly treats
`-ENODEV` as the normal no-PXP result and continues probing.

## NetBSD baseline equivalence

The NetBSD Cherryview `chv_info` likewise does not set `has_gt_uc` and
its engine mask has no GSC0.

The imported NetBSD `intel_guc_fw_init_early()` passes `HAS_GT_UC(i915)`
to `intel_uc_fw_init_early()`. When support is false, no firmware path is
selected and the uC state becomes `INTEL_UC_FIRMWARE_NOT_SUPPORTED`.

For the HP Cherryview target, modern PXP/GSC/GuC/HuC implementation modules
that are only reachable behind these predicates are therefore
REFERENCE_INAPPLICABLE. The generic unsupported/no-op control semantics remain
part of the target port and are not excluded.

## Classified implementation modules

- `gt/intel_gsc.c`
- `gt/uc/intel_gsc_fw.c`
- `gt/uc/intel_gsc_proxy.c`
- `gt/uc/intel_gsc_uc.c`
- `gt/uc/intel_gsc_uc_debugfs.c`
- `gt/uc/intel_gsc_uc_heci_cmd_submit.c`
- `gt/uc/intel_guc_capture.c`
- `gt/uc/intel_guc_debugfs.c`
- `gt/uc/intel_guc_hwconfig.c`
- `gt/uc/intel_guc_log_debugfs.c`
- `gt/uc/intel_guc_rc.c`
- `gt/uc/intel_guc_slpc.c`
- `gt/uc/intel_huc_debugfs.c`
- `gt/uc/intel_uc_debugfs.c`
- all nine `pxp/intel_pxp*.c` active implementation units

This classification is target-specific. It does not assert that those modules
are unimportant for Gen9+/Gen12+ i915 platforms.
