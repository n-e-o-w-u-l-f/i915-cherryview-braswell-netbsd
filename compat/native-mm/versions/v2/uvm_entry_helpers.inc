/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
/* Optional per-map-entry pager ownership.  No Linux types enter UVM. */
static const struct uvm_pagerops *
uvm_entry_pager(const struct vm_map_entry *entry)
{
	if (!UVM_ET_ISOBJ(entry) || entry->object.uvm_obj == NULL)
		return NULL;
	return entry->object.uvm_obj->pgops;
}

static void
uvm_entry_pager_copy(struct vm_map *map, const struct vm_map_entry *source,
    struct vm_map_entry *entry)
{
	const struct uvm_pagerops *ops = uvm_entry_pager(source);

	KASSERT(entry->uobj_private == NULL);
	if (source->uobj_private != NULL) {
		KASSERT(ops != NULL && ops->pgo_entry_copy != NULL);
		(*ops->pgo_entry_copy)(map, source, entry);
		KASSERT(entry->uobj_private != NULL);
		entry->flags |= UVM_MAP_NOMERGE;
	}
}

static void
uvm_entry_pager_update(struct vm_map *map, struct vm_map_entry *entry)
{
	const struct uvm_pagerops *ops = uvm_entry_pager(entry);

	if (entry->uobj_private != NULL) {
		KASSERT(ops != NULL && ops->pgo_entry_update != NULL);
		(*ops->pgo_entry_update)(map, entry);
	}
}

static void
uvm_entry_pager_link(struct vm_map *map, struct vm_map_entry *entry)
{
	const struct uvm_pagerops *ops = uvm_entry_pager(entry);

	if (entry->uobj_private != NULL) {
		KASSERT(ops != NULL && ops->pgo_entry_link != NULL);
		(*ops->pgo_entry_link)(map, entry);
	}
}

static void
uvm_entry_pager_unlink(struct vm_map *map, struct vm_map_entry *entry)
{
	const struct uvm_pagerops *ops = uvm_entry_pager(entry);

	if (entry->uobj_private != NULL) {
		KASSERT(ops != NULL && ops->pgo_entry_unlink != NULL);
		(*ops->pgo_entry_unlink)(map, entry);
	}
}

static void
uvm_entry_pager_detach(struct vm_map_entry *entry)
{
	const struct uvm_pagerops *ops = uvm_entry_pager(entry);

	if (entry->uobj_private != NULL) {
		KASSERT(ops != NULL && ops->pgo_entry_detach != NULL);
		(*ops->pgo_entry_detach)(entry);
		KASSERT(entry->uobj_private == NULL);
	}
}

static void
uvm_entry_pager_abort(struct vm_map *map, struct vm_map_entry *entry)
{
	if (entry->uobj_private == NULL)
		return;
	/* Preparation owns the reserved range while this map is write locked.
	 * Quiesce producers and revoke even a partially installed range before
	 * unlocking; delayed detach must not remove a later unrelated mapping.
	 */
	uvm_entry_pager_unlink(map, entry);
#ifdef __HAVE_UNLOCKED_PMAP
	uvm_map_lock_entry(entry, RW_WRITER);
#else
	uvm_map_lock_entry(entry, RW_READER);
#endif
	pmap_remove(vm_map_pmap(map), entry->start, entry->end);
	pmap_update(vm_map_pmap(map));
	uvm_map_unlock_entry(entry);
}
