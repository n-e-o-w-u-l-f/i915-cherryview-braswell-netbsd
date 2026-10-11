#!/usr/bin/env python3
"""Keep portable source checks independent of retired HP build stages."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "tools/run_pinned_i915_source_checks.py").read_text()

assert "/root/hp-driver-port-20261005" not in RUNNER

# These are NetBSD-ABI/compiler checks, not portable source checks.  They
# must receive a fresh explicit HP stage rather than run on a GitHub runner.
for test in (
    "test_linux_memory_ordering.py",
    "test_linux_kconfig.py",
    "test_linux_posix_types.py",
    "test_linux_rbtree.py",
    "test_linux_wordsize.py",
    "test_linux_raw_spinlock.py",
    "test_linux_instruction_pointer.py",
    "test_hp_shared_kconfig.py",
    "test_linux_compiler_math.py",
    "test_linux_math64.py",
    "test_linux_completion.py",
    "test_linux_typecheck_wordpart.py",
    "test_linux_container.py",
    "test_linux_typed_alloc.py",
    "test_linux_task_wait_worker.py",
    "test_linux_uuid.py",
    "test_linux_pwm.py",
    "test_linux_fatal_wait.py",
    "test_linux_bit_wait.py",
    "test_linux_task_entry.py",
):
    assert f'invoke("{test}"' not in RUNNER

for test in (
    "test_materialize_linux_i915.py",
    "test_drm_registration_source_contract.py",
    "test_chv_dpio_routing_source_contract.py",
    "test_edp_aux_irq_fallback.py",
    "test_chv_phy_powerwell_sync_reference.py",
):
    assert f'invoke("{test}"' in RUNNER

print("I915_PINNED_SOURCE_RUNNER_SCOPE_OK")
