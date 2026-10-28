#!/usr/bin/env python3
"""Compile/execute complete F22-patched native i915drmkms_attach_real().

F21 and F22 are applied to full exact original NetBSD source bytes.
The entire real function and the entire real F22 helper are passed to
host GCC/Clang without C-body rewriting. External kernel/DRM APIs
alone are mocked. Test both HP_I915_FWFB_FAILOVER off/on, real
probe-failure and success task ordering, queue lifetimes, and console.
This is NOT a NetBSD object or HP boot.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_f22_i915_fwfb_failover as base  # noqa: E402

DRIVER = base.DRIVER
CONFIG = base.CONFIG
SHAS = base.SHAS
F21 = base.F21
F22 = base.F22

STRUCT_OLD = """struct i915drmkms_softc {
    struct genfb_softc sc_fw_genfb;
    int pending;
};"""
STRUCT_NEW = """struct pci_attach_args { int pci_id; };
struct pci_dev { int pci_id; };
struct drm_device { int alive; };
struct intel_device_info { int generation; };
struct pci_device_id { uintptr_t driver_data; };
struct i915drmkms_task {
    void (*ift_fn)(struct i915drmkms_task *);
    struct { struct i915drmkms_task *next; } ift_u;
};
struct i915drmkms_task_head {
    struct i915drmkms_task *head;
};
struct i915drmkms_softc {
    struct genfb_softc sc_fw_genfb;
    device_t sc_dev;
    struct pci_attach_args sc_pa;
    void *sc_task_thread;
    struct i915drmkms_task_head sc_tasks;
    void *sc_task_wq;
    struct drm_device *sc_drm_dev;
    struct pci_dev sc_pci_dev;
};"""

EXTRAS = r"""
#define __diagused __attribute__((unused))
#define KASSERT(x) assert(x)
#define SIMPLEQ_EMPTY(q) ((q)->head == NULL)
#define SIMPLEQ_FIRST(q) ((q)->head)
#define SIMPLEQ_REMOVE_HEAD(q, field) do { \
    assert((q)->head != NULL); (q)->head = (q)->head->ift_u.next; \
} while (0)
#define atomic_store_relaxed(ptr, value) do { *(ptr) = (value); owner_clears++; } while (0)

static struct intel_device_info intel_info = {.generation=8};
static struct pci_device_id pci_id = {.driver_data=(uintptr_t)&intel_info};
static struct drm_device drm_dev = {.alive=1};
static int probe_fails, pmf_allowed, probe_calls, pmf_calls;
static int tasks_executed, owner_clears, enqueue_during_probe;
static struct i915drmkms_task task;
static void task_cb(struct i915drmkms_task *);
static int current_lwp;
static void *curlwp = &current_lwp;

