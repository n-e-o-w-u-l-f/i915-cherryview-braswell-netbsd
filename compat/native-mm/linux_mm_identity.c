/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */

#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/mutex.h>
#include <sys/proc.h>
#include <sys/workqueue.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_map.h>
#include <linux/mm_identity_netbsd.h>

static kmutex_t linux_mm_lock;
static unsigned int linux_mm_identities;
static unsigned int linux_mm_creators;
static volatile unsigned int linux_mm_release_calls;
static bool linux_mm_admitted;
static struct workqueue *linux_mm_release_queue;
static struct work linux_mm_release_barrier;

static void linux_mm_release(struct vmspace *);
static void linux_mm_destroy(struct work *, void *);

static const struct uvmspace_runtime_ops linux_mm_runtime_ops = {
	.uro_release = linux_mm_release,
	.uro_calls = &linux_mm_release_calls,
};

int
linux_mm_identity_init(void)
{
	int error;

	/* Serialized with the native module lifecycle, before any publication. */
	KASSERT(!linux_mm_admitted && linux_mm_identities == 0 &&
	    linux_mm_creators == 0 && linux_mm_release_calls == 0);
	/* mmgrab/mmget/last mmdrop may run under actual task IRQ/RCU locks.
	 * The queue interlock must be at the same highest caller IPL. */
	mutex_init(&linux_mm_lock, MUTEX_DEFAULT, IPL_HIGH);
	error = workqueue_create(&linux_mm_release_queue, "lnxmm",
	    linux_mm_destroy, NULL, PRI_NONE, IPL_HIGH, WQ_MPSAFE);
	if (error != 0) {
		mutex_destroy(&linux_mm_lock);
		return error;
	}
	linux_mm_admitted = true;
	return 0;
}

int
linux_mm_identity_quiesce(void)
{
	mutex_enter(&linux_mm_lock);
	if (linux_mm_identities != 0 || linux_mm_creators != 0 ||
	    atomic_load_relaxed(&linux_mm_release_calls) != 0) {
		mutex_exit(&linux_mm_lock);
		return EBUSY;
	}
	linux_mm_admitted = false;
	mutex_exit(&linux_mm_lock);
	return 0;
}

void
linux_mm_identity_resume(void)
{
	mutex_enter(&linux_mm_lock);
	KASSERT(linux_mm_release_queue != NULL);
	linux_mm_admitted = true;
	mutex_exit(&linux_mm_lock);
}

int
linux_mm_identity_fini(void)
{
	/* Aggregate lifecycle must close all new identities before dismantling
	 * FILE/task resources. A refusal here preserves every MM resource. */
	ASSERT_SLEEPABLE();
	mutex_enter(&linux_mm_lock);
	if (linux_mm_admitted || linux_mm_identities != 0 || linux_mm_creators != 0 ||
	    atomic_load_relaxed(&linux_mm_release_calls) != 0) {
		mutex_exit(&linux_mm_lock);
		return EBUSY;
	}
	mutex_exit(&linux_mm_lock);
	workqueue_enqueue(linux_mm_release_queue, &linux_mm_release_barrier, NULL);
	workqueue_wait(linux_mm_release_queue, &linux_mm_release_barrier);
	/* The final worker may have dropped the charged count just before
	 * returning. Join its actual callback before module code can retire. */
	workqueue_destroy(linux_mm_release_queue);
	linux_mm_release_queue = NULL;
	mutex_destroy(&linux_mm_lock);
	return 0;
}

static void
linux_mm_destroy(struct work *work, void *cookie)
{
	struct mm_struct *mm;

	(void)cookie;
	if (work == &linux_mm_release_barrier)
		return;
	mm = (struct mm_struct *)((char *)work -
	    __builtin_offsetof(struct mm_struct, netbsd_release_work));
	ASSERT_SLEEPABLE();
	KASSERT(mm->netbsd_vmspace == NULL && atomic_read(&mm->mm_count) == 0);
	kmem_free(mm, sizeof(*mm));
	mutex_enter(&linux_mm_lock);
	KASSERT(linux_mm_identities != 0);
	linux_mm_identities--;
	mutex_exit(&linux_mm_lock);
}

static void
linux_mm_get_locked(struct mm_struct *mm)
{
	KASSERT(mutex_owned(&linux_mm_lock));
	if (__predict_false(atomic_read(&mm->mm_count) == INT_MAX))
		panic("Linux MM structure reference overflow");
	KASSERT(atomic_read(&mm->mm_count) > 0);
	atomic_inc(&mm->mm_count);
}

