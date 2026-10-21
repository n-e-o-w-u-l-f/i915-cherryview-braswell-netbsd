# HP-I915 0069 — QEMU-only real NetBSD 11 kernel probe-error self-test

**Scope:** An independently linked NetBSD11/amd64 diagnostic kernel invokes the **unchanged original** `__i915_inject_probe_error` and `i915_error_injected` after NetBSD `configure()`, using a disposable `drm_i915_private` with the existing `mainbus0` device. The test-only caller is appended to `i915_utils.c` and called from `init_main.c`. The two production source files are **not modified on the Git branch**; this is a test-only patch.

**What this proves:** Real kernel execution of the i915 one-shot probe-error helper: disabled → 0; checkpoint 1 → 0; checkpoint 2 → -EFAULT (-14); later checkpoint → 0; error-injected state true then cleared; original parameter and static counter restored. This is **not** an actual `intel_connector_register` or `drm_connector_register_all` fault, physical Cherryview PCI test, HP KMS, RTL8723BE WPA2 or verified boot fallback.

## Reproduce on Legion

Requires pre-existing verified 0064 source+object tree, NetBSD cross-toolchain and immutable 0066 NetBSD11 guest root. From this directory:

```sh
python3 reproduce_0069.py \
  --baseline-0064 /var/lib/sentinelx/uploads/i915-0064-connector-fault-20261021-a01 \
  --disk /var/lib/sentinelx/uploads/i915-0066-qemu-native-smoke-20261021-a01/netbsd11-root-quiet-ffs2.raw \
  --output /var/lib/sentinelx/uploads/NEW-UNUSED-0069-REPRO
```

The script checks the original 0064 ELF SHA256 `22d0fd9e4c1aa3eac10cd6a4b0c67de6c16820aeba0150e38a8f6bb65195028e` and guest disk SHA256 `1210c3130785f399b4cc17e1cf32f1b3195a167f80fb7d9c39b91fafc495e586`; it refuses existing output directories. It copies source+objects to a new scratch, changes only the copied Makefile source root, applies the patch, compiles modified objects with native `-Werror`, links the full kernel, boots a negative control with the original 0064 kernel, then boots the diagnostic kernel **twice**. QEMU uses TCG, `-nic none`, guest disk `snapshot=on` and ISA debugcon port `0xe9`. Each test run emits one exact line:

```text
HP_I915_0069_KERNEL_PROBE_PASS disabled=0 before=0 hit=-14 after=0 fired=1 cleared=1 restored=1 old_param=0
```

The original kernel control must emit **zero bytes** to debugcon. Source patch is against the 0064 scratch baseline, **not** a deployable production patch. Pinned NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`. Canonical PRE/POST: [HP-I915-0069 governance](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/state/events/hp-i915-0069-qemu-kernel-probe-injection-20261021.jsonl).

**Safety:** Never install or boot this diagnostic kernel on HP, alter `boot.cfg`, disable SSH host-key checks, retry denied 0054 staging or the refused Nouveau shim. Independent physical early-console capture and exercised F77/stock rollback remain mandatory before HP experiments.

**Known boundary:** The first VGA screenshot readback was denied by SentinelX file-read policy. That image was **not** re-read through an alternate file tool; a separately instrumented QEMU virtual ISA debugcon test was compiled, linked and executed instead. Do not count the inaccessible screenshot as inspected evidence.
