# Safe i915 source/build hardening — 2026-10-14

State: SOURCE_VALIDATED / NATIVE_NOT_RUN / FULL_PORT_OPEN.

## Reconciled sources and governance

- Canonical public repository: `n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd`,
  active, default `main`, verified at `27fd4d7d483be456158884c08d04446dd5312326`.
  The original local main was clean at `f50fcf4`, eight commits behind. It was
  preserved; this work uses an isolated worktree/branch from remote main.
- Other remote branches: `ci/verify-pinned-i915-edp-rates-20261002` at
  `0aca6be3`, and `work/chv-rps-kms-recovery-20260929` at `a42f0830`.
  Open PR #1 concerns the old hosted-CI branch; it was not merged or run.
  Local `transfer/hp-*` branches retain historical work already represented
  in main. No destructive branch reconciliation occurred.
- Agent-Governance was independently fetched to `ed74b9a`; its original
  local main was 204 commits behind and was preserved. The current HP-I915
  projection distinguishes historical F77 from a later GENERIC-default
  request. LAST_TASKS is a pointer/index, not live HP evidence.
- Previous 2026-10-10 three-object DRM compile and relocatable link were
  successful for their dated source. The 121 imports were a partial-link
  observation. Neither this observation nor the 2026-10-11 lexical owner
  candidates prove full modern DRM/TTM/kernel closure.
- `/mnt/data/i915_cherryview_braswell_netbsd_arbeitsplan_2026-10-14.md` is
  inaccessible on this Windows executor. The referenced conversation yields
  content-reference placeholders; no hidden research text was reconstructed.

## Changes and false-positive prevention

`hp_graph_preflight.py` is the shared read-only native input gate. It validates
exact source membership, not just a count of 323: 323 i915, 66 DRM, eight display
and 13 TTM C units (410 total). It parses the pinned NetBSD config generator's
actual `ALLFILES`, `OBJS`, `OBJS.<attribute>` form and requires correct source
root and source/object ownership. Comments, unselected attributes and old
same-basename overrides cannot establish selection. Source/config/Makefile,
tool and source/generated-header hashes bind the report; they are checked again
after compilation/audit. A preflight pass means input identity only.

`prepare_hp_full_graph.py` requires explicit workspace, Linux, materialized,
NetBSD and existing toolchain paths. It verifies all 1,266 materialized input
hashes against the retained frozen manifest and a clean pinned NetBSD reference,
preserves existing outputs/status and writes a current 410-source ledger.
It is a development stage, not adapter parity or an installable kernel.

`probe_hp_full_graph.py` requires that preflight, refuses old selected `.o`/`.d`
files, runs serial dependency/object probes to avoid shared-generation races,
and retains failed/timeout/unbuilt diagnostics. Successful objects must be
fresh, nonempty amd64 ELF relocatables with unchanged sources. Zero-exit make
against an old up-to-date object cannot establish a new compile pass.

`build_hp_native_drm_adapter.py` retargets the recorded strict native compiler
flags to the explicit fresh tree/object/tools directories. Historical paths
exist only as inputs to this translation, never as active defaults. It compiles
the current canonical C source rather than requiring the obsolete fixed source
hash, records commands/versions/input hashes, refuses root and existing output,
and keeps the three-object scope explicit. It does not install or link a kernel.

`audit_hp_native_drm_symbol_owners.py` now consumes matching successful build
ledgers, checks selected source/object/hash/ELF identity, and produces per-symbol
consumer/provider edges across the selected DRM/TTM/i915 and native kernel
owners. Missing configured objects, unresolved strong imports and conflicting
strong/common providers keep `GRAPH_OPEN` (exit 1). A failed overall probe can
still contribute individually evidenced successful objects. Optional weak
imports are reported separately. Selected lexical C candidates remain only
candidates. `OBJECT_SYMBOL_CLOSURE` (exit 0) is **not** a final kernel-link,
ABI, lifecycle or KMS pass. Architecture/libkern/generated providers outside
the configured source list still require the final native kernel link.

