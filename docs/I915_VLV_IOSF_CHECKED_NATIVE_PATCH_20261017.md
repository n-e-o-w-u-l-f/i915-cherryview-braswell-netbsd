# Cherryview IOSF: checked NetBSD sideband transport integration candidate

2026-10-17 — **tested source-only native patch**, NOT a compiled/linked HP
kernel, no live GPU register/BIOS/boot changes.

## Verified reference and defect

Pinned Linux i915 `vlv_iosf_sb.c` invokes `vlv_sideband_rw` and
**returns its integer status** through `vlv_iosf_sb_write`. The pinned
NetBSD DRM2 `intel_sideband.c` already implements the same inner
serialized hardware transport `static int vlv_sideband_rw(...)`,
including `-EAGAIN` for idle timeout and `-ETIMEDOUT` for completion
timeout, but its outward `void vlv_iosf_sb_write(...)` discards
the return. The NetBSD sideband transport is selected by the
`i915drm/files.i915drmkms` kernel configuration.

Frozen reference:
- Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`
- NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`
- NetBSD original `intel_sideband.c` SHA-256
  `ae1aefbd0683cb031a0bc9b20a9c16c1438d391f51b4158fddfc0e1555a05807`
- NetBSD original `intel_sideband.h` SHA-256
  `498168f1ac94396e5e25aabd8f10e39e64f513f19e378d24b4f2b7b64110d612`

## Implemented candidates and positive/negative regressions

`compat/native-runtime/vlv-iosf/include/nb_i915_vlv_iosf_transaction.h`
maps 9 Linux unit IDs to the actual IOSF port and read/write opcode,
matching the pinned **Linux and NetBSD** register constants.
It refuses unsynchronized/unknown operations, passes
`-EAGAIN`/`-ETIMEDOUT` unchanged, and does not publish read
data on an error. It requires a truthful, already-held unit lock;
it is **not itself a mutex, bus_space bridge, or runtime lock proof**.
DPIO_2's port `0x1a` exists in both generations' register headers,
but the old NetBSD unit/lock interface cannot represent it. Its
transaction remains fail-closed until genuine lock ownership is ported.

`compat/native-runtime/vlv-iosf/patches/netbsd-intel-sideband-checked-status.patch`
contains a two-file, minimal diff against the pinned native NetBSD
`intel_sideband.c` and `intel_sideband.h`. It exposes
`nb_i915_vlv_iosf_rw_checked(...)`, calls the existing static
`vlv_sideband_rw()`, validates opcode/port/value arguments and
preserves the existing legacy `void vlv_iosf_sb_write()` ABI.

Tests:
- `tests/test_i915_vlv_iosf_transaction.py`: exact Linux/NetBSD
  register-file hashes and port/opcode definitions, host-C mocked
  reads/writes/guards/status failures, `-Wall -Wextra -Werror`.
- `tests/test_i915_netbsd_iosf_status_patch.py`: check frozen native
  C/header hashes, apply published diff on temporary NetBSD copies,
  check entry/legacy ABI, compile host-C extracted added function with
  `-Wall -Wextra -Werror`, and cover positive, EAGAIN, ETIMEDOUT,
  invalid port/opcode and null argument cases.

Both published tests were fetched from GitHub and executed PASS on
the existing local Legion source staging. No paid runner invoked.

## Nonnegotiable remaining prerequisites

1. **Native integration:** on HP only, after adequate access,
   source/ABI/audit gate and under established recovery; actually
   apply the patch in the target native kernel tree and integrate
   the modern parent callback's `struct drm_device*` to
   `struct drm_i915_private*` conversion and verified lock ownership.
2. **Full CHV IOSF state machine:** modern `locked_unit_mask`
   semantics, balanced PUNIT resource acquisition, DPIO_2,
   old PUNIT/CPU power hazards and full error unwind.
3. **323-unit kernel closure:** complete DRM, GEM, TTM, UVM,
   LinuxKPI/NetBSD symbols, DMA, MMIO, IRQ, display and KMS lifecycle;
   source/build selection mismatch has not been closed.
4. **Safe final build and boot:** NetBSD kernel image/link/map on HP
   only; an experimental boot only with independently verified
   G01–G09 early-console tracing, recovery and retained known-good
   kernel. A successful mock or patch does not resolve the
   historical i915 blackscreen.
