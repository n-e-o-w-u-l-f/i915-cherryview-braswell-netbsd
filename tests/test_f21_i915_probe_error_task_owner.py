#!/usr/bin/env python3
"""Check the real F21 i915 error branch from pinned NetBSD source.

Only tests the empty-queue task-owner correction; does not assert
that queued tasks are safe to discard or that the HP panic is fixed.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
PATH = Path("sys/external/bsd/drm2/i915drm/i915_pci_autoconf.c")
SHA = "9798385b02f247c08db9b16624d5ddc9d11a8ca5"
PATCH = ROOT / "patches/candidates/netbsd11-f21-i915-empty-probe-error-task-owner-20261028.patch"

PRE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stddef.h>
struct taskqueue { int pending; };
struct softc {
    void *sc_task_thread;
    struct taskqueue sc_tasks;
};
static struct softc state;
static int token;
static int error_log, zeroed;
#define SIMPLEQ_EMPTY(q) ((q)->pending == 0)
#define atomic_store_relaxed(p,v) do { *(p)=(v); zeroed++; } while(0)
static void aprint_error_dev(void *self, const char *message, int error) {
    (void)self;
    assert(error != 0);
    assert(message[0] != '\0');
    error_log++;
}
static int run_actual_error_branch(struct softc *sc, int error) {
    void *self = 0;
"""
POST = r"""
    return 0;
}
int main(void) {
    for (int tasks=0;tasks<=1;tasks++) {
        state=(struct softc){.sc_task_thread=&token,.sc_tasks={.pending=tasks}};
        error_log=zeroed=0;
        int result=run_actual_error_branch(&state, 7);
        assert(result == 7);
        assert(error_log == 1);
        assert(zeroed == (tasks==0));
        assert((state.sc_task_thread == NULL) == (tasks==0));
        assert(state.sc_tasks.pending==tasks);
    }
    puts("F21_ACTUAL_I915_ERROR_BRANCH_EMPTY_AND_QUEUED_PASS");
    return 0;
}
"""


def require(ok, why):
    if not ok:
        raise AssertionError(why)


def run():
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-tree", type=Path, required=True)
    args = p.parse_args()
    srcroot = args.netbsd_tree.resolve(strict=True)
    if (srcroot / ".git").exists():
        head = subprocess.check_output(["git", "-C", str(srcroot),
                                        "rev-parse", "HEAD"], text=True).strip()
        require(head == PIN, "wrong Git HEAD")
    data = (srcroot / PATH).read_bytes()
    oid = hashlib.sha1(b"blob " + str(len(data)).encode() +
                       b"\0" + data).hexdigest()
    require(oid == SHA, "source SHA drift")
    before = data.decode()
    with tempfile.TemporaryDirectory(prefix="f21-i915-") as tmp:
        root = Path(tmp)
        target = root / PATH
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        for flags in (("--check",), ()):
            subprocess.run(["git", "-C", str(root), "apply",
                            "--whitespace=error", *flags, str(PATCH)],
                           check=True, capture_output=True, text=True)
        after = target.read_text()
        from_s = "\terror = -i915_driver_probe(&sc->sc_pci_dev, ent);\n"
        to_s = "\tsc->sc_drm_dev = pci_get_drvdata(&sc->sc_pci_dev);"
        original = before[before.index(from_s):before.index(to_s)]
        patched = after[after.index(from_s):after.index(to_s)]
        require(after.replace(patched, original, 1) == before,
                "unexpected source modification outside probe-error branch")
        require(patched.count("SIMPLEQ_EMPTY(&sc->sc_tasks)") == 1,
                "wrong queue guard")
        require(patched.count("atomic_store_relaxed(&sc->sc_task_thread, NULL)") == 1,
                "wrong task-owner cleanup")
        require(patched.index("SIMPLEQ_EMPTY(") <
                patched.index("atomic_store_relaxed(") <
                patched.index("\t\treturn;"),
                "cleanup does not precede return")
        exact_branch = patched[patched.index("\tif (error) {"):
                               patched.index("\n\tsc->sc_drm_dev") if
                               "\n\tsc->sc_drm_dev" in patched else len(patched)]
        exact_branch = exact_branch.replace("\t\treturn;", "\t\treturn error;",1)
        require(exact_branch.count("return error;") == 1, "branch reconstruction")
        compile_body = PRE + exact_branch + "\n    return -1;\n}\n" + POST[POST.index("int main(void)"):]
        for cc in ("gcc", "clang"):
            c = root / (cc+".c")
            out = root / (cc+".out")
            c.write_text(compile_body)
            build = subprocess.run([cc,"-std=gnu11","-Wall","-Wextra",
                                    "-Werror","-fsanitize=undefined",
                                    str(c),"-o",str(out)],
                                   capture_output=True,text=True)
            require(build.returncode == 0, build.stderr)
            exec_result = subprocess.run([str(out)], capture_output=True,text=True)
            require(exec_result.returncode==0, exec_result.stderr)
            print(cc,exec_result.stdout.strip())
        print("F21_PINNED_GIT_APPLY_TWO_COMPILERS_EMPTY_ONLY_STATE_REPAIR_PASS")


if __name__ == "__main__":
    run()
