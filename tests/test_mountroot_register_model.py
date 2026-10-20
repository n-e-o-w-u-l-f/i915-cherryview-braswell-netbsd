#!/usr/bin/env python3
"""Isolated source-contract MODEL, not a NetBSD kernel or hardware test.

This intentionally reproduces the control-flow hazards observed at the pinned
NetBSD 11 source revision. No production driver code is modified.
"""
import unittest
from dataclasses import dataclass


@dataclass
class Dev:
    pending: int = 0
    queued_mountroot: bool = False
    alive: bool = True


def mountroot_enqueue_original(dev):
    dev.queued_mountroot = True  # frozen config_mountroot; no pending++


def detach_gate_original(dev):
    if dev.pending:
        return False
    dev.alive = False
    return True


def mountroot_run_original(dev):
    if not dev.queued_mountroot:
        return None
    dev.queued_mountroot = False
    return "LIVE" if dev.alive else "STALE_DEVICE"


def drm_register_original(ret):
    # frozen void i915_driver_register emits a log only on nonzero ret
    return 0  # frozen i915_driver_probe still returns success


def drm_register_corrected_model(ret):
    return ret if ret else 0


class SourceContractModel(unittest.TestCase):
    def test_pending_zero_allows_detach_before_queued_callback(self):
        d = Dev()
        mountroot_enqueue_original(d)
        self.assertEqual(d.pending, 0)
        self.assertTrue(detach_gate_original(d))
        self.assertEqual(mountroot_run_original(d), "STALE_DEVICE")

    def test_explicit_pending_guard_blocks_model_detach(self):
        d = Dev(pending=1, queued_mountroot=True)
        self.assertFalse(detach_gate_original(d))
        self.assertTrue(d.alive)

    def test_mountroot_callback_before_detach_is_live(self):
        d = Dev()
        mountroot_enqueue_original(d)
        self.assertEqual(mountroot_run_original(d), "LIVE")
        self.assertTrue(detach_gate_original(d))

    def test_immediate_mountroot_no_queue(self):
        d = Dev()
        self.assertIsNone(mountroot_run_original(d))

    def test_drm_negative_error_swallowed_in_frozen_model(self):
        self.assertEqual(drm_register_original(-12), 0)
        self.assertEqual(drm_register_original(0), 0)

    def test_drm_negative_error_propagated_in_corrected_model(self):
        self.assertEqual(drm_register_corrected_model(-12), -12)
        self.assertEqual(drm_register_corrected_model(0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
