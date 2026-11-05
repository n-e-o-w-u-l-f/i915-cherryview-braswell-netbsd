/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _LINUX_MAPPING_NETBSD_H_
#define _LINUX_MAPPING_NETBSD_H_

#include <sys/types.h>
#include <sys/queue.h>
#include <uvm/uvm_prot.h>
#include <linux/types.h>
#include <linux/mm_abi_types_netbsd.h>

struct linux_address_space;
struct vm_map;

/*
 * One actual native map-entry interval.  Its enclosing VMA owner retains the
 * post-mmap file/inode/device mapping lifetime until its last fault reference
 * has drained and the owner is destroyed, including after unregister.  The
 * mapping/registry pointer is immutable after registration and is not cleared
 * by unregister: a retained fault can safely reject a retired interval.
 * All fields below except the immutable mapping pointer and list link
 * are read or changed under the address-space registry's native rwlock.
 * Native map writers deactivate BEFORE pmap removal; a fault producer uses
 * the same registry lock and a captured generation before installing PTEs.
 */
struct linux_native_mapping {
	TAILQ_ENTRY(linux_native_mapping) link;
	struct linux_address_space *mapping;
	struct vm_map *map;
	vaddr_t start;
	vaddr_t end;
	voff_t offset;
	vm_prot_t protection;
	vm_prot_t max_protection;
	uint64_t generation;
	bool registered;
	bool active;
	bool shared_writable;
};

struct linux_mapping_snapshot {
	struct vm_map *map;
	vaddr_t start;
	vaddr_t end;
	voff_t offset;
	vm_prot_t protection;
	vm_prot_t max_protection;
	uint64_t generation;
};

int linux_mapping_registry_init(struct linux_address_space *);
int linux_mapping_registry_destroy(struct linux_address_space *);
/* Native errno. Publication takes invalidate read with trylock, then the
 * registry writer, while the caller may hold its Native map/object locks.
 * EBUSY publishes nothing. Backing discard holds invalidate write and may
 * proceed only with registry count zero; inactive/pending VMAs count too. */
int linux_mapping_register(struct linux_address_space *,
    struct linux_native_mapping *, struct vm_map *, vaddr_t, vaddr_t,
    voff_t, vm_prot_t, vm_prot_t, bool);
/* Infallible internal copy. The Native source-map/exclusive-child interlock
 * keeps parent registered, so invalidate's unmapped-only writer cannot
 * observe count zero. No new admission or trylock is needed for this clone. */
void linux_mapping_clone_register(struct linux_native_mapping *,
    struct linux_native_mapping *, struct vm_map *, vaddr_t, vaddr_t,
    voff_t, vm_prot_t, vm_prot_t);
void linux_mapping_activate(struct linux_native_mapping *);
void linux_mapping_update(struct linux_native_mapping *, vaddr_t, vaddr_t,
    voff_t, vm_prot_t, vm_prot_t, bool);
void linux_mapping_deactivate(struct linux_native_mapping *);
void linux_mapping_unregister(struct linux_native_mapping *);
bool linux_mapping_snapshot(struct linux_native_mapping *,
    struct linux_mapping_snapshot *);

/* Native errno.  A successful result installs actual PTEs and synchronizes
 * the native pmap.  Cache flags must be a supported PMAP_CACHE_* encoding.
 * The caller owns/pins every supplied physical page for the operation and
 * guarantees revocation before its backing can be released/reused.
 */
int linux_mapping_enter_pfn_range(struct linux_native_mapping *, uint64_t,
    vaddr_t, paddr_t, vsize_t, vm_prot_t, unsigned int);
bool linux_mapping_extract(struct linux_native_mapping *, uint64_t,
    vaddr_t, paddr_t *);
void linux_mapping_zap(struct linux_native_mapping *, vaddr_t, vsize_t);

int mapping_mapped(const struct linux_address_space *);
void unmap_mapping_range(struct linux_address_space *, loff_t, loff_t, int);
void unmap_mapping_pages(struct linux_address_space *, linux_pgoff_t,
    linux_pgoff_t, bool);

#endif /* _LINUX_MAPPING_NETBSD_H_ */
