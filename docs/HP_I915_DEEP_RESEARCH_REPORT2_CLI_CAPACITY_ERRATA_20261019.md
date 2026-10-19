# HP-I915 — second Deep Research report: exact CLI, test and handoff corrections

Date: 2026-10-19  
Scope: second user-pasted Deep Research output `Eingefügter Text(2).txt`.  
**Status: source-verified command/acceptance correction only. No kernel/test execution.**  
Previous source branch HEAD: `dd1cf2d6b3856c8987a5cfb5cfc8e3f128bddfd2`.  
Branch: `work/hp-native-drm-stage-replay-20261015`.  
First report correction: [HP_I915_DEEP_RESEARCH_HANDOFF_ERRATA_20261019.md](HP_I915_DEEP_RESEARCH_HANDOFF_ERRATA_20261019.md).

## Directly verified source and governance contracts

The authored [0045 source regression script](../tests/test_chv_edp_short_hpd_0045_source.py), pinned Git blob `b58df313f43998cfed7ea7479fbd01a18429f0e1`, defines `main()` and **five mandatory CLI file arguments**:
`--netbsd-dp`, `--netbsd-pm-shim`, `--netbsd-power`,
`--netbsd-hotplug`, `--patch`. Its `if __name__ == "__main__": main()`
means simply invoking `pytest tests/test_chv_edp_short_hpd_0045_source.py`
does **not** run its regression entrypoint; no `test_*` test functions
are defined in that file. Pytest would not collect sixteen separate cases.
The report's expectation of sixteen printed `FAIL` test outcomes is wrong:
one single CLI source-model regression loops over **16 deliberately dangerous
source-string mutants**, internally rejects them, and prints these three
positive markers on actual full success:
- `CHV_EDP_HPD0045_PINNED_SOURCE_GUARD_PASS`
- `CHV_EDP_HPD0045_SIXTEEN_MUTATIONS_REFUSED`
- `CHV_EDP_HPD0045_BYTE_EXACT_REVERSE_PASS`

The suite uses a scratch temporary directory and `git apply --check`,
`git apply`, `git apply --reverse` against byte-exact pinned NetBSD source,
with scripted text mutation auditing. It does **not** simulate an IRQ,
PPS timing, concurrent electrical HPD, framebuffer flipping or
`drm_connector_put()`. The doubled release mutant is
`intel_display_power_put(dev_priv, domain, wakeref)`, not
`drm_connector_put()`. Hence no HP host, running KMS kernel, root,
`/dev/dri/card0` or framebuffer test harness is prerequisite for the
*source-model* script, although separate **native and physical** release
tests will need real NetBSD setup later.

**Execution status:** AUTHORED **NOT_RUN**; previous provider-denied
equivalent i915 source regression may not be rerouted through another
tool/host without genuine authorization change. This errata contains no
run command requiring execution now.

## Specific incorrect and unsafe report instructions

