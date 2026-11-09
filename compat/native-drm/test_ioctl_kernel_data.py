#!/usr/bin/env python3
"""HP-native C11/UBSan model of the exact source-derived ioctl functions.

This deliberately models DRM descriptors, file state, allocation and uaccess.
It does not validate kernel headers, real file lifetime, UVM or hardware.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import socket
import subprocess
import sys

from prepare_ioctl_patch import derive, STAGED_SOURCE

ROOT = Path(__file__).resolve().parents[2]
OWNER = Path(__file__).resolve().parent
CASES = (
    "small_caller_large_driver", "large_caller_small_driver",
    "output_only_zeroes_entire_caller",
    "direction_intersection_suppresses_output",
    "zero_size_accepts_null_buffer", "permission_error_retains_output",
    "driver_error_retains_output", "unplugged_has_no_output_or_dispatch",
    "invalid_type_has_no_output", "invalid_driver_index_has_no_dispatch",
    "invalid_core_index_has_no_dispatch", "missing_handler_has_no_output",
    "allocation_failure_unwinds_without_output", "required_native_parameters",
    "driver_table_dispatch", "root_master_render_permissions",
    "user_wrapper_keeps_uaccess", "user_copyin_fault_unwinds",
    "user_copyout_fault_overrides_dispatch_error",
)
FUNCTIONS = ("drm_ioctl_permit", "drm_ioctl_kernel", "drm_ioctl_dispatch",
             "drm_ioctl", "drm_ioctl_kernel_data")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def function(text, name):
    start = re.search(r"(?m)^(?:static\s+)?(?:int|long)\s+" +
        re.escape(name) + r"\([^;{]*\)\n\{", text)
    if start is None:
        raise ValueError("exact source function missing: " + name)
    opening = text.index("{", start.start())
    tokens = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|'
        r"'(?:\\.|[^'\\])*'|[{}]")
    depth = 0
    for token in tokens.finditer(text, opening):
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if depth == 0:
                return text[start.start():token.end()] + "\n"
    raise ValueError("unbalanced source function: " + name)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("semantic control source anchor changed: " + old[:70])
    return text.replace(old, new, 1)


def controls(actual):
    return (
        ("dispatches_into_short_native_buffer", replace_once(actual,
            "retcode = drm_ioctl_kernel(filp, func, kdata, ioctl->flags);",
            "retcode = drm_ioctl_kernel(filp, func, "
            "native_out_size ? native_data : kdata, ioctl->flags);"),
         CASES[0], "p[i] == 0"),
        ("ignores_canonical_allocation_size", replace_once(actual,
            "ksize = max(max(in_size, out_size), drv_size);",
            "ksize = max(max(in_size, out_size), drv_size & 0U);"),
         CASES[0], "last_alloc_size >= callback_zero_end"),
        ("does_not_zero_extend_input", replace_once(actual,
            "memset(kdata + in_size, 0, ksize - in_size);",
            "memset(kdata + in_size, 0xa5, ksize - in_size);"),
         CASES[0], "p[i] == 0"),
        ("ignores_permission_failure", replace_once(actual,
            "ret = drm_ioctl_permit(flags, file_priv);\n"
            "\tif (unlikely(ret))\n\t\treturn ret;",
            "ret = drm_ioctl_permit(flags, file_priv);\n"
            "\tif (unlikely(ret))\n\t\tret = 0;"),
         CASES[5], "ret == -EACCES"),
        ("suppresses_native_error_output", replace_once(actual,
            "retcode = drm_ioctl_kernel(filp, func, kdata, ioctl->flags);\n"
            "\tif (native_out_size) {",
            "retcode = drm_ioctl_kernel(filp, func, kdata, ioctl->flags);\n"
            "\tif (native_out_size && retcode == 0) {"),
         CASES[5], "ret == -EACCES"),
    )


def disable_core():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
        help="complete unchanged pinned Linux drivers/gpu/drm/drm_ioctl.c")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (platform.system() != "NetBSD" or
            platform.release().split(".", 1)[0] != "11" or
            socket.gethostname().split(".", 1)[0] != "hp-tpnw121" or
            os.geteuid() == 0):
        parser.error("C compilation requires the unprivileged HP NetBSD 11 owner")
    output = args.output.resolve()
    if (output.parent != ROOT.parent.resolve() or
            not output.name.startswith("i915-ioctl-model-") or
            output.exists() or output.is_symlink()):
        parser.error("new isolated i915-ioctl-model-* sibling output required")
    source = args.source.resolve(strict=True)
    before = source.read_bytes()
    after = derive(before)
    contract = json.loads((OWNER / "drm_ioctl_kernel_data.json").read_text(
        encoding="utf-8"))
    patch = "".join(difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        "a/" + STAGED_SOURCE, "b/" + STAGED_SOURCE)).encode("utf-8")
    if (sha(before) != contract["before_sha256"] or
            sha(after) != contract["after_sha256"] or
            sha(patch) != contract["patch_sha256"] or
            patch != (OWNER / "drm_ioctl_kernel_data.patch").read_bytes()):
        raise ValueError("complete source/derived patch contract changed")
    actual = "\n".join(function(after.decode("utf-8"), name)
        for name in FUNCTIONS)
    fixture = (OWNER / "test_ioctl_kernel_data.c").read_text(encoding="utf-8")
    marker = "/* ACTUAL_FUNCTIONS */"
    if fixture.count(marker) != 1:
        raise ValueError("model function insertion point changed")
    variants = (("actual", actual, None, None), *controls(actual))
    output.mkdir(mode=0o700)
    report = {
        "state": "RUNNING", "host": socket.gethostname(),
        "source_sha256": sha(before), "derived_source_sha256": sha(after),
        "patch_sha256": sha(patch),
        "actual_function_sha256": sha(actual.encode("utf-8")),
        "model_fixture_sha256": sha(fixture.encode("utf-8")),
        "tests": [],
        "limitation": "Actual five DRM ioctl function bodies compiled against "
            "explicit delegated descriptor/file/allocator/uaccess models; "
            "not kernel-header, native file/UVM, full-link or hardware acceptance.",
    }
    status = output / "status.json"

    def save():
        temporary = output / "status.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        temporary.replace(status)

    save()
    try:
        for name, bodies, failing_case, assertion in variants:
            cfile = output / (name + ".c")
            binary = output / name
            generated = fixture.replace(marker, bodies)
            cfile.write_text(generated, encoding="utf-8", newline="\n")
            argv = ["/usr/bin/cc", "-std=c11", "-O1", "-g", "-Wall",
                "-Wextra", "-Werror", "-fsanitize=undefined",
                "-fno-sanitize-recover=undefined", str(cfile), "-o", str(binary)]
            build = subprocess.run(argv, capture_output=True, text=True,
                timeout=120)
            (output / (name + ".build.log")).write_text(
                build.stdout + build.stderr, encoding="utf-8", newline="\n")
            row = {"name": name, "command": argv,
                "generated_source_sha256": sha(cfile.read_bytes()),
                "compile_exit": build.returncode}
            report["tests"].append(row)
            save()
            if build.returncode != 0:
                raise RuntimeError("C model/control failed to compile: " + name)
            run = subprocess.run([str(binary)], capture_output=True, text=True,
                timeout=30, preexec_fn=disable_core)
            (output / (name + ".stdout.log")).write_text(run.stdout,
                encoding="utf-8", newline="\n")
            (output / (name + ".stderr.log")).write_text(run.stderr,
                encoding="utf-8", newline="\n")
            passed = re.findall(r"(?m)^PASS (\w+)$", run.stdout)
            started = re.findall(r"(?m)^RUN (\w+)$", run.stdout)
            row.update(run_exit=run.returncode, passed_cases=passed,
                started_cases=started, binary_sha256=sha(binary.read_bytes()))
            if failing_case is None:
                row["accepted"] = (run.returncode == 0 and
                    passed == list(CASES) and started == list(CASES) and
                    "DRM_IOCTL_KERNEL_DATA_MODEL_PASS 19\n" in run.stdout and
                    run.stderr == "")
            else:
                index = CASES.index(failing_case)
                row.update(expected_case=failing_case,
                    expected_assertion=assertion)
                row["accepted"] = (run.returncode == -signal.SIGABRT and
                    passed == list(CASES[:index]) and
                    started == list(CASES[:index + 1]) and
                    "CHECK_FAILED " + assertion + "\n" in run.stderr)
            save()
            if not row["accepted"]:
                raise RuntimeError("strict C model/control oracle failed: " + name)
            print("HP_DRM_IOCTL_MODEL", name, "PASS", flush=True)
        if source.read_bytes() != before:
            raise RuntimeError("pinned source changed while running model")
        report["state"] = "PASSED"
    except Exception as exc:
        report.update(state="FAILED", error=str(exc))
        raise
    finally:
        save()
    print("HP_DRM_IOCTL_KERNEL_DATA_MODEL_PASS 19_CASES_5_CONTROLS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
