# HP i915 symbol-owner recursive scan — 2026-10-15

Source: `main@27fd4d7d483be456158884c08d04446dd5312326`; working branch
`work/hp-native-drm-stage-replay-20261015`. This is a source/build-audit tool correction, **not**
a change to the GPU driver hardware state machine or a completed kernel build.

## PRE / Cause

The existing `tools/audit_hp_native_drm_symbol_owners.py` used
`p.glob("*.o")` to enumerate provider objects. This only examines
top-level objects. NetBSD object trees have nested directories, so the
tool could mistakenly classify an unresolved symbol as lacking a provider,
and its 121-symbol report could be incomplete. Source-owner name matching
alone cannot prove a linked definition. No physical NetBSD/i915 source is
changed by this test or audit.

## Change

`provider_objects()` now uses a recursive object scan under *explicitly
authorized* native object roots, resolves duplicate paths, omits the partial
`ld -r` object under investigation, and refuses symlinks escaping selected
provider roots. The scan fails closed above 100000 candidate objects to
avoid an uncontrolled input explosion.

`tests/test_hp_drm_symbol_owner_scan.py` exercises nested objects,
duplicate roots, omission of the partial link, archive exclusion, and
symlink escape rejection. A Python-only isolated unit test executed on
Legion (via a temporary harness; no native compile) and reported
`I915_HP_DRM_SYMBOL_OWNER_RECURSIVE_SCAN_TEST_PASS`.

## POST / Scope

The test confirms object path enumeration semantics only. It does not
demonstrate matching symbol definitions, object ABI suitability,
333+ translation-unit integration, final kernel link, or a usable display.
(The frozen full i915 reference currently contains 323 active C units;
the separate DRM/TTM dependency closure remains open.)

Next: run the updated scanner with current genuine HP object roots and
`x86_64--netbsd-nm` (HP only), then classify unresolved names by actual
compiled owner, native kernel provider, conditional build exclusion,
or missing adapter. Maintain a full per-unit dependency map before
any unobservable F83/F84-style hardware retest.
