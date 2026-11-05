/* Native object-mapping entry derived from the enclosing NetBSD uvm_mmap.c.
 * The enclosing source's copyright notices and license remain authoritative.
 * Copyright (c) 2026 n-e-o-w-u-l-f (runtime transaction integration).
 */
int
uvm_mmap_object(struct proc *p, vaddr_t *address, vsize_t length,
    vm_prot_t protection, vm_prot_t maximum, int flags, int advice,
    struct uvm_object *object, voff_t offset,
    struct uvm_mmap_request *request)
{
	struct uvm_object *transaction = NULL;
	struct vm_map *map;
	vaddr_t original, fallback = 0;
	bool owned = true, hint = false;
	int error;

	/* Like sys_mmap, consume the supplied object reference on every exit. */
	if (object != NULL && object->pgops->pgo_mmap_finish != NULL) {
		KASSERT(object->pgops->pgo_reference != NULL);
		(*object->pgops->pgo_reference)(object);
		transaction = object;
	}
	if (p != curproc || address == NULL || length == 0 ||
	    (protection & ~VM_PROT_ALL) != 0 ||
	    ((flags & (MAP_SHARED | MAP_PRIVATE)) == (MAP_SHARED | MAP_PRIVATE)) ||
	    ((flags & MAP_ANON) != 0 ? object != NULL : object == NULL) ||
	    (offset & (PAGE_SIZE - 1)) != 0 ||
	    length > __type_max(vsize_t) - PAGE_SIZE + 1) {
		error = EINVAL;
		goto out;
	}
	map = &p->p_vmspace->vm_map;
	length = round_page(length);
	original = *address;
	if (flags & MAP_FIXED) {
		if ((*address & (PAGE_SIZE - 1)) != 0) {
			error = EINVAL;
			goto out;
		}
		error = range_test(map, *address, length, true);
		if (error != 0)
			goto out;
	} else if (*address == 0 || !(flags & MAP_TRYFIXED)) {
		fallback = p->p_emul->e_vm_default_addr(p,
		    (vaddr_t)p->p_vmspace->vm_daddr, length,
		    map->flags & VM_MAP_TOPDOWN);
		if (*address == 0 || !(map->flags & VM_MAP_TOPDOWN))
			*address = MAX(*address, fallback);
		else
			*address = MIN(*address, fallback);
		hint = *address != 0 && *address != fallback;
	}
	maximum = PAX_MPROTECT_MAXPROTECT(curlwp, protection, 0, maximum);
	if ((protection & maximum) != protection) {
		error = EACCES;
		goto out;
	}
	error = PAX_MPROTECT_VALIDATE(curlwp, protection);
	if (error != 0)
		goto out;
	pax_aslr_mmap(curlwp, address, original, flags);
	if (hint && object != NULL)
		(*object->pgops->pgo_reference)(object);
	owned = false;
	error = uvm_mmap(map, address, length, protection, maximum, flags,
	    advice, object, offset, p->p_rlimit[RLIMIT_MEMLOCK].rlim_cur, request);
	if (hint) {
		if (error != 0) {
			*address = fallback;
			pax_aslr_mmap(curlwp, address, original, flags);
			error = uvm_mmap(map, address, length, protection, maximum,
			    flags, advice, object, offset,
			    p->p_rlimit[RLIMIT_MEMLOCK].rlim_cur, request);
		} else if (object != NULL) {
			(*object->pgops->pgo_detach)(object);
		}
	}
out:
	if (owned && object != NULL)
		(*object->pgops->pgo_detach)(object);
	if (transaction != NULL) {
		(*transaction->pgops->pgo_mmap_finish)(transaction);
		(*transaction->pgops->pgo_detach)(transaction);
	}
	if (request != NULL)
		(*request->finish)(request);
	return error;
}
