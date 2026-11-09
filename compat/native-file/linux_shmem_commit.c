/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/*
 * Native shmem commit admission. NetBSD has no Linux vm_committed_as policy.
 * This component charges logical non-NORESERVE pages against a conservative
 * fresh native free-RAM/free-swap snapshot, retaining native kernel/pager
 * reserves. Charges have real constructor/grow/rollback/destructor owners.
 *
 * This is admission accounting, NOT preallocated physical pages, reserved
 * swap slots, a promise against later system-wide pressure, or Linux global
 * overcommit parity. Other native VM consumers retain their native policy.
 */
#include <sys/param.h>
#include <sys/atomic.h>
#include <sys/errno.h>
#include <sys/mutex.h>
#include <sys/systm.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_swap.h>
#include <linux/fs_netbsd.h>

static kmutex_t shmem_commit_lock;
static uint64_t shmem_committed_pages;

void
linux_shmem_commit_init(void)
{
    mutex_init(&shmem_commit_lock, MUTEX_DEFAULT, IPL_NONE);
    shmem_committed_pages = 0;
}

void
linux_shmem_commit_fini(void)
{
    if (shmem_committed_pages != 0)
        panic("linux_shmem_commit_fini: outstanding inode admission charge");
    mutex_destroy(&shmem_commit_lock);
}

int
linux_shmem_commit_set(struct linux_inode *inode, loff_t size)
{
    uint64_t pages, previous, add, limit;
    int freepages, reserves, swap_available, swap_inuse;

    ASSERT_SLEEPABLE();
    if (!inode->netbsd_shmem || inode->netbsd_noreserve)
        return 0;
    if (size < 0)
        return EINVAL;
    pages = howmany((uint64_t)size, PAGE_SIZE);
    mutex_enter(&shmem_commit_lock);
    previous = inode->netbsd_commit_pages;
    if (pages <= previous) {
        if (shmem_committed_pages < previous - pages)
            panic("linux_shmem_commit_set: charge underflow");
        shmem_committed_pages -= previous - pages;
        inode->netbsd_commit_pages = pages;
        mutex_exit(&shmem_commit_lock);
        return 0;
    }
    /* The actual native routine synchronizes per-CPU free-page counters.
     * Swap values are conservative admission snapshots, as in native VM
     * statistics; this lock serializes only this component's own charges. */
    freepages = uvm_availmem(false);
    reserves = atomic_load_relaxed(&uvmexp.reserve_kernel) +
        atomic_load_relaxed(&uvmexp.reserve_pagedaemon);
    limit = freepages > reserves ? (uint64_t)(freepages - reserves) : 0;
#if defined(VMSWAP)
    swap_available = atomic_load_relaxed(&uvmexp.swpgavail);
    swap_inuse = atomic_load_relaxed(&uvmexp.swpginuse);
    if (swap_available > swap_inuse)
        limit += (uint64_t)(swap_available - swap_inuse);
#else
    swap_available = swap_inuse = 0;
    (void)swap_available;
    (void)swap_inuse;
#endif
    add = pages - previous;
    if (add > limit || shmem_committed_pages > limit - add) {
        mutex_exit(&shmem_commit_lock);
        return ENOMEM;
    }
    shmem_committed_pages += add;
    inode->netbsd_commit_pages = pages;
    mutex_exit(&shmem_commit_lock);
    return 0;
}