struct mm_struct *
linux_mm_identity_get(struct vmspace *vm)
{
	struct mm_struct *candidate, *mm;

	if (vm == NULL || VMSPACE_IS_KERNEL_P(vm))
		return NULL;
	/* Charge a constructor BEFORE any sleeping allocation/interlock. Its
	 * first caller still owns the aggregate module's entry code reference. */
	mutex_enter(&linux_mm_lock);
	if (!linux_mm_admitted) {
		mutex_exit(&linux_mm_lock);
		return NULL;
	}
	if (__predict_false(linux_mm_creators == UINT_MAX))
		panic("Linux MM constructor count overflow");
	linux_mm_creators++;
	mutex_exit(&linux_mm_lock);
	/* The caller owns a native vmspace/process/fault reference already. */
	candidate = kmem_zalloc(sizeof(*candidate), KM_SLEEP);
	mutex_enter(&vm->vm_runtime_lock);
	mutex_enter(&linux_mm_lock);
	if (!linux_mm_admitted || vm->vm_refcnt <= 0 ||
	    vm->vm_runtime_execs != 0 ||
	    (vm->vm_map.flags & VM_MAP_DYING) != 0) {
		KASSERT(linux_mm_creators != 0);
		linux_mm_creators--;
		mutex_exit(&linux_mm_lock);
		mutex_exit(&vm->vm_runtime_lock);
		kmem_free(candidate, sizeof(*candidate));
		return NULL;
	}
	mm = vm->vm_runtime;
	if (mm != NULL) {
		KASSERT(vm->vm_runtime_ops == &linux_mm_runtime_ops);
		linux_mm_get_locked(mm);
		KASSERT(linux_mm_creators != 0);
		linux_mm_creators--;
		mutex_exit(&linux_mm_lock);
		mutex_exit(&vm->vm_runtime_lock);
		kmem_free(candidate, sizeof(*candidate));
		return mm;
	}
	mm = candidate;
	mm->netbsd_vmspace = vm;
	/* Native runtime ownership plus this caller's structure reference. */
	atomic_set(&mm->mm_count, 2);
	vm->vm_runtime = mm;
	membar_producer();
	vm->vm_runtime_ops = &linux_mm_runtime_ops;
	if (__predict_false(linux_mm_identities == UINT_MAX))
		panic("Linux MM identity count overflow");
	linux_mm_identities++;
	KASSERT(linux_mm_creators != 0);
	linux_mm_creators--;
	mutex_exit(&linux_mm_lock);
	mutex_exit(&vm->vm_runtime_lock);
	return mm;
}

struct mm_struct *
linux_mm_identity_get_current(void)
{
	if (curproc == &proc0)
		return NULL;
	return linux_mm_identity_get(curproc->p_vmspace);
}

struct mm_struct *
linux_mm_identity_get_proc(struct proc *proc)
{
	struct vmspace *vm = NULL;
	struct mm_struct *mm = NULL;
	int error;
	bool foreign = proc != curproc;

	if (proc == &proc0)
		return NULL;
	/* Native exec holds this writer lock from kern_exec.c:798 through
	 * image replacement and the success release at 1398.  The raw native
	 * proc_vmspace_getref has no such interlock itself.  The current-LWP
	 * exception also avoids recursive reader acquisition during exec's
	 * descriptor-close callbacks while it owns that writer lock.
	 */
	if (foreign)
		rw_enter(&proc->p_reflock, RW_READER);
	mutex_enter(proc->p_lock);
	error = proc_vmspace_getref(proc, &vm);
	mutex_exit(proc->p_lock);
	if (error == 0) {
		mm = linux_mm_identity_get(vm);
		if (mm == NULL)
			uvmspace_free(vm);
		/* Otherwise transfer both our native pin and the new structure
		 * reference to the caller as one genuine mmget/mmput owner.
		 */
	}
	if (foreign)
		rw_exit(&proc->p_reflock);
	return mm;
}

void
mmgrab(struct mm_struct *mm)
{
	mutex_enter(&linux_mm_lock);
	linux_mm_get_locked(mm);
	mutex_exit(&linux_mm_lock);
}

