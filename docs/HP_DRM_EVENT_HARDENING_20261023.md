# HP-native DRM event failure-path validation — 2026-10-23

Recovered the two-file event hardening from preserved, unpublished commit
`1f9124d761bd6e8f0a0897f318f1d34c5a1c81d4` onto active base
`8a164f10c45c3d66f7648376ccd2177c8dfe81ba`. The original checkout and preserved
history remain untouched. The other two unpublished graph/runner commits were
not merged: replacing their files wholesale would discard newer replay and
owner-audit protections.

## Source change

`drm_native_read_events` now validates the iovec count before calculating the
snapshot allocation size. The shared cleanup returns success when complete
events have already been delivered. The existing copy-fault branch already
preserved that progress; this centralizes the invariant. On amd64 the genuine
integer iovec count cannot overflow size_t by multiplication with an iovec.
This is defensive hardening, not a demonstrated KMS or black-screen fix.

The replay tool retains its strict canonical-source digest guard, updated only
to the reviewed LF source SHA256:
`1717ce53cb1d903067b87798502d665c8a79f16763c6d433ebf0ef331845bc43`.
Historical source hashes and prior kernel evidence remain historical.

## Actual HP execution

Authenticated direct strict-key SSH reached HP `megal`, NetBSD11.0 amd64,
running F77. Compilation ran only on this HP, as the unprivileged owner.
The tested staged Git tree was `9895d1ae1edbd0e1586f4f22e149b3abebd5b115`;
all five changed code/test blobs match the native receipt SHA256 values.
This report and evidence are the subsequent documentation-only additions.

- Four DRM source contracts: PASS.
- Existing native argv relocation source regression: PASS.
- Existing bridge-header/partial-link command source regression: PASS.
- Actual extracted `drm_native_error`, `drm_native_put_back` and
  `drm_native_read_events` bodies: **19 native C11/UBSan cases PASS**.
- Five deliberate semantic mutants: **all rejected** at the expected assertion,
  with the exact preceding case sequence and SIGABRT. An arbitrary failure is
  not accepted as mutation proof.

The fixture mutates real mock iovec cursors across boundaries. It verifies
first/second-event partial-copy rollback, retained completed events, event
ordering and space, wait/lock interruption, invalid counts, undersized buffers,
balanced locks and release of the original snapshot allocation size. Compiler
flags retain Werror and UBSan; the sign-compare exception matches the preserved
native DRM compiler invocation rather than changing the signed mock residual.
Expected assertion failures cannot create core files.

The first attempt's 19 positive cases passed. Its cursor-restore mutant hit the
reader-return assertion before the predicted cursor assertion: without rollback,
the shared exit sees the partial residual change as progress. The strict oracle
refused that unexpected assertion. Under a fresh PRE, only the expected assertion
was corrected; a new isolated checkout/output repeated the entire acceptance.
The failed attempt and controller UTF-8 handoff repair remain recorded in
Agent-Governance, not overwritten.

[Structured evidence](evidence/HP_NATIVE_DRM_EVENT_C11_20261023.json).
HP artifacts: `/home/megal/hp-driver-source-stage-20261023/event-fixture-a02/`.
The earlier failed `event-fixture-a01` output is preserved.

## Acceptance boundary

This is a native userland source-bound mock fixture, not a kernel ABI compile,
physical copyout, concurrency test, GPU operation or full 410-unit port closure.
Cursor rollback cannot undo bytes already copied to user memory. KM_SLEEP has
no recoverable ENOMEM branch here, and the wait path is reached only before
any completed event. The progress mutant removes both equivalent guards; the
runtime cases alone do not distinguish their original and centralized forms.

The prior private diagnostic kernel was built from the earlier i915 base and
was not rebuilt or altered in this step. It does not establish native ABI
acceptance for this modern adapter change. No installed kernel, EFI, boot.cfg,
radio or old worktree changed. Physical early-console capture and exercised
F77/stock fallback remain prerequisites for any experimental boot. KMS, WPA2,
PM/recovery and modern Linux323 semantic parity remain OPEN.