| Second report claim/instruction | Verified correction |
|---|---|
| `pytest tests/test_chv_edp_short_hpd_0045_source.py` drives 16 tests | The source is a `python3` CLI requiring five paths, not a pytest suite. No execution has occurred. |
| Expected each mutant “FAIL” from pytest and any “PASS” proves failure | Internal mutant rejection yields a **successful outer script**, `0` exit and the three explicit `*_PASS` / `*_REFUSED` markers. |
| One mutant doubly invokes `drm_connector_put()` | Actual C string mutation doubles `intel_display_power_put(dev_priv, domain, wakeref)`. |
| Mutants force concurrent real IRQ/PPS or LVDS hardware events | No concurrency scheduler, real IRQ, HPD injection or LVDS operation appears in the authored source. |
| Routine `git reset --hard origin/main` after `git fetch --all` | **Do not run.** This drops uncommitted local changes and discards the feature-branch state in favor of potentially unrelated `main`. Verify clean worktree and exact branch/ref first; use non-destructive reads. |
| `config HP_I915; buildkernel KERNCONF=HP_I915` | Not the documented NetBSD `build.sh` operation. The NetBSD Guide specifies `./build.sh [options] kernel=<existing-config>`; actual HP config/toolchain/target integration must be verified before use, and physical build/boot release remains blocked. |
| `scripts/check_chat_handoff_capacity.py --used ... --limit ...` | **Unsupported flags**. Actual GitHub script blob `ba92a35f41adbbeb89f0532c45797705ff20826f` offers `--chat-used/--chat-limit`, `--context-used/--context-limit`, `--work-units`, `--heavy-phases`, `--self-test`. A valid observed chat-specific meter differs from a context-only proxy or unknown capacity. |
| Capacity script returns status `1` for handoff | Actual script returns `3` for `HANDOFF`, `2` for invalid inputs, `0` for other actions. A percentage must **never be invented** when no trusted active-chat meter exists. |
| `verify_current_handoff.py` plans chat capacity and yields `CLOSED_SOURCE_NEEDS_HANDOFF` | Actual script blob `93c792a0636a046a721ca3ddb8bcdb73abb87971` is a **read-only HEAD vs owner/current/event validator**; `CLOSED_SOURCE_VERIFIED` means coherent source pointer only. No capacity metering or automatic handoff. |
| PRE and POST sections belong in `HP-I915-CURRENT.md`, logs in `logs/` | Canonical PRE/POST are append-only `Agent-Governance/state/events/*.jsonl`. `state/projects/HP-I915.md` projects state; `handoffs/HP-I915-CURRENT.md` is a single live `PRE_OPEN`/`POST_CLOSED` pointer, **not** a fabricated success template or archival ledger. |
| 90% capacity with 54k/128k models is the known current limit | `CHAT_CAPACITY_HANDOFF.md` explicitly distinguishes context, quotas, output and UI chat lifetime. Without a verified meter, do not assert a percentage or product-specific cap. Use observed work-unit fallback only and preserve durable handoff; no automatic internal token telemetry. |
| Kernel build/install and HP reboot are the immediate next steps | **Blocked** by release/recovery prerequisites: independently verified G01–G09 early console, live standard-kernel rollback and native i915+DRM/TTM+RTL build/integration prerequisites. No active C integration, HP kernel/bootloader change, physical KMS, WPA2 or recovery acceptance is established. |

## Primary NetBSD build documentation (REFERENCE ONLY — not a command authorization)

- [NetBSD Guide §33: Crosscompiling NetBSD with build.sh](https://www.netbsd.org/docs/guide/en/chap-build.html), especially §33.4 `kernel=MYKERNEL`.
- [NetBSD Guide §34: Compiling the kernel](https://www.netbsd.org/docs/guide/en/chap-kernel.html), especially §34.5.
- [NetBSD Guide §35: Updating from sources](https://www.netbsd.org/docs/guide/en/chap-updating.html) emphasizes correct tools/objects and *separate* install steps.
- [NetBSD kernel directory change](https://wiki.netbsd.org/kernel_dir/): version-dependent kernel directory layouts can differ; **do not assume `/netbsd.old` is already a working tested rescue**.

These are documentation/command-shape references, not proof of NetBSD 11
toolchain identity on HP, KERNCONF `HP_I915`, working recovery, bootloader
layout, compiled or running kernel.

## Clean re-entry and next permitted scope

1. Fetch actual i915 branch HEAD and the `HP-I915-CURRENT.md` pointer;
   validate its matching `state/events/` PRE/POST and owner source head.
2. Keep 0045 in `candidates/` and the Python script **NOT_RUN**; continue
   **independent source-only** review of pinned NetBSD/Linux interfaces and
   0013/0014/0043/0044/0045 composition. The 300 remaining semantic rows
   remain OPEN until separately source-adjudicated.
3. If truly independent, newly authorized executable acceptance becomes
   available, run the exact CLI on known pinned frozen sources with explicit
   arg paths and three success markers. Never reroute a prior denied
   equivalent i915 test to another executor.
4. Require native NetBSD linker evidence and separately proven recovery
   before any HP kernel install/boot, then physical eDP/KMS and RTL/WPA2
   acceptance. No destructive Git reset or speculative `pytest`/build commands.

The second Deep Research report and its illustrative PRE/POST template are
**not** authoritative runtime proof. Record this report's errors without
modifying its original uploaded source. Project's authoritative PRE/POST:
`Agent-Governance/state/events/hp-i915-deep-research-cli-handoff-errata-20261019.jsonl`.
