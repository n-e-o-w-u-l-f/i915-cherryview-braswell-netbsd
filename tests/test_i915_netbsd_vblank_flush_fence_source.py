#!/usr/bin/env python3
"""Source-level fence contract for the NetBSD VBlank work provider.

Only audits exact source ordering and a FIFO queue model.  This is NOT an
actual HP NetBSD kernel, IRQ, scheduler or concurrency test.
"""
import argparse
from pathlib import Path

REQUIRE = (
    ("worker removes queued node", "list_del_init(&work->node);\n\t\tKASSERT(!work->running);"),
    ("worker marks callback active", "work->running = true;"),
    ("worker marks callback complete", "work->running = false;"),
    ("worker executes callback", "(*work->base.func)(&work->base);"),
    ("fence inserted after existing ready callbacks",
     "list_add_tail(&fence.node, &vblank->ready_work);"),
    ("fence woken by worker waitqueue",
     "DRM_SPIN_WAKEUP_ALL(&vblank->worker_wait_queue,\n\t    &dev->event_lock);\n\tDRM_SPIN_WAIT_NOINTR_UNTIL"),
    ("fence waits until worker stops using the stack node",
     "list_empty(&fence.node) && !fence.running"),
    ("single flush waits for pending IRQ reference handoff",
     "&dev->event_lock, !work->pending_ref"),
    ("single flush fences active or ready work",
     "if (!list_empty(&work->node) || work->running)\n\t\tnb_vblank_flush_ready_locked(vblank);"),
    ("all flush waits pending vblank stage",
     "list_empty(&vblank->pending_work));\n\tKASSERT(error == 0);\n\tnb_vblank_flush_ready_locked(vblank);"),
)
FORBIDDEN = ("list_empty(&vblank->ready_work) &&\n\t    !vblank->worker_running",)


def check(source):
    for name, needle in REQUIRE:
        if source.count(needle) != 1:
            raise AssertionError(f"{name}: expected exactly one matching site")
    for needle in FORBIDDEN:
        if needle in source:
            raise AssertionError("obsolete live-ready-drain wait still present")
    worker = source.index("nb_vblank_worker_main(void *cookie)")
    start = source.index("list_del_init(&work->node);", worker)
    busy = source.index("work->running = true;", start)
    callback = source.index("(*work->base.func)(&work->base);", busy)
    done = source.index("work->running = false;", callback)
    wake = source.index("DRM_SPIN_WAKEUP_ALL(&vblank->work_wait_queue,", done)
    if not start < busy < callback < done < wake:
        raise AssertionError("worker callback/completion ordering changed")
    enqueue = source.index("list_add_tail(&fence.node, &vblank->ready_work);")
    fence_wait = source.index("list_empty(&fence.node) && !fence.running")
    if not enqueue < fence_wait:
        raise AssertionError("fence waited before enqueue")


def fifo_model():
    # The existing callback may self-rearm during execution.  A sentinel
    # queued behind that callback must finish before later ready work.
    ready = ["existing", "fence"]
    executed = []
    while ready:
        item = ready.pop(0)
        executed.append(item)
        if item == "existing":
            ready.append("self-rearmed after fence")
        if item == "fence":
            break
    assert executed == ["existing", "fence"]
    assert ready == ["self-rearmed after fence"]
    # A fence inserted behind an already queued second callback still waits
    # for both, not for a later producer.
    ready = ["one", "two", "fence", "later"]
    executed = []
    while ready:
        item = ready.pop(0)
        executed.append(item)
        if item == "fence":
            break
    assert executed == ["one", "two", "fence"] and ready == ["later"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--provider-c", type=Path, required=True)
    args = p.parse_args()
    source = args.provider_c.read_text()
    check(source)
    fifo_model()
    # Mutation refusal checks, not just positive string matching.
    for needle, substitute in (
        (REQUIRE[4][1], "list_add(&fence.node, &vblank->ready_work);"),
        (REQUIRE[6][1], "list_empty(&fence.node)"),
        (REQUIRE[8][1], "if (false) ;"),
        (REQUIRE[9][1], "list_empty(&vblank->ready_work));"),
    ):
        mutated = source.replace(needle, substitute, 1)
        assert mutated != source
        try:
            check(mutated)
        except AssertionError:
            continue
        raise AssertionError("dangerous mutation escaped source contract")
    print("I915_NETBSD_VBLANK_FLUSH_FENCE_SOURCE_MODEL_PASS")
    print("Scope: source ordering + FIFO model; NetBSD HP native/runtime NOT_RUN")


if __name__ == "__main__":
    main()
