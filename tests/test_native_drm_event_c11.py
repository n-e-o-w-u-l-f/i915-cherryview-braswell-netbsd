#!/usr/bin/env python3
"""Extract the actual event-reader functions; execute C only on HP NetBSD 11.

Without --native this checks source contracts and assembles the fixture in
memory.  The C fixture models uio/list/locking/allocator APIs; it is neither
a kernel ABI compilation nor physical DRM/KMS acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "compat/native-drm/drm_cdevsw.c"
FIXTURE = ROOT / "tests/fixtures/native_drm_event.c"
MARKER = "/* SOURCE_BOUND_FUNCTIONS */"
EXPECTED_CASES = (
    "error_translation",
    "zero_residual_before_count_validation",
    "zero_iovec_count_no_allocation",
    "negative_iovec_count_no_allocation",
    "empty_nonblocking",
    "initial_lock_restart",
    "initial_lock_eintr",
    "empty_wait_restart",
    "empty_wait_eintr",
    "wake_then_relock_restart_retains_event",
    "wake_relock_and_deliver",
    "undersized_buffer_requeues_without_copy",
    "first_fault_restores_cursor_and_queue_order",
    "second_fault_restores_remaining_iovec",
    "second_fault_crossing_iovecs_restores_both",
    "two_events_success_free_original_snapshot_size",
    "all_iovecs_consumed_free_original_snapshot_size",
    "progress_then_undersized_event_retained",
    "progress_returns_before_wait_or_eagain",
)
# Expected deterministic assertion and complete passed-case prefix for each
# mutant. An unrelated crash/nonzero status is not semantic rejection proof.
MUTANT_FAILURES = {
    "remove_both_progress_guards": (
        13, "drm_native_read_events(&ctx.file, &ctx.uio) == 0"),
    "omit_uio_cursor_restore": (
        12, "drm_native_read_events(&ctx.file, &ctx.uio) == EFAULT"),
    "omit_iovec_contents_restore": (
        12, "ctx.iov[i].iov_base == ctx.buffers[i]"),
    "free_using_remaining_iovec_count": (
        10, "size == ctx.allocation_size"),
    "omit_invalid_iovec_count_guard": (
        2, "size > 0 && size <= sizeof(ctx.iov)"),
}
LIMITATION = (
    "Native HP C11/UBSan execution of unchanged extracted function bodies "
    "with mock uio/list/lock/allocator APIs; not kernel ABI, physical copyout, "
    "concurrency, DRM/KMS, or full driver acceptance. Cursor rollback does "
    "not undo bytes already copied into user memory. KM_SLEEP ENOMEM and "
    "post-progress wait interruption are not reachable source paths."
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(source: str, start: str, end: str) -> str:
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("source function boundary changed: " + start)
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish].rstrip() + "\n"


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("source/mutant anchor changed: " + repr(old))
    return source.replace(old, new, 1)


def assemble() -> tuple[str, dict[str, str], dict[str, str]]:
    # Normalizing line endings changes no C tokens. Native Git sources use LF.
    raw = SOURCE.read_bytes()
    source = raw.decode("utf-8").replace("\r\n", "\n")
    functions = {
        "drm_native_error": extract(source,
            "static int\ndrm_native_error(long error)\n",
            "\ndev_t\nlinux_drm_minor_devno"),
        "drm_native_put_back": extract(source,
            "static void\ndrm_native_put_back(struct drm_file *priv, struct drm_pending_event *event)\n",
            "\nstatic int\ndrm_native_read_events("),
        "drm_native_read_events": extract(source,
            "static int\ndrm_native_read_events(struct linux_file *file, struct uio *uio)\n",
            "\nstatic int\ndrm_native_read("),
    }
    reader = functions["drm_native_read_events"]
    if reader.index("SIZE_MAX / sizeof(*saved_iov)") >= reader.index(
            "allocation_size = (size_t)uio->uio_iovcnt"):
        raise ValueError("iovec range check must precede snapshot sizing")
    if reader.index("*uio = saved_uio;") >= reader.rindex(
            "drm_native_put_back(priv, event);"):
        raise ValueError("copy failure must restore cursor before requeue")
    shared = "\n\tif (original_resid != uio->uio_resid)\n\t\treturn 0;\n"
    if shared not in reader.split("out:", 1)[1]:
        raise ValueError("shared exit must preserve completed events")
    template = FIXTURE.read_text(encoding="utf-8").replace("\r\n", "\n")
    if template.count(MARKER) != 1:
        raise ValueError("fixture must contain exactly one extraction marker")
    joined = "\n".join(functions.values())
    if source.count("#include <sys/cdefs.h>") != 1:
        raise ValueError("original source license boundary changed")
    # Generated C retains the complete original copyright/license notice.
    original_notice = source.split("#include <sys/cdefs.h>", 1)[0]
    assembled = original_notice + template.replace(MARKER, joined)
    mutations = {}
    without_inner = replace_once(joined,
        "\n\t\t\tif (original_resid != uio->uio_resid)\n\t\t\t\terror = 0;\n", "\n")
    mutations["remove_both_progress_guards"] = replace_once(
        without_inner, shared, "\n")
    mutations["omit_uio_cursor_restore"] = replace_once(
        joined, "\t\t\t*uio = saved_uio;\n", "")
    mutations["omit_iovec_contents_restore"] = replace_once(joined,
        "\t\t\tmemcpy(saved_uio.uio_iov, saved_iov,\n"
        "\t\t\t    (size_t)saved_uio.uio_iovcnt * sizeof(*saved_iov));\n", "")
    mutations["free_using_remaining_iovec_count"] = replace_once(joined,
        "kmem_free(saved_iov, allocation_size);",
        "kmem_free(saved_iov, (size_t)uio->uio_iovcnt * sizeof(*saved_iov));")
    mutations["omit_invalid_iovec_count_guard"] = replace_once(joined,
        "\tif (uio->uio_iovcnt <= 0 || (size_t)uio->uio_iovcnt >\n"
        "\t    SIZE_MAX / sizeof(*saved_iov))\n\t\treturn EINVAL;\n", "")
    mutants = {name: original_notice + template.replace(MARKER, body)
               for name, body in mutations.items()}
    identity = {
        "source_sha256": sha(raw),
        "fixture_sha256": sha(FIXTURE.read_bytes()),
        "assembled_sha256": sha(assembled.encode()),
        **{name + "_sha256": sha(body.encode())
           for name, body in functions.items()},
    }
    return assembled, mutants, identity


def require_native_hp() -> None:
    release = platform.release().split(".", 1)[0]
    if (platform.system() != "NetBSD" or release != "11" or
            platform.machine().lower() not in ("amd64", "x86_64") or
            socket.gethostname().split(".", 1)[0] != "hp-tpnw121"):
        raise ValueError("native C execution requires hp-tpnw121 / NetBSD 11 / amd64")
    if os.geteuid() == 0:
        raise ValueError("native C fixture requires the unprivileged HP owner")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--output", type=Path,
                        help="new private evidence directory; required with --native")
    args = parser.parse_args()
    try:
        if args.native:
            require_native_hp()  # Admission precedes any compiler/output creation.
        assembled, mutants, identity = assemble()
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if not args.native:
        if args.output is not None:
            parser.error("--output is only available with --native")
        print(json.dumps({"state": "SOURCE_ASSEMBLY_CONTRACT_PASS",
                          **identity, "mutant_count": len(mutants),
                          "native_execution": "NOT_RUN", "limitation": LIMITATION}, indent=2))
        return 0
    if args.output is None or not args.output.is_absolute():
        parser.error("--native requires an absolute new --output directory")
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir():
        parser.error("preserve previous evidence; output must be new with an existing parent")
    # Expected failing mutants must never leave core dumps on the HP filesystem.
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    output.mkdir(mode=0o700)
    report = {
        "state": "RUNNING", "started": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(), "system": platform.platform(),
        "python": platform.python_version(), "identity": identity,
        "source_path": str(SOURCE), "output": str(output),
        "limitation": LIMITATION, "checks": [],
        "mutation_note": "Progress mutant removes BOTH equivalent guards; runtime behavior alone does not distinguish the old and centralized guards.",
    }
    report_path = output / "status.json"

    def save() -> None:
        temporary = output / "status.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(report_path)

    save()
    try:
        env = dict(os.environ, LC_ALL="C", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        for name, code in {"actual_functions": assembled, **mutants}.items():
            c_path = output / (name + ".c")
            binary = output / name
            c_path.write_text(code, encoding="utf-8")
            # The frozen native DRM argv retains -Wextra/-Werror and explicitly
            # uses -Wno-sign-compare: HP_NATIVE_DRM_TASK_ENTRY_20261006.json,
            # native_three_unit_gate DRM row, lines525-528. Preserve the signed
            # mock residual and the original C body rather than casting it away.
            command = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wno-sign-compare",
                       "-pedantic", "-g", "-fsanitize=undefined",
                       "-fno-sanitize-recover=undefined", str(c_path), "-o", str(binary)]
            compiled = subprocess.run(command, text=True, capture_output=True,
                                      timeout=120, env=env)
            compile_log = output / (name + ".compile.log")
            compile_log.write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
            row = {"name": name, "command": command,
                   "source_sha256": sha(c_path.read_bytes()),
                   "compile_exit": compiled.returncode,
                   "compile_log_sha256": sha(compile_log.read_bytes())}
            report["checks"].append(row)
            save()
            if compiled.returncode != 0:
                raise RuntimeError("fixture/mutant did not compile: " + name)
            ran = subprocess.run([str(binary)], text=True, capture_output=True,
                                 timeout=30, env=env)
            run_log = output / (name + ".run.log")
            run_log.write_text(ran.stdout + ran.stderr, encoding="utf-8")
            positive = name == "actual_functions"
            observed_cases = [line.removeprefix("CASE_PASS ")
                              for line in ran.stdout.splitlines()
                              if line.startswith("CASE_PASS ")]
            row.update(run_exit=ran.returncode,
                       run_log_sha256=sha(run_log.read_bytes()),
                       binary_sha256=sha(binary.read_bytes()),
                       observed_case_names=observed_cases,
                       expected="PASS" if positive else "SEMANTIC_MUTANT_REJECTED")
            if positive:
                row["accepted"] = (
                    ran.returncode == 0 and tuple(observed_cases) == EXPECTED_CASES and
                    "NATIVE_DRM_EVENT_CASES_PASS count=19" in ran.stdout)
            else:
                prefix_count, assertion = MUTANT_FAILURES[name]
                reason_checks = {
                    "terminated_by_sigabrt": ran.returncode == -signal.SIGABRT,
                    "expected_case_prefix": tuple(observed_cases) == EXPECTED_CASES[:prefix_count],
                    "expected_assertion_present": assertion in ran.stderr,
                }
                row.update(expected_assertion=assertion,
                           expected_case_prefix_count=prefix_count,
                           rejection_reason_checks=reason_checks,
                           rejection_stderr=ran.stderr[-3000:])
                row["accepted"] = all(reason_checks.values())
            save()
            if not row["accepted"]:
                raise RuntimeError("unexpected fixture/mutant result: " + name)
            print(name, row["expected"], flush=True)
        if sha(SOURCE.read_bytes()) != identity["source_sha256"]:
            raise RuntimeError("canonical source changed during execution")
        report["state"] = "PASSED"
    except Exception as error:
        report["state"] = "FAILED"
        report["error"] = str(error)
    finally:
        report["finished"] = datetime.now(timezone.utc).isoformat()
        save()
    print("HP_NATIVE_DRM_EVENT_C11_UBSAN_" + report["state"], output)
    return 0 if report["state"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
