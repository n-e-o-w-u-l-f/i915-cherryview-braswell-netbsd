#!/usr/bin/env python3
"""Exact native notifier owner -> real task/MM structure lifetime and entry.

Source transformation only; no host, compiler, install or boot operation.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK = "sys/external/bsd/drm2/linux/linux_task.c"
HEADER = "sys/external/bsd/drm2/include/linux/task_netbsd.h"
BEFORE = {
    TASK: "1b435ea0d47726f9de3bc9d49bbec4b5f26bcbf31dc4d217daa4ae00df8d7f2d",
    HEADER: "fb3c0fd2ddb558868cf8c3ef4b566a9eeced50da236e2fd74b5f86038c0cda8e",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("non-unique native task anchor: " + old[:100])
    return text.replace(old, new, 1)


def derive():
    path = ROOT / "compat/native-task-notifier/generate.py"
    spec = importlib.util.spec_from_file_location("native_task_notifier", path)
    notifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notifier)
    _, before, _, _ = notifier.sources()
    for path, expected in BEFORE.items():
        if sha(before[path]) != expected:
            raise ValueError("tested native task source changed: " + path)
    task, header = before[TASK].decode(), before[HEADER].decode()
    owner = (HERE / "task_mm_owner.inc").read_text(encoding="utf-8")
    spare_path = ROOT / "compat/native-file/task_entry_preallocated.inc"
    spare_bytes = spare_path.read_bytes().replace(b"\r\n", b"\n")
    spare = spare_bytes.decode()
    quiesce_path = ROOT / "compat/native-file/task_quiesce_retained.inc"
    quiesce_bytes = quiesce_path.read_bytes().replace(b"\r\n", b"\n")
    spare = once(spare, "\t\tget_task_struct(task);\n",
        "\t\tget_task_struct(task);\n\t\tlinux_task_refresh_mm(task);\n")
    task = once(task, "#include <sys/workqueue.h>\n",
        "#include <sys/workqueue.h>\n#include <linux/mm_identity_netbsd.h>\n")
    task = once(task, "void\nlinux_task_attach_current(struct task_struct *task)",
        owner + "\n" + quiesce_bytes.decode() + "\n" + spare +
        "\nvoid\nlinux_task_attach_current(struct task_struct *task)")
    task = once(task, "    KASSERT(lwp_getspecific(task_key) == NULL);\n",
        "    KASSERT(lwp_getspecific(task_key) == NULL);\n"
        "    linux_task_refresh_mm(task);\n")
    task = once(task, "        linux_task_unreserve();\n        return task;\n",
        "        linux_task_unreserve();\n"
        "        linux_task_refresh_mm(task);\n        return task;\n")
    task = once(task,
        "        get_task_struct(task);\n        linux_task_unreserve();\n",
        "        get_task_struct(task);\n        linux_task_unreserve();\n"
        "        linux_task_refresh_mm(task);\n")
    task = once(task, "            ASSERT_SLEEPABLE();\n"
        "            KASSERT(!cv_has_waiters(&task->lt_sleep_cv));\n",
        "            ASSERT_SLEEPABLE();\n"
        "            if (task->mm != NULL)\n"
        "                mmdrop(task->mm);\n"
        "            task->mm = NULL;\n"
        "            KASSERT(!cv_has_waiters(&task->lt_sleep_cv));\n")
    header = once(header, "struct task_struct {\n",
        "struct mm_struct;\nstruct task_struct {\n")
    header = once(header, "    struct lwp *lt_lwp;\n",
        "    struct lwp *lt_lwp;\n"
        "    /* Structure ref only: no vmspace -> task/VMA -> vmspace cycle.\n"
        "     * Pointer replacement/read is protected by lt_lock. */\n"
        "    struct mm_struct *mm;\n")
    header = once(header, "void linux_task_entry_leave(struct task_struct **);\n",
        "void linux_task_entry_leave(struct task_struct **);\n"
        "void linux_task_entry_enter_preallocated(struct task_struct **,\n"
        "    struct task_struct **);\n"
        "struct mm_struct *linux_get_task_mm(struct task_struct *);\n")
    header = once(header, "int linux_task_system_quiesce(void);\n",
        "int linux_task_system_quiesce(void);\n"
        "int linux_task_system_quiesce_retained(struct task_struct *);\n")
    after = {TASK: task.encode(), HEADER: header.encode()}
    return before, after, {
        "task_mm_owner.inc": sha(owner.encode()),
        "compat/native-file/task_entry_preallocated.inc": sha(spare_bytes),
        "compat/native-file/task_quiesce_retained.inc": sha(quiesce_bytes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before, after, assets = derive()
    patch = "".join("".join(difflib.unified_diff(
        before[p].decode().splitlines(True), after[p].decode().splitlines(True),
        "a/" + p, "b/" + p)) for p in BEFORE).encode()
    target = args.output / "task_mm_owner.patch"
    contract = args.output / "task_mm_owner.json"
    if not args.output.is_dir() or target.exists() or contract.exists():
        parser.error("existing owned directory with new patch/contract required")
    state = {"version": 2, "required_prior": "exact compiled task-notifier",
        "files": {p: {"before_sha256": sha(before[p]),
            "after_sha256": sha(after[p])} for p in BEFORE},
        "assets_sha256": assets, "patch_sha256": sha(patch),
        "acceptance": "Source preparation only. Native MM identity V4, "
            "actual task entry/exec races, teardown and full link remain gates."}
    target.write_bytes(patch)
    contract.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8",
        newline="\n")
    print("NATIVE_TASK_MM_OWNER_SOURCE_PREPARED")


if __name__ == "__main__":
    main()