static const struct pci_device_id *
i915drmkms_pci_lookup(const struct pci_attach_args *pa) {
    assert(pa == &sc.sc_pa);
    return &pci_id;
}
static int i915_driver_probe(struct pci_dev *dev,
                             const struct pci_device_id *id) {
    assert(dev == &sc.sc_pci_dev && id == &pci_id);
    probe_calls++;
    if (enqueue_during_probe) {
        /* This is how native synchronous callback scheduling
         * populates the queue while i915_driver_probe runs. */
        assert(sc.sc_task_thread == curlwp);
        assert(sc.sc_tasks.head == NULL);
        task.ift_fn = task_cb;
        task.ift_u.next = NULL;
        sc.sc_tasks.head = &task;
    }
    return probe_fails ? -7 : 0;
}
static struct drm_device *pci_get_drvdata(struct pci_dev *dev) {
    assert(dev == &sc.sc_pci_dev);
    return &drm_dev;
}
static bool i915drmkms_suspend(device_t dev, const void *q) {
    (void)dev; (void)q; return true;
}
static bool i915drmkms_resume(device_t dev, const void *q) {
    (void)dev; (void)q; return true;
}
static bool pmf_device_register(device_t dev,
    bool (*suspend)(device_t,const void *),
    bool (*resume)(device_t,const void *)) {
    assert(dev == self && suspend != NULL && resume != NULL);
    pmf_calls++;
    return pmf_allowed != 0;
}
static void task_cb(struct i915drmkms_task *task) {
    assert(task != NULL);
    assert(sc.sc_task_thread == curlwp);
    tasks_executed++;
}
"""

MAIN = r"""
int main(void) {
    int cases = 0;
    for (int fail=0;fail<=1;fail++)
    for (int queued=0;queued<=1;queued++)
    for (int scenario=0;scenario<7;scenario++)
    for (int pmf=0;pmf<=1;pmf++) {
        sc=(struct i915drmkms_softc){0};
        cons=(struct consdev){.cn_dev=NODEV};
        cn_tab=&cons;
        dict=(struct mock_props){
            .is_console=true, .has_console=true,
            .has_width=true, .has_height=true, .has_depth=true,
            .has_stride=true, .has_address=true, .has_virtual=true,
            .width=1366,.height=768,.depth=32,.stride=5464,
            .address=0xe0000000ULL,.virtual_address=0x10000000ULL
        };
        child_available=init_success=assign_dev=property_set_ok=1;
        attach_error=0;
        searches=init_calls=attach_calls=0;
        lock_held=locks=unlocks=errors=successes=set_calls=0;
        probe_calls=pmf_calls=tasks_executed=owner_clears=0;
        probe_fails=fail;
        pmf_allowed=pmf;
        enqueue_during_probe=queued;
        sc.sc_tasks.head=NULL;

        switch (scenario) {
        case 0: break;  // successful ordinary preattach
        case 1: dict.is_console=false; break;
        case 2: cn_tab=NULL; break;
        case 3: child_available=0; break;
        case 4: dict.width=200; break;
        case 5: attach_error=ENXIO; break;
        case 6: cons.cn_dev=33; break;
        }
        i915drmkms_attach_real(self);

        assert(probe_calls==1);
        assert(lock_held==0 && locks==unlocks);
        assert(owner_clears == (fail && queued ? 0 : 1));
        if (!fail) {
            assert(sc.sc_task_thread == NULL);
            assert(sc.sc_drm_dev == &drm_dev);
            assert(sc.sc_tasks.head == NULL);
            assert(tasks_executed == queued);
            assert(pmf_calls == 1);
            assert(searches==0 && init_calls==0 && attach_calls==0);
        } else {
            assert(sc.sc_drm_dev == NULL);
            assert(pmf_calls == 0 && tasks_executed == 0);
            assert((sc.sc_tasks.head!=NULL)==queued);
            assert((sc.sc_task_thread!=NULL)==queued);
            if (queued || !F22_BUILD_FLAG) {
                assert(searches==0 && init_calls==0 && attach_calls==0);
                assert(successes==0);
            } else if (scenario==0) {
                assert(searches==1 && init_calls==1 && attach_calls==1);
                assert(successes==1 && cons.cn_dev==42);
            } else if (scenario==3) {
                assert(searches==1 && init_calls==0 && attach_calls==0);
            } else if (scenario==5) {
                assert(searches==1 && init_calls==1 && attach_calls==1);
                assert(successes==0);
            } else {
                assert(searches==0 && init_calls==0 && attach_calls==0);
            }
        }
        cases++;
    }
    assert(cases==56);
    printf("F23_FULL_REAL_I915_ATTACH_56_CASES_PASS_F22_%d\n",
           F22_BUILD_FLAG);
    return 0;
}
"""


def check(ok: bool, why: str) -> None:
    if not ok:
        raise AssertionError(why)


def sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def real_function(src: str) -> str:
    start=src.index("static void\ni915drmkms_attach_real(device_t self)\n{")
    end=src.index("\nstatic int\ni915drmkms_detach(",start)
    return src[start:end]


def main() -> None:
    p=argparse.ArgumentParser()
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--netbsd-tree",type=Path)
    modes.add_argument("--verified-blob-dir",type=Path)
    args=p.parse_args()
    orig=(args.netbsd_tree or args.verified_blob_dir).resolve(strict=True)
    if args.netbsd_tree:
        head=subprocess.check_output(
            ["git","-C",str(orig),"rev-parse","HEAD"],text=True).strip()
        check(head==base.PIN,"wrong NetBSD pinned HEAD")
    with tempfile.TemporaryDirectory(prefix="f23-i915-attach-real-") as temp:
        root=Path(temp)
        for path,expected in SHAS.items():
            raw=(orig/path).read_bytes()
            check(sha(raw)==expected,f"wrong original {path}")
            file=root/path
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(raw)
        base.patch_apply(root,F21)
        base.patch_apply(root,F22)
        driver=(root/DRIVER).read_text()
        fn=real_function(driver)
        helper=base.source_func(driver)
        check("i915drmkms_fwfb_failover(self);" in fn,
              "native i915 function lacks F22 error call")
        check(fn.index("i915_driver_probe(") <
              fn.index("i915drmkms_fwfb_failover(self);") <
              fn.index("pci_get_drvdata("),
              "actual F22 native control flow mismatch")
        stub=base.HOST
        check(stub.count(STRUCT_OLD)==1,"F22 mock layout drift")
        stub=stub.replace(STRUCT_OLD,STRUCT_NEW)
        for cc in ("gcc","clang"):
            for std in ("gnu99","gnu11"):
                for enabled in (0,1):
                    # No modifications to fn or helper source bodies.
                    # Only harness external APIs and C preprocessor
                    # selection differ.
                    code=(stub+EXTRAS+
                          "#if HP_I915_FWFB_FAILOVER\n"+
                          helper+"\n#endif\n"+
                          fn+"\n"+
                          f"#define F22_BUILD_FLAG {enabled}\n"+
                          MAIN)
                    name=f"{cc}_{std}_option_{enabled}"
                    c=root/(name+".c")
                    binary=root/(name+".out")
                    c.write_text(code)
                    command=[cc,"-std="+std,"-Wall","-Wextra","-Werror",
                             "-fsanitize=undefined",
                             "-Wno-unused-function",
                             "-fno-sanitize-recover=all"]
                    if enabled:
                        command+=["-DHP_I915_FWFB_FAILOVER=1"]
                    command += [str(c),"-o",str(binary)]
                    result=subprocess.run(command,
                                          capture_output=True,text=True)
                    check(result.returncode==0,
                          name+" compile: "+result.stderr)
                    run=subprocess.run([str(binary)],
                                       capture_output=True,text=True)
                    check(run.returncode==0,name+" run: "+run.stderr)
                    check("56_CASES_PASS" in run.stdout,
                          name+" PASS marker missing")
                    print("F23_COMPLETE_I915DRMKMS_ATTACH_REAL_PASS",name)
    print("F23_F21_F22_REAL_I915_ATTACH_REAL_448_GCC_CLANG_UBSAN_CASES_PASS")
    print("F23_NOT_NETBSD_NATIVE_KERNEL_OBJECT_OR_HP_BOOT")


if __name__=="__main__":
    main()
