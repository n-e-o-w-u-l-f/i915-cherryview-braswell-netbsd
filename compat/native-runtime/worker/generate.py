#!/usr/bin/env python3
"""Generate the isolated native kthread candidate from its frozen baseline."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "base"
EXPECTED_BASE = {
    "kthread.h": "4384d635d5049d38bd322009007b04808afeb30e4c99c0e484ba95bfbd10933b",
    "linux_kthread.c": "566260787e456fe3ea40fb50f2cc93500faf0ccb4927a0a5e977777ad89d61bf",
}
for name, expected in EXPECTED_BASE.items():
    if hashlib.sha256((BASE / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError("changed frozen baseline: " + name)

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match: {old[:100]!r}")
    return text.replace(old, new)

header = (BASE / "kthread.h").read_text()
header = replace_once(header, "#include <linux/spinlock.h>",
    "#include <linux/spinlock.h>\n#include <linux/list.h>\n"
    "#include <linux/task_netbsd.h>")
header = replace_once(header, "#endif  /* _LINUX_KTHREAD_H_ */",
    (ROOT / "worker_header.inc").read_text() + "\n#endif  /* _LINUX_KTHREAD_H_ */")

source = (BASE / "linux_kthread.c").read_text()
source = replace_once(source, "#include <sys/condvar.h>",
    "#include <sys/param.h>\n#include <sys/condvar.h>\n"
    "#include <sys/errno.h>\n#include <sys/intr.h>\n#include <sys/systm.h>")
source = replace_once(source, "#include <linux/kthread.h>",
    "#include <linux/kthread.h>\n#include <linux/sched.h>")
source = source.replace("struct task_struct", "struct linux_kthread")
source = replace_once(source, "struct linux_kthread {\n",
    "struct linux_kthread {\n\tstruct task_struct *kt_task;\n"
    "\tstruct kthread_worker *kt_worker;\n\tbool kt_attached;\n")
start = source.index("static specificdata_key_t linux_kthread_key")
end = source.index("static void\nlinux_kthread_start", start)
source = source[:start] + '''int
linux_kthread_init(void)
{

	return linux_task_system_init();
}

void
linux_kthread_fini(void)
{

	linux_task_system_fini();
}

#define linux_kthread() _linux_kthread(__func__)
static struct linux_kthread *
_linux_kthread(const char *caller)
{
	struct task_struct *task = linux_current_task();
	struct linux_kthread *K;

	KASSERTMSG(task != NULL && task->lt_kthread != NULL,
	    "%s must be called from Linux kthread", caller);
	K = task->lt_kthread;
	return K;
}

''' + source[end:]
source = replace_once(source, "\tlwp_setspecific(linux_kthread_key, T);",
    "\tlinux_task_attach_current(T->kt_task);\n"
    "\tmutex_enter(&T->kt_lock);\n\tT->kt_attached = true;\n"
    "\tcv_broadcast(&T->kt_cv);\n\tmutex_exit(&T->kt_lock);")
source = replace_once(source,
    "\tT = kmem_zalloc(sizeof(*T), KM_SLEEP);\n",
    "\tT = kmem_zalloc(sizeof(*T), KM_SLEEP);\n"
    "\tT->kt_task = linux_task_alloc();\n"
    "\tif (T->kt_task == NULL) {\n\t\tkmem_free(T, sizeof(*T));\n"
    "\t\treturn NULL;\n\t}\n"
    "\tT->kt_task->lt_kthread = T; /* Not yet published. */\n")
source = replace_once(source, "\tKASSERT(T->kt_exited);",
    "\tunsigned long flags;\n\tstruct task_struct *task = T->kt_task;\n\n"
    "\t/* Native create failure does not create a runnable LWP. */\n"
    "\tKASSERT(T->kt_exited || T->kt_lwp == NULL);\n"
    "\traw_spin_lock_irqsave(&task->lt_lock, flags);\n"
    "\tKASSERT(task->lt_kthread == T);\n\ttask->lt_kthread = NULL;\n"
    "\traw_spin_unlock_irqrestore(&task->lt_lock, flags);")
source = replace_once(source,
    "\tkmem_free(T, sizeof(*T));\n}\n\nstruct linux_kthread *\nkthread_run",
    "\tkmem_free(T, sizeof(*T));\n\tput_task_struct(task);\n}\n\n"
    "static struct task_struct *\nlinux_kthread_spawn")
source = replace_once(source,
    "linux_kthread_spawn(int (*func)(void *), void *cookie, const char *name,\n"
    "    spinlock_t *interlock, drm_waitqueue_t *wq)",
    "linux_kthread_spawn(int (*func)(void *), void *cookie, const char *name,\n"
    "    spinlock_t *interlock, drm_waitqueue_t *wq,\n"
    "    struct kthread_worker *worker, int native_flags)")
source = replace_once(source,
    "\tT = kthread_alloc(func, cookie, interlock, wq);\n"
    "\terror = kthread_create(PRI_NONE, KTHREAD_MPSAFE, NULL,",
    "\tT = kthread_alloc(func, cookie, interlock, wq);\n"
    "\tif (T == NULL)\n\t\treturn ERR_PTR(-ENOMEM);\n"
    "\tT->kt_worker = worker;\n\tif (worker != NULL)\n"
    "\t\tworker->task = T->kt_task;\n"
    "\terror = kthread_create(PRI_NONE,\n"
    "\t    KTHREAD_MPSAFE|KTHREAD_MUSTJOIN|native_flags, NULL,")
source = replace_once(source,
    "\tif (error) {\n\t\tkthread_free(T);",
    "\tif (error) {\n\t\tif (worker != NULL)\n"
    "\t\t\tworker->task = NULL;\n\t\tkthread_free(T);")
source = replace_once(source, "\treturn T;\n}\n\nint\nkthread_stop",
    "\t/* Publish a common task with TLS/LWP identity already attached. */\n"
    "\tmutex_enter(&T->kt_lock);\n\twhile (!T->kt_attached)\n"
    "\t\tcv_wait(&T->kt_cv, &T->kt_lock);\n\tmutex_exit(&T->kt_lock);\n"
    "\treturn T->kt_task;\n}\n\nstruct task_struct *\n"
    "kthread_run(int (*func)(void *), void *cookie, const char *name,\n"
    "    spinlock_t *interlock, drm_waitqueue_t *wq)\n{\n\n"
    "\treturn linux_kthread_spawn(func, cookie, name, interlock, wq,\n"
    "\t    NULL, 0);\n}\n\nint\nkthread_stop")
source = replace_once(source, "kthread_stop(struct linux_kthread *T)\n{\n\tint ret;",
    "kthread_stop(struct task_struct *task)\n{\n"
    "\tstruct linux_kthread *T = task->lt_kthread;\n\tint ret;\n\n"
    "\tKASSERT(T != NULL);")
source = replace_once(source, "\t/* Free the (Linux) kthread.  */",
    "\t/* Drain the native MUSTJOIN LWP before reclaiming its backend. */\n"
    "\t(void)kthread_join(T->kt_lwp);\n\n\t/* Free the (Linux) kthread.  */")
for api in ["kthread_park", "kthread_unpark", "__kthread_should_park"]:
    source = replace_once(source, api + "(struct linux_kthread *T)\n{",
        api + "(struct task_struct *task)\n{\n"
        "\tstruct linux_kthread *T = task->lt_kthread;")
source = replace_once(source, "return __kthread_should_park(T);",
    "return __kthread_should_park(T->kt_task);")
source = replace_once(source,
    "\tspin_unlock(T->kt_interlock);\n\n\t/* Wait for the thread to finish.  */",
    "\tspin_unlock(T->kt_interlock);\n\n"
    "\t/* Also wake callbacks sleeping on the common Linux task CV. */\n"
    "\t(void)linux_wake_up_process(task);\n\n"
    "\t/* Wait for the thread to finish.  */")
source = replace_once(source,
    "\tDRM_SPIN_WAKEUP_ALL(T->kt_wq, T->kt_interlock);\n"
    "\tspin_unlock(T->kt_interlock);\n\n\t/*\n"
    "\t * Wait until the thread has issued kthread_parkme",
    "\tDRM_SPIN_WAKEUP_ALL(T->kt_wq, T->kt_interlock);\n"
    "\tspin_unlock(T->kt_interlock);\n"
    "\t(void)linux_wake_up_process(task);\n\n\t/*\n"
    "\t * Wait until the thread has issued kthread_parkme")
source = replace_once(source, "\twhile (T->kt_shouldpark) {\n",
    "\twhile (T->kt_shouldpark) {\n"
    "\t\tlinux_set_current_state(TASK_PARKED);\n")
source = replace_once(source,
    "\tmutex_exit(&T->kt_lock);\n\tspin_lock(T->kt_interlock);\n}",
    "\tlinux_set_current_state(TASK_RUNNING);\n"
    "\tmutex_exit(&T->kt_lock);\n\tspin_lock(T->kt_interlock);\n}")
source += "\n" + (ROOT / "worker.inc").read_text()

(ROOT / "include/linux/kthread.h").write_text(header)
(ROOT / "linux_kthread.c").write_text(source)
diff = []
for rel, old, new in [("include/linux/kthread.h", (BASE / "kthread.h").read_text(), header),
                      ("linux/linux_kthread.c", (BASE / "linux_kthread.c").read_text(), source)]:
    path = "sys/external/bsd/drm2/" + rel
    diff.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                   "a/" + path, "b/" + path))
(ROOT / "native-kthread-worker.patch").write_text("".join(diff))
(ROOT / "candidate-sha256.json").write_text(json.dumps({
    p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
    for p in ["include/linux/kthread.h", "linux_kthread.c", "worker.inc", "native-kthread-worker.patch"]
}, indent=2) + "\n")