The C adapter now calculates snapshot size after validating iovec count and
keeps whole-event progress suppression at its shared exit. Review confirmed
the existing copy-fault branch already restores the uio and requeues the failed
event after preserving prior whole-event progress. This is defensive hardening,
not a reproduced new runtime defect. Open cleanup retains one release for
each acquired task/minor/fd/file; failed driver open does not acquire release
ownership. Pinned NetBSD `fd_clone` affixes the descriptor and unconditionally
returns EMOVEFD, so no invented clone-failure unwind was added.
Reference: [pinned kern_descrip.c](https://github.com/NetBSD/src/blob/03d918f6d0e81fa05b8f1160eca0628ad39988a6/sys/kern/kern_descrip.c).

## Actual tests and limitations

Executed on local Windows with Python, without a C compiler, make or nm:

```text
python -B tools/run_local_hardening_checks.py --output <new-report.json>
30 preflight/owner controls: PASS
4 native DRM source contracts: PASS
pinned runner scope check: PASS
90 Python files parsed: PASS
git diff --check: PASS
```

[Exact attributable report](evidence/I915_LOCAL_HARDENING_FINAL_20261014.json)
records timestamps, interpreter, base Git HEAD, dirty implementation state,
commands/exits and tested Python/C hashes. Fixtures are synthetic source/nm/ELF
headers, not compiled providers. Native-host admission was tested by invoking
all five actual CLI entrypoints on the foreign executor: refusal occurred before
any output or compiler invocation. Same-count wrong sources, missing TTM,
comment-only selection, stale stage/Makefile/source/object/header identity,
old/modern drm_ioctl owner conflicts and partial-three-vs-323 controls pass.

Recorded hashes identify the tested Windows worktree bytes. Git normalizes
line endings for committed blobs; normalized committed/tested source text was
checked separately. These local hashes are not a native HP stage/ELF identity.

Two new defensive C source guards intentionally failed before their associated
change and then passed; they do not establish a historical runtime failure.
An initial graph test exposed an iterator/len mismatch in the new helper;
normalizing the expected iterable to a set corrected it. The original case
passed on re-run. No build failure was hidden by suppressing a native gate.

The full pinned-tree source suite was not run; reference material found on
Spinnennet is a lead, not verified fresh pinned-checkout integration evidence.
No updated C object or actual current native owner graph has been produced.

## Native reproduction after HP access is restored

First inspect actual HP OS, boot/recovery identity, source stage, owner account,
existing free toolchain, free space and active processes. Preserve old artifacts.
Use a new isolated owner workspace; no production source/boot changes.

```sh
python3 -B tools/prepare_hp_full_graph.py \
  --workspace "$work" --linux-tree "$linux" \
  --materialized-tree "$materialized" --netbsd-tree "$netbsd" \
  --base-tool-dir "$existing_tools"
python3 -B tools/hp_graph_preflight.py \
  --native-tree "$work/netbsd-full-linux" --object-dir "$work/full-linux-obj" \
  --tool-dir "$work/full-linux-tools" --graph-status "$work/full-linux-graph-status.json"
python3 -B tools/probe_hp_full_graph.py --workspace "$work" --output "$work/new-probe" \
  --native-tree "$work/netbsd-full-linux" --object-dir "$work/full-linux-obj" \
  --tool-dir "$work/full-linux-tools" --graph-status "$work/full-linux-graph-status.json"
python3 -B tools/audit_hp_native_drm_symbol_owners.py --output "$work/new-owners" \
  --native-tree "$work/netbsd-full-linux" --object-dir "$work/full-linux-obj" \
  --tool-dir "$work/full-linux-tools" --graph-status "$work/full-linux-graph-status.json" \
  --build-status "$work/new-probe/status.json"
```

Variables above must identify actually verified existing inputs/new outputs;
the commands are a reproduction contract, not execution evidence. Old configured
reports lacking the current ledger fail closed. Stabilize generated ABI inputs
before probing; changed generated headers are reported, not silently accepted.
Additional selected native/kernel providers need ledgers with the same unit
fields (`state`, `source`, `source_sha256`, `d_exit`, `o_exit`,
`source_unchanged`, `artifact.path`, `artifact.sha256`, matching `preflight`).
Do not fabricate these records or substitute old unrelated `.o` files.

## Blockers and safety

RDC returned exhausted monthly quota; no retry/re-pair or paid executor was used.
Bounded strict-host-key, BatchMode owner SSH to HP timed out directly and through
both authenticated Spinnennet and Legion hops. This establishes unavailable
SSH execution for this session, not that HP crashed or that F77 is running.

Current boot/default/F77 recovery and early physical serial trace remain
unverified. Full 323-unit/native DRM/TTM/UVM/IRQ/PCI/GEM/PM ABI and final kernel
link remain open. No installation, reboot, boot-menu modification, firmware or
GPU-MMIO change, F83/F84 replay, hosted CI dispatch or cost-bearing resource
was performed. The functioning historical F77 boot path was not modified.
