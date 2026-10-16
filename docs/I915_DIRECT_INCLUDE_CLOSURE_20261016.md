# 323 i915 units: exact NetBSD direct-include path audit

Date: 2026-10-16. SOURCE-ONLY, not semantic/API/ABI/kernel parity.
Linux pin (declared): fd179f8a05be3ccae366b9b96e176b51fbe54aab.
NetBSD pin (declared): 03d918f6d0e81fa05b8f1160eca0628ad39988a6.

Complete Linux-selected filelist is 323 C translation units. The script tools/audit_i915_direct_include_closure.py
requires the existing docs/I915-STRUCTURAL-COVERAGE.tsv table with the exact
same 323 paths. For each source it inventories direct include paths, SHA256,
structural presence classification, and unmatched NetBSD DRM header paths.
It saves a full, reproducible per-unit JSON matrix in the chosen output path.

Read-only Legion reference-stage run: 323/323 Linux C files present;
136 EXACT_ACTIVE_DIST, 13 ACTIVE_OVERRIDE_OR_MOVED, 7 PRESENT_NOT_BUILT,
167 UNRESOLVED_NO_BASENAME. Found 215 distinct direct shared Linux/DRM/UAPI
header paths: 150 exact header path matches at the selected NetBSD DRM
and shared common LinuxKPI roots, 65 without exact paths; 140 Linux C
files use at least one unmatched path.
553 distinct quote-style local include names were also captured.

Top direct header path gaps by user count: linux/string_helpers.h (37),
drm/intel/display_parent_interface.h (24), linux/iopoll.h (19),
drm/intel/intel_pcode_regs.h (16), drm/intel/step.h (15).
The earlier 137/78/175 result is superseded: shared NetBSD common/include
provides linux/slab.h, linux/kernel.h and 11 other matching header paths.

Missing SAME-PATH header does not prove a missing API. Headers may have
NetBSD-specific names or live under roots not scanned. This is a lexical
preprocessor include audit (including inactive #if), not Kconfig evaluation,
transitive dependency resolution, symbol ownership or kernel compilation.
Materialized reference directory revisions are declared, not independently
verified as immutable git objects by this tool; each C source hash and input
manifest hash are retained in the per-unit report for follow-up verification.

Use Python 3 (source-only, no kernel compiler) with arguments:
  --filelist /opt/ChatGPT/hp-driver-port/i915-reference-stage-20261001/i915-active.filelist
  --linux-i915 /opt/ChatGPT/hp-driver-port/i915-reference-stage-20261001/drivers/gpu/drm/i915
  --netbsd-drm2 /opt/ChatGPT/hp-driver-port/netbsd-src-03d918f6-full/sys/external/bsd/drm2
  --structural docs/I915-STRUCTURAL-COVERAGE.tsv
  --out /isolated/owner/i915-direct-includes.json

Prioritize real CHV display/eDP/DP-AUX/DPIO and GEM/GT providers, then
the DRM file/task/mmap lifecycle and TTM closure. Do not equate this report
with a linked kernel or fixed F83/F84 blackscreen. HP-only kernel/native
builds and physical early-console/rollback gates are still open.

Corrected model test and full 323-stage audit executed on Legion after
including the official sys/external/bsd/common/include directory;
all source-only tests passed. Latest generated report SHA256:
f4be73008d26e536fe5e63f936ce0893ba00cce24d97aafc11e8e4d9214b5158.
This hash identifies temporary source-only JSON evidence; no NetBSD
C compiler or physical HP hardware was invoked.
