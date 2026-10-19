# CHV/VLV IOSF PUNIT exclusion and CPU QoS: real NetBSD ABI blockers

**19 October 2026 — pinned reference-source finding; not compiled or hardware verified.**

## Frozen code and confirmed behavior

The Linux `torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab` backend `drivers/gpu/drm/i915/vlv_iosf_sb.c` (Git blob `1f0332b4ad0df58af3b1bd0de7a9290dfa7cf758`) calls `iosf_mbi_punit_acquire` before PUNIT access and `iosf_mbi_punit_release` afterward; for **Valleyview only** it raises and restores a CPU latency QoS request and pings CPUs.

NetBSD's exact frozen `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6` implements the same *source call sequence* in `intel_sideband.c` (Git blob `1cc6a956b90cc44a85fa153ea1aa9ba58a605eed`). However, its compatibility ABI has no corresponding effect:

| Native NetBSD file (pinned Git blob) | Actual implementation | Impact |
| --- | --- | --- |
| `sys/external/bsd/drm2/include/asm/iosf_mbi.h` — `b72c89aed5d1e0ad258c0dd8a6561eafe6398089` | `iosf_mbi_punit_acquire()`, `iosf_mbi_punit_release()`, `iosf_mbi_assert_punit_acquired()` all have empty function bodies | **Does not provide kernel-global PUNIT serialization** |
| `sys/external/bsd/drm2/include/linux/pm_qos.h` — `52d2df0db516eb5473d53a0b8c98ab7fb8d62690` | `struct pm_qos_request { char dummy; }`; `pm_qos_add_request()`, `pm_qos_update_request()`, `pm_qos_remove_request()` all have empty function bodies | **Does not enforce CPU latency or own a live QoS request** |
| `sys/external/bsd/drm2/dist/drm/i915/intel_sideband.c` — `1cc6a956b90cc44a85fa153ea1aa9ba58a605eed` | Has a real per-i915 `sb_lock` mutex, and PUNIT/QoS calls, but the two APIs above are no-ops | `sb_lock` serializes this driver; it is **not evidence for global, cross-driver MBI arbitration** |

The prior three-body normalized-token IOSF parity applies to *control-flow/call sequence only*. OS ABI effects differ. This is an unresolved, **source-confirmed semantic port blocker**. It must not be marked complete in the 300-file i915 matrix.

**Applicability:** Cherryview uses the PUNIT acquire/release wrappers, so their missing global semantics need an explicit callsite/concurrency assessment. The CPU sleep/latency workaround in the frozen Linux source is specifically Valleyview/Bay Trail gated; do **not** assert that its absent latency enforcement caused a Cherryview HP hang. The evidence also does not establish that competing non-i915 MBI consumers exist in this NetBSD kernel: enumerate consumers before selecting the proper lock.

## Corrected interpretation of candidate 0042

`candidates/0042-netbsd11-i915-iosf-qos-failed-probe-unwind.patch` correctly improves the *syntactic* early-error unwind, avoids double-destroying workqueues already cleaned inside the allocation helper, and matches upstream's Valleyview-only QoS condition. Nevertheless, the earlier description of a genuine NetBSD **QoS resource leak** overstates what the pinned `pm_qos.h` supports: `pm_qos_add_request` allocates **nothing** in the current stub, so omitting its `remove` does **not** leak a live QoS resource. Other initialized mutex/uncore objects can remain uncleaned on the direct-return error edge and still justify the source control-flow repair. **The 0042 C/patch regression remains not run** because the prior execution attempt was blocked; do not advance its acceptance state.

## Reproducible source guard

`tests/test_chv_iosf_netbsd_compat_shim_contract.py` pins all four source identities, confirms that the three PUNIT functions and three QoS functions really have empty bodies, checks actual i915/Valleyview callsites and requires a deliberate **new review** if any one of those six functions changes. Its six mutation cases are *defined* but **have not been executed in this step**. A successful source guard would **not** constitute runtime parity; it explicitly emits `STATUS: BLOCKED_RUNTIME_PARITY`.

## Engineering obligations before whole-unit semantic closure

1. Map every NetBSD consumer of PUNIT/MBI access and prove whether the existing per-device `sb_lock` is sufficient. If cross-driver protection is needed, implement a real globally shared NetBSD MBI arbitration primitive with correct initialization, ownership, lock hierarchy, teardown and error behavior; a static header-local mutex is **not** globally shared and is not an acceptable shortcut.
2. Verify the target-specific CPU PM/idle API and required Valleyview-only CPU package latency guarantee. Do not blindly replace the no-op QoS functions with a platform-wide idle-disabling hack, and do not extend the Bay Trail workaround to CHV without evidence.
3. Verify all conditional `get/put` exit paths in the real IOSF/DRM call graph, including the separate Linux `locked_unit_mask` safety checks, native preemption boundaries and failure releases. Test under native concurrency and fault injection when authorized.
4. Verify the `0042` candidate's native NetBSD compile/link and actual post-failure cleanup before production integration. Record independent recovery and user's kernel test before physical KMS per existing governance.

**Release gate:** 300/300 open semantic i915 source rows and all full-kernel/HP physical gates remain unverified. No HP build, installation, boot, global PM change or connector reroute occurred.
