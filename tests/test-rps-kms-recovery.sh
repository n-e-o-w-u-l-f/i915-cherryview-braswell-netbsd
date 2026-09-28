#!/bin/sh
set -eu

src=${1:-sys/external/bsd/drm2/dist/drm/i915/gt/intel_rps.c}

if [ ! -f "$src" ]; then
    echo "usage: $0 /path/to/intel_rps.c" >&2
    exit 2
fi

fn=$(sed -n '/^void intel_rps_mark_interactive(/,/^}/p' "$src")

printf '%s\n' "$fn" | grep -Fq 'intel_gt_has_init_error(rps_to_gt(rps))' || {
    echo "FAIL: intel_rps_mark_interactive lacks the GT-init-error guard" >&2
    exit 1
}

lock_line=$(printf '%s\n' "$fn" | grep -n 'mutex_lock(&rps->power.mutex)' | head -1 | cut -d: -f1)
guard_line=$(printf '%s\n' "$fn" | grep -n 'intel_gt_has_init_error(rps_to_gt(rps))' | head -1 | cut -d: -f1)

[ "$guard_line" -lt "$lock_line" ] || {
    echo "FAIL: guard must execute before the RPS mutex is touched" >&2
    exit 1
}

echo "PASS: KMS recovery skips destroyed RPS state after GT init failure"
