/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */

#include <sys/param.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/rwlock.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_map.h>
#include <uvm/uvm_pmap.h>
#include <linux/fs_netbsd.h>
#include <linux/mapping_netbsd.h>
#include <linux/rwsem.h>
#include <linux/spinlock.h>

struct linux_mapping_registry {
	krwlock_t lock;
	TAILQ_HEAD(, linux_native_mapping) entries;
	unsigned long count;
	bool dying;
};

static bool
linux_mapping_interval(vaddr_t start, vaddr_t end, voff_t offset,
    vm_prot_t protection, vm_prot_t maximum)
{
	return offset >= 0 && start < end &&
	    ((start | end | (uintmax_t)offset) & (PAGE_SIZE - 1)) == 0 &&
	    (uintmax_t)(end - start) <=
	    (uintmax_t)__type_max(voff_t) - (uintmax_t)offset &&
	    (protection & maximum) == protection &&
	    (maximum & ~VM_PROT_ALL) == 0;
}

static void
linux_mapping_advance(struct linux_native_mapping *entry)
{
	/* Never let an ancient fault transaction become valid after wrap. */
	if (__predict_false(entry->generation == UINT64_MAX))
		panic("Linux VMA mapping generation exhausted");
	entry->generation++;
}

static bool
linux_mapping_physical_range(paddr_t physical, vsize_t length)
{
	uintmax_t first = (uintmax_t)physical;
	uintmax_t maximum = (uintmax_t)__type_max(paddr_t);

	return first <= maximum &&
	    (uintmax_t)(length - PAGE_SIZE) <= maximum - first;
}

int
linux_mapping_registry_init(struct linux_address_space *mapping)
{
	struct linux_mapping_registry *registry;

	KASSERT(mapping != NULL && mapping->netbsd_mappings == NULL);
	registry = kmem_zalloc(sizeof(*registry), KM_SLEEP);
	rw_init(&registry->lock);
	TAILQ_INIT(&registry->entries);
	init_rwsem(&mapping->invalidate_lock);
	init_rwsem(&mapping->i_mmap_rwsem);
	spin_lock_init(&mapping->i_private_lock);
	atomic_set(&mapping->i_mmap_writable, 0);
	mapping->netbsd_mappings = registry;
	return 0;
}

int
linux_mapping_registry_destroy(struct linux_address_space *mapping)
{
	struct linux_mapping_registry *registry = mapping->netbsd_mappings;

	KASSERT(registry != NULL);
	rw_enter(&registry->lock, RW_WRITER);
	if (registry->count != 0) {
		rw_exit(&registry->lock);
		return EBUSY;
	}
	KASSERT(TAILQ_EMPTY(&registry->entries));
	registry->dying = true;
	rw_exit(&registry->lock);
	/* The last inode owner excludes new registry users at this boundary. */
	KASSERT(atomic_read(&mapping->i_mmap_writable) == 0);
	spin_lock_destroy(&mapping->i_private_lock);
	destroy_rwsem(&mapping->i_mmap_rwsem);
	destroy_rwsem(&mapping->invalidate_lock);
	rw_destroy(&registry->lock);
	mapping->netbsd_mappings = NULL;
	kmem_free(registry, sizeof(*registry));
	return 0;
}

int
linux_mapping_register(struct linux_address_space *mapping,
    struct linux_native_mapping *entry, struct vm_map *map,
    vaddr_t start, vaddr_t end, voff_t offset, vm_prot_t protection,
    vm_prot_t maximum, bool shared_writable)
{
	struct linux_mapping_registry *registry = mapping->netbsd_mappings;
	int error;

	if (map == NULL || !linux_mapping_interval(start, end, offset,
	    protection, maximum))
		return EINVAL;
	KASSERT(entry != NULL && entry->mapping == NULL &&
	    !entry->registered && registry != NULL);
	/* Native callers may already own map/object locks.  Never sleep behind
	 * truncate's invalidate writer while holding those locks.  Publication
	 * must nevertheless share its interlock: count==0 under that writer
	 * remains stable through the backing mutation. */
	if (!down_read_trylock(&mapping->invalidate_lock))
		return EBUSY;
	rw_enter(&registry->lock, RW_WRITER);
	if (registry->dying) {
		rw_exit(&registry->lock);
		up_read(&mapping->invalidate_lock);
		return ENODEV;
	}
	if (shared_writable) {
		error = mapping_map_writable(mapping);
		if (error != 0) {
			rw_exit(&registry->lock);
			up_read(&mapping->invalidate_lock);
			return -error;
		}
	}
	entry->mapping = mapping;
	entry->map = map;
	entry->start = start;
	entry->end = end;
	entry->offset = offset;
	entry->protection = protection;
	entry->max_protection = maximum;
	entry->generation = 1;
	entry->shared_writable = shared_writable;
	entry->active = false;
	entry->registered = true;
	TAILQ_INSERT_TAIL(&registry->entries, entry, link);
	if (__predict_false(registry->count == ULONG_MAX))
		panic("Linux VMA registry count exhausted");
	registry->count++;
	rw_exit(&registry->lock);
	up_read(&mapping->invalidate_lock);
	return 0;
}

