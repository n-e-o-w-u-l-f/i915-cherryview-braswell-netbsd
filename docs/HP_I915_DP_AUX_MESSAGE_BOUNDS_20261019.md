# NetBSD i915 Cherryview DP-AUX: bounded transfer buffer and non-null payload

**Date:** 2026-10-19. **Scope:** frozen-source guard and separate candidate; **NOT** full-source-unit acceptance, native build or HP hardware verification.

## Frozen evidence

- NetBSD `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`, `sys/external/bsd/drm2/dist/drm/i915/display/intel_dp.c` Git blob `1dd8858b2d331906190258c8602af55966ff986c`. The existing `intel_dp_aux_transfer()` uses `u8 txbuf[20], rxbuf[20]` and `size_t txsize, rxsize`.
- Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab`, `drivers/gpu/drm/i915/display/intel_dp_aux.c` Git blob `3cb07b0a901cff7291eca9479f24128989d6c0e7`. The frozen upstream implementation also computes `HEADER_SIZE + msg->size` and `msg->size + 1` before testing the result against 20. Thus this candidate is an **additional NetBSD defensive boundary**, **not** a claim of token-level upstream parity.
- `HEADER_SIZE` is `BARE_ADDRESS_SIZE + 1`, with `BARE_ADDRESS_SIZE=3`. A nonempty AUX write contains 4 header bytes and at most 16 payload bytes in the 20-byte TX array. A read response reserves 1 byte for the reply and at most 19 payload bytes in the 20-byte RX array.
- Existing NetBSD `WARN_ON(txsize > 20)` and `WARN_ON(rxsize > 20)` occur **after** their respective unsigned additions. For extremely large values such as `SIZE_MAX`, size_t arithmetic may wrap to a small value and evade these checks; then a write may copy an unbounded `msg->size` into `txbuf`, and a malformed read can reach an invalid/null destination. These are demonstrated **source-level integer/pointer safety issues**, not established real HP fault causes.

## Actual code change

The standalone [candidate 0043](../candidates/0043-netbsd11-i915-dp-aux-size-overflow-guard.patch) changes *only* `intel_dp_aux_transfer()`:

1. Reject nonzero `msg->size` with NULL `msg->buffer` **before** preparing the AUX header: `-EINVAL`.
2. In the write cases, reject `msg->size > sizeof(txbuf) - HEADER_SIZE` **before** the addition: `-E2BIG`. Exactly 16 bytes remain allowed.
3. In read cases, reject `msg->size >= sizeof(rxbuf)` **before** adding the reply byte: `-E2BIG`. Exactly 19 bytes remain allowed.
4. Only call `memcpy()` for a positive received payload length. A zero-length reply does not pass a potentially NULL destination to `memcpy`.

The established `WARN_ON` checks remain as defense-in-depth; valid transfer operations and existing AUX power/lock/VDD lifecycles are unchanged. This is unrelated to candidate 0013 (IRQ/cold polling) or 0014 (precharge).

## Evidence/limits

- **READBACK PASS:** Candidate source `ad495900e2c41ef0fc3469114fb34d02395b8e62`, regression-test authoring `7258b2fe4f7e5b9d3a14a9141ab91f24e1850978` and count correction `07173246cc48c2bb415d3d5a87ee3d84d2bd5876`, verified by fetching committed contents.
- **SOURCE REPLAY PASS (not `git apply`):** a pure, isolated text-hunk verifier reconstructed all four patches against the pinned original C source using exact original-context comparisons; four hunk counts and new-line locations verified; reverse reconstruction was byte-for-byte identical to the frozen original source. Six static source conditions and **38** JavaScript boundary-model checks passed (0, 1, 15, 16, 17, 19, 20 and 64-bit `SIZE_MAX`, plus null and invalid request cases).
- **NOT RUN:** `tests/test_i915_dp_aux_message_bounds_pinned.py` is authored; its actual scratch `git apply`, five C-source mutation refusals and source-test Python execution have **not** been run. The attempted raw-source download for this separate test was unavailable, and it was not replaced with a target-host attempt.
- **NOT RUN:** native NetBSD compile/link/DRM/KMS, real AUX/eDP/display probing, suspend/resume, HP kernel install/boot, and RTL8723BE integrated kernel verification. No test instrumentation was installed on the HP.
- **UNRESOLVED:** Real NetBSD callsite proof for all `drm_dp_aux_msg` producers, ABI/lock/runtime dependency checks, interaction with already staged DP/AUX WIP, and all remaining 300 full Linux i915 source-unit semantic reviews.

## Release gate

Keep 0043 **candidate-only** until complete, authorized source-unit review, isolated native NetBSD compilation and regression, integration with already modified `display/intel_dp.c`, and user-installed independent-recovery HP kernel testing under existing governance. Neither patch publication nor source-text replay justifies accepting any of the 300 outstanding whole units.
