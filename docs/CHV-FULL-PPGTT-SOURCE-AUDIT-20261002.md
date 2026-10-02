# Cherryview full 32-bit PPGTT — pinned source / real-overlay audit

Status: **SOURCE-VERIFIED, NATIVE BUILD AND HARDWARE UNVERIFIED**. This document concerns the genuine existing Legion staging change `/opt/ChatGPT/hp-driver-port/chv-full-ppgtt.real.patch`; it does not claim a deployable kernel or full 323-TU i915/DRM/TTM/LinuxKPI parity.

## Authoritative inputs

- Frozen NetBSD/src `03d918f6d0e81fa05b8f1160eca0628ad39988a6`: `i915_pci.c` `chv_info`, `gt/intel_lrc.c` `execlists_request_alloc`, `gt/intel_gtt.h` (PDP helpers and 3-level count), `i915_reg.h` (ring-PDP register offsets).
- Frozen Linux `fd179f8a05be3ccae366b9b96e176b51fbe54aab`: `i915_pci.c` `chv_info` and `gt/intel_execlists_submission.c` `emit_pdps` / `execlists_request_alloc`. **The Linux function is in `gt/intel_execlists_submission.c`, not in Linux `gt/intel_lrc.c`.**
- Actual separate NetBSD linked worktree `/opt/ChatGPT/hp-driver-port/port-netbsd` read via the permitted read-only Legion device interface. Original host staging patch `chv-full-ppgtt.real.patch` also inspected read-only. No Legion command or source edit was performed.

## Verified source delta

| Contract | Pinned NetBSD | Pinned Linux / existing genuine overlay |
|---|---|---|
| Cherryview PPGTT mode | `INTEL_PPGTT_ALIASING` | `INTEL_PPGTT_FULL` |
| Cherryview PPGTT size | 32 bits | 32 bits |
| Three-level PDP count | `GEN8_3LVL_PDPES=4` already defined | Four PDP entries emitted |
| Execlists allocation | Unconditional invalidate only | For non-4-level VM, emit PDPs before normal invalidate |
| Required NetBSD helpers | `i915_page_dir_dma_addr`, `i915_vm_to_ppgtt`, `i915_vm_is_4lvl` already defined | Used by staged `emit_pdps` |
| Ring PDP registers | `GEN8_RING_PDP_UDW` / `GEN8_RING_PDP_LDW` already defined | High/low DMA address for PDP indices 3,2,1,0 |

The genuine Legion `gt/intel_lrc.c:emit_pdps()` implementation **matches pinned Linux after removing C comments and whitespace and omitting one immediately duplicated final `intel_ring_advance(rq, cs)` in the frozen Linux function**. The original Linux function contains three `intel_ring_advance` calls, including two consecutive advances of the same unmodified pointer at the very end; the staged NetBSD implementation contains the first advance after `MI_ARB_DISABLE + MI_NOOP` and one final advance after all four PDP writes and `MI_ARB_ENABLE`. The staged `execlists_request_alloc()` is otherwise identical to pinned Linux after comment/whitespace normalization. Pinned NetBSD lacks `emit_pdps` and currently selects aliasing PPGTT.

A separate source contract `tests/test_chv_full_ppgtt_source_contract.py` (commit `3a4129e27f202863b5b6cff3ab2a6c4b22bedfb9`) verifies the two frozen revisions, actual CHV feature values, four-PDP count, existing NetBSD helper/register interfaces and the pinned Linux request path. With **a genuine distinct** `--overlay-tree`, it additionally checks the staged CHV FULL/32 setting and normalized exact function/request-allocation equivalence; frozen-only CI explicitly prints `OVERLAY_UNVERIFIED`, not a misleading success for the inaccessible host. The common pinned runner invokes this test and the manually dispatched CI sparse checkout includes the additional pinned source files.

## Hardware-state order and remaining acceptance gates

The pinned Linux and staged NetBSD sequence is: disable arbitration and advance the ring; flush residual context-load operations; invalidate to avoid forcewake errors; reserve `4 * GEN8_3LVL_PDPES + 2` ring dwords; emit posted LRI to the 4 PDP UDW/LDW address pairs from the per-context page-directory DMA addresses, highest PDP index first; enable arbitration and advance; run the existing final request invalidate. Reordering commands or updating wrong MMIO engine offsets can hang the GPU.

**Before promoting staged PPGTT to a kernel candidate**, verify exact staged patch byte identity and actual `git apply`/reverse-check on frozen and real overlay, error paths for ring allocation/flush, per-context VM allocation/32-bit address mapping, DMA and page-directory lifetime, GGTT/PPGTT switching, engine reset, PM/suspend/resume and the independent DRM/TTM/LinuxKPI build dependency graph. Execute native NetBSD object and combined kernel builds, then HP runtime/KMS tests only with the F77 rollback retained. None of these checks is established by source-token equivalence alone.

## Independent isolated strict-C behavior test (2026-10-02)

A disposable, local host C11 harness using the genuine Legion `emit_pdps()` source and `execlists_request_alloc()` control flow (C comments removed in the harness) was compiled with `-std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -fno-omit-frame-pointer`. Its mocked engine/ring, context, PDP DMA addresses, register offsets and flush API explicitly checked **seven** scenarios: a successful three-level request emits 20 ring dwords, all four PDP high/low DMA register pairs in the order 3/2/1/0, posted LRI, disable/enable arbitration, and the two preparatory plus final invalidate flushes; a four-level VM emits no PDPs; first/second `intel_ring_begin` failures propagate; and the first, second and final flush failures propagate without incorrectly clearing the existing request's reserved-space accounting. The local command returned the marker `I915_CHV_FULL_PPGTT_ISOLATED_C11_ASAN_UBSAN_7_CASES_OK` after **7/7 PASS**. The independent scratch test source is retained in the conversation artifact `chv_ppgtt_isolated_test.c`, not as a new production driver change.

**Evidence limitation:** this C harness copied the function into an isolated mock; it did not build the actual `intel_lrc.o` under NetBSD, validate kernel ABI or DMA bus mappings, complete the full PPGTT/GGTT lifecycle, or execute GPU commands on Cherryview. The published Python frozen/overlay source-contract script and the main test runner are independently still **NOT EXECUTED**. F77 and every Legion source were left unmodified.

The unrelated GitHub-hosted Actions blocker remains separate: existing full and minimal jobs failed before reporting any steps, with logs unavailable. Automatic workflow triggering is quarantined pending an independently verified runner diagnosis; the new PPGTT test is not claimed executed in hosted CI.