void
linux_mapping_clone_register(struct linux_native_mapping *parent,
    struct linux_native_mapping *entry, struct vm_map *map,
    vaddr_t start, vaddr_t end, voff_t offset, vm_prot_t protection,
    vm_prot_t maximum)
{
	struct linux_address_space *mapping = parent->mapping;
	struct linux_mapping_registry *registry = mapping->netbsd_mappings;
	int error;

	KASSERT(map != NULL && entry->mapping == NULL &&
	    linux_mapping_interval(start, end, offset, protection, maximum));
	rw_enter(&registry->lock, RW_WRITER);
	KASSERT(parent->registered && registry->count != 0 && !registry->dying);
	if (parent->shared_writable) {
		error = mapping_map_writable(mapping);
		if (__predict_false(error != 0))
			panic("Linux writable parent VMA clone denied");
	}
	entry->mapping = mapping;
	entry->map = map;
	entry->start = start;
	entry->end = end;
	entry->offset = offset;
	entry->protection = protection;
	entry->max_protection = maximum;
	entry->generation = 1;
	entry->shared_writable = parent->shared_writable;
	entry->registered = true;
	entry->active = false;
	TAILQ_INSERT_TAIL(&registry->entries, entry, link);
	if (__predict_false(registry->count == ULONG_MAX))
		panic("Linux VMA registry count exhausted");
	registry->count++;
	rw_exit(&registry->lock);
}

void
linux_mapping_activate(struct linux_native_mapping *entry)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;

	rw_enter(&registry->lock, RW_WRITER);
	KASSERT(entry->registered && !entry->active && !registry->dying);
	linux_mapping_advance(entry);
	entry->active = true;
	rw_exit(&registry->lock);
}

void
linux_mapping_update(struct linux_native_mapping *entry, vaddr_t start,
    vaddr_t end, voff_t offset, vm_prot_t protection, vm_prot_t maximum,
    bool shared_writable)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;

	KASSERT(linux_mapping_interval(start, end, offset, protection, maximum));
	rw_enter(&registry->lock, RW_WRITER);
	KASSERT(entry->registered && !registry->dying);
	if (__predict_false((maximum & ~entry->max_protection) != 0))
		panic("Linux VMA update increased its native maximum protection");
	/* mprotect can reduce the maximum, never grant a new maximum. */
	KASSERT(!shared_writable || entry->shared_writable);
	if (entry->shared_writable && !shared_writable)
		mapping_unmap_writable(entry->mapping);
	entry->shared_writable = shared_writable;
	linux_mapping_advance(entry);
	entry->start = start;
	entry->end = end;
	entry->offset = offset;
	entry->protection = protection;
	entry->max_protection = maximum;
	rw_exit(&registry->lock);
}

void
linux_mapping_deactivate(struct linux_native_mapping *entry)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;

	rw_enter(&registry->lock, RW_WRITER);
	KASSERT(entry->registered);
	if (entry->active) {
		linux_mapping_advance(entry);
		entry->active = false;
	}
	rw_exit(&registry->lock);
}

void
linux_mapping_unregister(struct linux_native_mapping *entry)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;

	rw_enter(&registry->lock, RW_WRITER);
	KASSERT(entry->registered && !entry->active && registry->count != 0);
	TAILQ_REMOVE(&registry->entries, entry, link);
	registry->count--;
	entry->registered = false;
	if (entry->shared_writable)
		mapping_unmap_writable(entry->mapping);
	/* The VMA/file owner keeps this immutable mapping identity alive until
	 * all fault references drain.  A late generation check can now observe
	 * !registered safely instead of dereferencing a cleared pointer.
	 */
	rw_exit(&registry->lock);
}

bool
linux_mapping_snapshot(struct linux_native_mapping *entry,
    struct linux_mapping_snapshot *snapshot)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;
	bool active;

	rw_enter(&registry->lock, RW_READER);
	active = entry->registered && entry->active;
	if (active) {
		snapshot->map = entry->map;
		snapshot->start = entry->start;
		snapshot->end = entry->end;
		snapshot->offset = entry->offset;
		snapshot->protection = entry->protection;
		snapshot->max_protection = entry->max_protection;
		snapshot->generation = entry->generation;
	}
	rw_exit(&registry->lock);
	return active;
}

