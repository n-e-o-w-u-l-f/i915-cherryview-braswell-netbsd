# Pinned i915 source-check scope — 2026-10-11

`tools/run_pinned_i915_source_checks.py` is a **host-independent** gate. It
accepts a clean NetBSD checkout at
`03d918f6d0e81fa05b8f1160eca0628ad39988a6` and a clean Linux checkout at
`fd179f8a05be3ccae366b9b96e176b51fbe54aab`, then verifies source contracts,
candidate patch applicability and composed patch ordering.

It intentionally does not invoke tests that compile a NetBSD kernel ABI or
depend on a private HP object tree. Those checks previously embedded the now
deleted `/root/hp-driver-port-20261005` path, so running them from GitHub's
Linux runner could only produce a misleading failure. They must be migrated
to an explicitly supplied, newly created owner-stage path before the next HP
ABI build.

Passing this gate proves neither an i915 kernel object build nor a working
display. The next graphics hardware action remains the trace-first F77
recovery procedure in `docs/HP_I915_BLACK_SCREEN_ROOT_CAUSE_20261011.md`.
