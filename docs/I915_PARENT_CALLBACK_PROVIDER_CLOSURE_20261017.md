# Intel i915 parent callback providers — full pinned source inventory

Source-only checkpoint, 2026-10-17. **Not a functional NetBSD kernel.**

The fixed Linux reference `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`
defines `include/drm/intel/display_parent_interface.h` with SHA-256
`bf203599dde029eca7dade66c70ea3f00754e49da00f47a8d7b05c0bffee8cbe`.
The original MIT Intel header is *read* from the frozen reference but
not copied to this repo. This avoids treating the previously denied
header publishing operation as authorization for a different path.

Run the source-only tool on Legion against its existing frozen 323-C-file
reference stage, passing `--linux-i915`, `--filelist`, `--interface`
and `--output` to `tools/audit_i915_parent_provider_closure.py`.
Run `tests/test_i915_parent_provider_closure.py` with the first three
matching args. Both refuse incomplete or changed source evidence.

PRE: Linux driver `i915_driver.c` assigns 16 interface structs using
`&provider` and four generic function callbacks **without** `&`.
The first audit falsely rejected them, and a previous regex omitted
`pc8` because a callback field includes a digit. The corrected audit
parses all 20 designated assignments and 323 active units.

POST: All 16 provider symbol definitions found in active C:
BO `i915_bo.c`, DPT `i915_dpt.c`, DSB `i915_dsb_buffer.c`,
FB pin `i915_fb_pin.c`, frontbuffer `gem/i915_gem_object_frontbuffer.c`,
HDCP `i915_hdcp_gsc.c`, initial plane `i915_initial_plane.c`,
IRQ `i915_irq.c`, overlay `i915_overlay.c`,
panic `gem/i915_gem_panic.c`, PC8 `i915_display_pc8.c`,
Pcode `intel_pcode.c`, RPM `intel_runtime_pm.c`,
RPS `gt/intel_rps.c`, stolen `gem/i915_gem_stolen.c`,
VLV/CHV IOSF `vlv_iosf_sb.c`.

Across the 16 interfaces, 95 direct struct function members are declared,
94 initialized by the Linux provider structs. The unbound
`fb_pin.reuse_vma` has an explicit NULL guard in
`display/intel_parent.c`. The `(*tiling)` callback argument to
`panic.setup` is not a distinct struct member. The four
VLV/CHV IOSF `get/put/read/write` methods are each initialized.

The tool also verifies Linux probe-order source anchors:
PCI enable, parent assignment, early probe, GT, MMIO, hardware,
display-without-IRQ, IRQ, display-without-GEM, GEM, full display,
registration. Four mutation regressions PASS by rejecting intentionally
removed IOSF write, provider pointer, IRQ install and parent assignment.

**Scope limit:** Regex source declaration/ownership only; macro and Kconfig
preprocessing, provider implementation correctness, ABI signatures,
actual NetBSD callbacks, synchronized IOSF MMIO, GEM/TTM/UVM resources,
unwind lifetime, native kernel link and blackscreen G01–G09 tracing remain
unproven. All HP builds/installs/boots remain prohibited pending
validated authorization, console and rollback. No additional-cost CI.