int
linux_mapping_enter_pfn_range(struct linux_native_mapping *entry,
    uint64_t generation, vaddr_t address, paddr_t physical, vsize_t length,
    vm_prot_t protection, unsigned int cache)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;
	vaddr_t cursor;
	int error = 0;

	if (length == 0 || ((address | physical | length) & (PAGE_SIZE - 1)) ||
	    !linux_mapping_physical_range(physical, length) ||
	    (cache != PMAP_WRITE_BACK && cache != PMAP_WRITE_COMBINE &&
	    cache != PMAP_NOCACHE && cache != PMAP_NOCACHE_OVR))
		return EINVAL;
	rw_enter(&registry->lock, RW_READER);
	if (!entry->registered || !entry->active ||
	    entry->generation != generation) {
		error = ERESTART;
		goto out;
	}
	if (address < entry->start || address >= entry->end ||
	    length > entry->end - address ||
	    (protection & entry->protection) != protection) {
		error = EACCES;
		goto out;
	}
	for (cursor = address; cursor < address + length; cursor += PAGE_SIZE) {
		error = pmap_enter(vm_map_pmap(entry->map), cursor, physical,
		    protection, PMAP_CANFAIL | protection | cache);
		if (error != 0) {
			/* As in Linux remap_pfn_range, a partial mapping must not
			 * survive an error that can release its physical backing.
			 */
			pmap_remove(vm_map_pmap(entry->map), address, cursor);
			break;
		}
		physical += PAGE_SIZE;
	}
	pmap_update(vm_map_pmap(entry->map));
out:
	rw_exit(&registry->lock);
	return error;
}

bool
linux_mapping_extract(struct linux_native_mapping *entry,
    uint64_t generation, vaddr_t address, paddr_t *physical)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;
	bool present;

	rw_enter(&registry->lock, RW_READER);
	present = entry->registered && entry->active &&
	    entry->generation == generation && address >= entry->start &&
	    address < entry->end &&
	    pmap_extract(vm_map_pmap(entry->map), address, physical);
	rw_exit(&registry->lock);
	return present;
}

int
mapping_mapped(const struct linux_address_space *mapping)
{
	struct linux_mapping_registry *registry = mapping->netbsd_mappings;
	bool mapped;

	rw_enter(&registry->lock, RW_READER);
	mapped = registry->count != 0;
	rw_exit(&registry->lock);
	return mapped;
}

void
linux_mapping_zap(struct linux_native_mapping *entry, vaddr_t start,
    vsize_t length)
{
	struct linux_mapping_registry *registry = entry->mapping->netbsd_mappings;

	KASSERT(length != 0 && ((start | length) & (PAGE_SIZE - 1)) == 0);
	rw_enter(&registry->lock, RW_WRITER);
	KASSERT(entry->registered && start >= entry->start &&
	    start <= entry->end && length <= entry->end - start);
	linux_mapping_advance(entry);
	pmap_remove(vm_map_pmap(entry->map), start, start + length);
	pmap_update(vm_map_pmap(entry->map));
	rw_exit(&registry->lock);
}

void
unmap_mapping_pages(struct linux_address_space *mapping,
    linux_pgoff_t first, linux_pgoff_t count, bool even_cows)
{
	struct linux_mapping_registry *registry = mapping->netbsd_mappings;
	struct linux_native_mapping *entry;
	unsigned long last = first + count - 1;

	if (last < first)
		last = ULONG_MAX;
	rw_enter(&registry->lock, RW_WRITER);
	TAILQ_FOREACH(entry, &registry->entries, link) {
		unsigned long entry_first = entry->offset >> PAGE_SHIFT;
		unsigned long entry_count = (entry->end - entry->start) >> PAGE_SHIFT;
		unsigned long entry_last = entry_first + entry_count - 1;
		unsigned long low, high;
		vaddr_t start, end;

		if (!entry->active || entry_last < first || entry_first > last)
			continue;
		/* Native COW overlays are dealt with by the map-entry bridge;
		 * this registry installs only the object's own device PTEs.
		 * A separate COW page is never represented by these producers.
		 */
		(void)even_cows;
		low = MAX(first, entry_first);
		high = MIN(last, entry_last);
		start = entry->start + ((low - entry_first) << PAGE_SHIFT);
		end = entry->start + ((high - entry_first + 1) << PAGE_SHIFT);
		linux_mapping_advance(entry);
		pmap_remove(vm_map_pmap(entry->map), start, end);
		pmap_update(vm_map_pmap(entry->map));
	}
	rw_exit(&registry->lock);
}

void
unmap_mapping_range(struct linux_address_space *mapping,
    loff_t begin, loff_t length, int even_cows)
{
	unsigned long first = (unsigned long long)begin >> PAGE_SHIFT;
	unsigned long count;
	unsigned long long bytes = (unsigned long long)length;

	/* Match the frozen byte-range conversion without signed overflow. */
	if (length == 0 || bytes > (unsigned long long)-1 - (PAGE_SIZE - 1))
		count = 0;
	else
		count = (bytes + PAGE_SIZE - 1) >> PAGE_SHIFT;
	unmap_mapping_pages(mapping, first, count, even_cows != 0);
}