void
mmdrop(struct mm_struct *mm)
{
	bool last;

	mutex_enter(&linux_mm_lock);
	KASSERT(atomic_read(&mm->mm_count) > 0);
	last = atomic_dec_and_test(&mm->mm_count);
	if (last) {
		/* Runtime ownership must have been retired by actual exec/free. */
		KASSERT(mm->netbsd_vmspace == NULL);
		KASSERT(linux_mm_identities != 0);
		/* Embedded work requires no allocation or blocking final release.
		 * Keep the object charged through actual native destruction. */
		workqueue_enqueue(linux_mm_release_queue,
		    &mm->netbsd_release_work, NULL);
	}
	mutex_exit(&linux_mm_lock);
}

bool
mmget_not_zero(struct mm_struct *mm)
{
	struct vmspace *vm;
	unsigned int old, next;
	bool acquired = false;

	mutex_enter(&linux_mm_lock);
	vm = mm->netbsd_vmspace;
	if (vm == NULL)
		goto out;
	/* Holding the MM lock excludes its native release hook and hence
	 * vmspace destruction.  The CAS excludes resurrecting a native count
	 * already decremented to zero by uvmspace_free before that hook.
	 */
	old = (unsigned int)vm->vm_refcnt;
	while (old != 0) {
		if (__predict_false(old == INT_MAX))
			panic("Linux native MM user reference overflow");
		next = atomic_cas_uint((volatile unsigned int *)&vm->vm_refcnt,
		    old, old + 1);
		if (next == old) {
			linux_mm_get_locked(mm);
			acquired = true;
			break;
		}
		old = next;
	}
out:
	mutex_exit(&linux_mm_lock);
	return acquired;
}

void
mmget(struct mm_struct *mm)
{
	if (__predict_false(!mmget_not_zero(mm)))
		panic("Linux mmget on a retired native MM identity");
}

void
mmput(struct mm_struct *mm)
{
	struct vmspace *vm;

	mutex_enter(&linux_mm_lock);
	vm = mm->netbsd_vmspace;
	KASSERT(vm != NULL && vm->vm_refcnt > 0);
	mutex_exit(&linux_mm_lock);
	/* May invoke the native MM release hook.  Do not hold linux_mm_lock. */
	uvmspace_free(vm);
	mmdrop(mm);
}

int
linux_mm_users(const struct mm_struct *mm)
{
	int users;

	mutex_enter(&linux_mm_lock);
	users = mm->netbsd_vmspace != NULL ? mm->netbsd_vmspace->vm_refcnt : 0;
	mutex_exit(&linux_mm_lock);
	return users;
}

static void
linux_mm_release(struct vmspace *vm)
{
	struct mm_struct *mm;

	mutex_enter(&linux_mm_lock);
	mm = vm->vm_runtime;
	KASSERT(mm != NULL && mm->netbsd_vmspace == vm);
	/* No future lock/pin operation may follow this retired native pointer. */
	mm->netbsd_vmspace = NULL;
	vm->vm_runtime = NULL;
	vm->vm_runtime_ops = NULL;
	mutex_exit(&linux_mm_lock);
	mmdrop(mm); /* Drop native runtime ownership, not VMA/task references. */
}

static struct vmspace *
linux_mm_lock_space(struct mm_struct *mm)
{
	struct vmspace *vm;

	/* A temporary actual address-space pin also excludes exec reuse. */
	mmget(mm);
	mutex_enter(&linux_mm_lock);
	vm = mm->netbsd_vmspace;
	KASSERT(vm != NULL);
	mutex_exit(&linux_mm_lock);
	return vm;
}

void
mmap_read_lock(struct mm_struct *mm)
{
	struct vmspace *vm = linux_mm_lock_space(mm);
	vm_map_lock_read(&vm->vm_map);
}

void
mmap_read_unlock(struct mm_struct *mm)
{
	struct vmspace *vm = mm->netbsd_vmspace;
	KASSERT(vm != NULL);
	vm_map_unlock_read(&vm->vm_map);
	mmput(mm);
}

void
mmap_write_lock(struct mm_struct *mm)
{
	struct vmspace *vm = linux_mm_lock_space(mm);
	vm_map_lock(&vm->vm_map);
}

void
mmap_write_unlock(struct mm_struct *mm)
{
	struct vmspace *vm = mm->netbsd_vmspace;
	KASSERT(vm != NULL);
	vm_map_unlock(&vm->vm_map);
	mmput(mm);
}
