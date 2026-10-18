#!/usr/bin/env python3
"""Strict source-level Linux/NetBSD i915 VBlank flush-stage contract.

Caution: source checks and a FIFO model alone are NOT native C builds,
actual IRQ work generation proof or real kernel timing measurements.
"""
import argparse
import hashlib
from pathlib import Path
import re

LINUX_SHA256 = "9cd5fc6e2d1c5d34a165999d00af67c64de399b3f43ececb1077d85624574171"
NATIVE_SHA256 = "fe31c46d491a4b93589d6c8308895266de22ee66913864ddde8b1234c29b12be"


def require(ok, why):
    if not ok:
        raise AssertionError("VBLANK_FLUSH_PARITY_REFUSED: " + why)


def method(text, symbol):
    m = re.search(r"(?m)^void\s+" + re.escape(symbol) + r"\s*\(", text)
    require(m is not None, "missing method: " + symbol)
    at = text.index("{", m.end())
    level = 0
    for n in range(at, len(text)):
        if text[n] == "{":
            level += 1
        elif text[n] == "}":
            level -= 1
            if level == 0:
                return text[at + 1:n]
    raise AssertionError("unbalanced braces in " + symbol)


def section(text, first, last):
    start = text.index(first)
    end = text.index(last, start + len(first))
    return text[start:end]


def check(linux, native):
    lf = method(linux, "drm_vblank_work_flush")
    la = method(linux, "drm_vblank_work_flush_all")
    nf = method(native, "drm_vblank_work_flush")
    na = method(native, "drm_vblank_work_flush_all")
    # Linux itself uses live pending-list emptiness before a worker snapshot.
    # No generation snapshot exists during the *pending* phase in either OS.
    require("list_empty(&work->node)" in lf and
            "kthread_flush_work(&work->base)" in lf,
            "Linux single-work pending/worker two-phase contract changed")
    require("list_empty(&vblank->pending_work)" in la and
            "kthread_flush_worker(vblank->worker)" in la,
            "Linux all-work pending/worker two-phase contract changed")
    # NetBSD work->node belongs to pending OR ready, so pending_ref is the
    # correct marker of the Linux pending-only work->node state.
    require("!work->pending_ref" in nf and
            "if (!list_empty(&work->node) || work->running)" in nf and
            "nb_vblank_flush_ready_locked(vblank)" in nf,
            "NetBSD single-work pending/ready boundary changed")
    require("list_empty(&vblank->pending_work)" in na and
            "nb_vblank_flush_ready_locked(vblank)" in na,
            "NetBSD all-work pending/ready boundary changed")
    ready = section(native, "nb_vblank_ready(", "nb_vblank_worker_main(")
    require("work->pending_ref = false;" in ready and
            "list_add_tail(&work->node, &vblank->ready_work);" in ready,
            "NetBSD pending_ref transition no longer maps Linux pending list")
    handoff = section(native, "drm_handle_vblank_works(", "drm_vblank_work_init(")
    require("nb_vblank_ready(vblank, work);" in handoff and
            "nb_i915_vblank_ref_put_locked(vblank);" in handoff,
            "NetBSD pending work IRQ handoff no longer releases IRQ ref")
    fence = section(native, "nb_vblank_flush_ready_locked(", "drm_vblank_work_flush(")
    require("list_add_tail(&fence.node, &vblank->ready_work);" in fence and
            "list_empty(&fence.node) && !fence.running" in fence and
            "DRM_SPIN_WAKEUP_ALL(&vblank->worker_wait_queue," in fence,
            "NetBSD ready queue no longer uses completion fence")
    worker = section(native, "nb_vblank_worker_main(", "drm_vblank_worker_init(")
    for needle in (
        "list_del_init(&work->node);",
        "work->running = true;",
        "(*work->base.func)(&work->base);",
        "work->running = false;",
        "DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,",
    ):
        require(needle in worker, "NetBSD worker missing " + needle)
    require(worker.index("list_del_init(&work->node);") <
            worker.index("work->running = true;") <
            worker.index("(*work->base.func)(&work->base);") <
            worker.index("work->running = false;") <
            worker.index("DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,"),
            "NetBSD worker completion order incorrect")


def fifo_model():
    # After the Linux pending-stage gate opens, both worker flushes
    # synchronize only work queued before the flush snapshot/fence.
    for backlog in ([], ["a"], ["a", "b"], ["running", "a"]):
        ready = list(backlog) + ["fence"]
        expected = list(backlog) + ["fence"]
        seen = []
        while ready:
            name = ready.pop(0)
            seen.append(name)
            if name == "a":
                ready.append("a-rearmed")
            if name == "fence":
                break
        require(seen == expected, "FIFO fence waited on later rearmed callback")
        require("a-rearmed" not in seen,
                "newly rearmed work incorrectly joined completed snapshot")
    # A continuously renewed pending target may keep pending stage nonempty
    # indefinitely on BOTH Linux and NetBSD; this is a shared limitation,
    # not uniquely an absent NetBSD ready-work fence.
    pending = ["work"]
    for seq in range(10):
        pending[:] = ["work:next_vblank_" + str(seq)]
        require(len(pending) > 0,
                "snapshot pending evidence accidentally marked complete")


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--linux", required=True, type=Path)
    arg.add_argument("--native", required=True, type=Path)
    a = arg.parse_args()
    texts = []
    for p, digest in ((a.linux, LINUX_SHA256), (a.native, NATIVE_SHA256)):
        data = p.read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest,
                "frozen source SHA mismatch: " + str(p))
        texts.append(data.decode("utf-8"))
    linux, native = texts
    check(linux, native)
    fifo_model()
    mutations = (
        ("linux_lost_pending", linux.replace(
            "list_empty(&vblank->pending_work)",
            "list_empty(&vblank->ready_work)", 1), native),
        ("native_lost_pending", linux, native.replace(
            "list_empty(&vblank->pending_work)",
            "list_empty(&vblank->ready_work)", 1)),
        ("native_lost_pending_ref", linux, native.replace(
            "!work->pending_ref",
            "list_empty(&work->node)", 1)),
        ("native_lost_fence", linux, native.replace(
            "list_empty(&fence.node) && !fence.running",
            "list_empty(&fence.node)", 1)),
        ("native_lost_wakeup", linux, native.replace(
            "DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,",
            "/* lost wakeup */", 1)),
    )
    for label, l, n in mutations:
        require((l, n) != (linux, native), "invalid mutation " + label)
        try:
            check(l, n)
        except AssertionError:
            continue
        raise AssertionError("VBLANK_FLUSH_PARITY_REFUSED: accepted " + label)
    print("VBLANK_PINNED_LINUX_NETBSD_FLUSH_PENDING_AND_FENCE_5_MUTATIONS_PASS")
    print("Open: continuously rescheduled pending wait; scheduler FIFO-vs-RR;"
          " native IRQ/thread stress and HP build NOT_RUN")


if __name__ == "__main__":
    main()
