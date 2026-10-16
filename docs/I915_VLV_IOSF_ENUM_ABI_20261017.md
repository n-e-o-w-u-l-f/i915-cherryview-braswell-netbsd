# Cherryview IOSF old-to-new unit/lock-mask ABI translation

SOURCE-ONLY isolation candidate (2026-10-17); not integrated in the HP
kernel; NOT a working native i915 driver.

Pinned Linux `include/drm/intel/vlv_iosf_sb_regs.h` at
torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab
defines **nine** `VLV_IOSF_SB_*` indices including inserted
`VLV_IOSF_SB_DPIO_2=4`. Its SHA-256 in the frozen Linux stage:
`e4198672b507cff85df32084643c731d29f32efa67c820a4bea91aaeee3804df`.

Frozen NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6
`sys/external/bsd/drm2/dist/drm/i915/intel_sideband.h` has only
eight indices, missing DPIO_2. SHA-256:
`498168f1ac94396e5e25aabd8f10e39e64f513f19e378d24b4f2b7b64110d612`.
NetBSD legacy `intel_sideband.c` is active in
`i915drm/files.i915drmkms` and contains functional predecessors:
`vlv_iosf_sb_get/put`, `vlv_sideband_rw`, PUNIT, BUNIT, CCK,
CCU, FLISDSI and DPIO helpers. Its SHA:
`ae1aefbd0683cb031a0bc9b20a9c16c1438d391f51b4158fddfc0e1555a05807`.

## Actual ABI hazard

A modern Linux `BIT(VLV_IOSF_SB_PUNIT)` is **bit 8** while
NetBSD's older `BIT(VLV_IOSF_SB_PUNIT)` is **bit 7**.
Passing the new mask directly to the old sideband getter would
skip the legacy PUNIT lock/ownership protocol. FLISDSI, GPIO, NC
are also shifted. For Cherryview this can affect CDCLK and power
programming. Linux's sideband module tracks `locked_unit_mask`,
whereas the old NetBSD source uses `sb_lock` without this tracking.
Modern `vlv_iosf_sb_write` returns an int status; the older
`vlv_iosf_sb_write` returns void and drops the internal error.
These differences must be ported before claiming runtime parity.

## Isolated implementation

`compat/native-runtime/vlv-iosf/include/nb_i915_vlv_iosf_unit_bridge.h`
is a BSD-2-Clause new implementation of *unit and lock-mask*
translation. It uses disjoint enum names, preserving all eight
representable units without colliding with the old NetBSD namespace,
and returns `-EOPNOTSUPP` for DPIO_2 instead of silently
routing to the wrong physical IOSF unit. It returns `-EINVAL`
for invalid masks/units; the result argument remains unchanged
on failure. It **does not implement** the read/write devfn/port/opcode
transaction or install callbacks and is not a kernel-API replacement.

Test `tests/test_i915_vlv_iosf_enum_bridge.py` validates hashes and
both frozen enum values, then compiles and executes the adapter in a
host-only C fixture with `-Wall -Wextra -Werror`: each single-bit unit,
PUNIT mask translation, combined mask, all-eight mask, zero mask,
unsupported DPIO_2, invalid bits, null pointers and unknown unit.
No physical MMIO is touched.

## Remaining work

Verify actual NetBSD bus/register mapping, mutex/latency QoS and
atomic preemption discipline, bridge return statuses for every
read/write method, add required CHV DPIO_2 transport, integrate the
parent display interface only after native ABI/provider closure,
then compile/link on HP and collect independent G01-G09 early-console
trace with rollback before any boot attempt.
