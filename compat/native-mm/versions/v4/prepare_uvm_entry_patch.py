#!/usr/bin/env python3
"""Derive per-entry pager ownership and mmap reference cleanup from NetBSD pin.

Produces reviewed source patches only.  No compiler, installation, boot or
physical mapping acceptance is performed by this preparation tool.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
EXPECTED = {
    "sys/uvm/uvm_extern.h": "14d6eb1c13d7b6e9f182d8c5043a719df8152858b2b3991120114ccd7867a5bb",
    "sys/uvm/uvm_pager.h": "89d472b83a9249cce27301500ffc1d313f2454c7ad0375abe573a19584d481f4",
    "sys/uvm/uvm_map.h": "a7caf1e149874521e7fbc09483ad17d8ae72fda08b9b366a35c84f3f25c92a3b",
    "sys/uvm/uvm_map.c": "4f87e2d28da17fbce3ccada6bd969ec7d1f39a79076df334f7b09014ab4a684b",
    "sys/uvm/uvm_mmap.c": "c1b1c3e16f12a9a30b777eba3f08dfec08f61d3d10c384569c5d67317bc7733d",
    "sys/uvm/uvm_fault.h": "bb7266cd2178412241f66462b04192afba9ab92daea9f5b7a0f8a9903ceb06b4",
    "sys/uvm/uvm_fault_i.h": "666c14b43342fb469f77a9a597598a1d01522d888d3cd008a3ef27617daaa22b",
    "sys/uvm/uvm_fault.c": "712ff2464d1a749b163a5563b772b88cf9d7b3f993807437d7a81512a0381c22",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("pinned native source anchor changed: " + old[:100])
    return text.replace(old, new, 1)


def pager(text):
    text = once(text, "struct uvm_object;\n", "struct uvm_object;\n"
        "struct vm_map;\nstruct vm_map_entry;\n")
    text = once(text, "struct uvm_pagerops {\n",
        "struct uvm_pagerops;\n"
        "/* One original file/internal mmap call, independent of object class.\n"
        " * The request survives all address-hint attempts.  Its data owns\n"
        " * preparation references; finish releases them exactly once.\n"
        " * Entry prepare sees it through uobj_mmap_request only during the\n"
        " * call and publishes an independently owned uobj_private VMA. */\n"
        "struct uvm_mmap_request {\n"
        "\tconst struct uvm_pagerops *entry_ops;\n\tvoid *data;\n"
        "\tvoid (*finish)(struct uvm_mmap_request *);\n};\n\n"
        "struct uvm_pagerops {\n")
    return once(text,
        "\tvoid\t(*pgo_markdirty)(struct uvm_object *);\n",
        "\tvoid\t(*pgo_markdirty)(struct uvm_object *);\n\n"
        "\t/* Optional per-map-entry ownership, separate from object refs.\n"
        "\t * prepare runs with the actual selected range before publication;\n"
        "\t * failure leaves cleanup to entry_detach after map unlock.\n"
        "\t * copy is infallible and creates a distinct owner for a final\n"
        "\t * fork/split/extract interval.  update/link/unlink run with the\n"
        "\t * native map write locked, or on an exclusively owned unpublished\n"
        "\t * child map during fork. Copy may prepare an inactive extraction\n"
        "\t * owner before the destination map is locked. Unlink precedes PTE\n"
        "\t * removal and may\n"
        "\t * also be called again before tree removal (idempotent).\n"
        "\t * detach runs with maps unlocked and clears uobj_private.\n"
        "\t */\n"
        "\tint\t(*pgo_entry_prepare)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_copy)(struct vm_map *,\n"
        "\t\t    const struct vm_map_entry *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_update)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_link)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_unlink)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_detach)(struct vm_map_entry *);\n"
        "\t/* Optional fault interval guard, before amap/object lookup.\n"
        "\t * enter runs map-read-locked, before any amap/object lock; an\n"
        "\t * error owns nothing. leave precedes EVERY map unlock. A\n"
        "\t * successful Native relock re-enters and revalidates before\n"
        "\t * using cached pages, including private COW overlays. No owner\n"
        "\t * pointer is dereferenced while Native maps are unlocked.\n"
        "\t * Managed entries use only their checked center page. */\n"
        "\tint\t(*pgo_entry_fault_enter)(struct vm_map *,\n"
        "\t\t    struct vm_map_entry *, vaddr_t, vm_prot_t, bool);\n"
        "\tvoid\t(*pgo_entry_fault_leave)(struct vm_map_entry *);\n"
        "\t/* Complete one original mmap transaction after all hint retries.\n"
        "\t * The caller keeps an extra object reference until this returns.\n"
        "\t * May drop preparation-only file/code references; must not fail. */\n"
        "\tvoid\t(*pgo_mmap_finish)(struct uvm_object *);\n")


def map_extern(text):
    text = once(text,
        "int\t\t\tuvm_map(struct vm_map *, vaddr_t *, vsize_t,\n",
        "struct uvm_mmap_request;\n"
        "int\t\t\tuvm_map_request(struct vm_map *, vaddr_t *, vsize_t,\n"
        "\t\t\t    struct uvm_object *, voff_t, vsize_t, uvm_flag_t,\n"
        "\t\t\t    struct uvm_mmap_request *);\n"
        "int\t\t\tuvm_map(struct vm_map *, vaddr_t *, vsize_t,\n")
    return once(text,
        "int\t\t\tuvm_mmap_anon(struct proc *, void **, size_t);\n",
        "int\t\t\tuvm_mmap_anon(struct proc *, void **, size_t);\n"
        "int\t\t\tuvm_mmap_object(struct proc *, vaddr_t *, vsize_t,\n"
        "\t\t\t    vm_prot_t, vm_prot_t, int, int, struct uvm_object *,\n"
        "\t\t\t    voff_t, struct uvm_mmap_request *);\n")


def map_header(text):
    text = once(text, "struct vm_map_entry {\n",
        "struct uvm_pagerops;\nstruct uvm_mmap_request;\n"
        "struct vm_map_entry {\n")
    text = once(text, "\tvoff_t uma_uoffset;\n",
        "\tvoff_t uma_uoffset;\n"
        "\tstruct uvm_mmap_request *uma_request;\n")
    return once(text,
        "\tstruct vm_aref\t\taref;\t\t/* anonymous overlay */\n",
        "\tstruct vm_aref\t\taref;\t\t/* anonymous overlay */\n"
        "\tvoid\t\t\t*uobj_private; /* per-entry pager owner */\n"
        "\tconst struct uvm_pagerops *uobj_entry_ops; /* independent of pgops */\n"
        "\tstruct uvm_mmap_request *uobj_mmap_request; /* prepare-only borrow */\n")


def map_source(text, helper):
    text = once(text, "#include <uvm/uvm_readahead.h>\n",
        "#include <uvm/uvm_readahead.h>\n\n" + helper + "\n")
    text = once(text, "\tuvm_rb_insert((map), (entry)); \\\n",
        "\tuvm_rb_insert((map), (entry)); \\\n"
        "\tuvm_entry_pager_link((map), (entry)); \\\n")
    text = once(text, "\t(map)->nentries--; \\\n",
        "\tuvm_entry_pager_unlink((map), (entry)); \\\n"
        "\t(map)->nentries--; \\\n")
    text = once(text, "\tme->flags = 0;\n",
        "\tme->flags = 0;\n\tme->etype = 0;\n"
        "\tme->object.uvm_obj = NULL;\n\tme->aref.ar_amap = NULL;\n"
        "\tme->uobj_private = NULL;\n\tme->uobj_entry_ops = NULL;\n"
        "\tme->uobj_mmap_request = NULL;\n")
    text = once(text, "\tpool_cache_put(&uvm_map_entry_cache, me);\n",
        "\tKASSERT(me->uobj_private == NULL);\n"
        "\tKASSERT(me->uobj_mmap_request == NULL);\n"
        "\tpool_cache_put(&uvm_map_entry_cache, me);\n")
    text = once(text, "\tmemcpy(dst, src, sizeof(*dst));\n\tdst->flags = 0;\n",
        "\tmemcpy(dst, src, sizeof(*dst));\n\tdst->flags = 0;\n"
        "\t/* A copied pointer is not a second VMA owner. */\n"
        "\tdst->uobj_private = NULL;\n\tdst->uobj_mmap_request = NULL;\n")
    text = once(text, "\tuvm_mapent_splitadj(new_entry, entry, start);\n",
        "\tuvm_mapent_splitadj(new_entry, entry, start);\n"
        "\tuvm_entry_pager_copy(map, entry, new_entry);\n")
    text = once(text, "\tuvm_map_entry_link(map, entry->prev, new_entry);\n",
        "\tuvm_map_entry_link(map, entry->prev, new_entry);\n"
        "\t/* Keep the old registry interval covering both halves until\n"
        "\t * the new half is active; revocation must never see a gap. */\n"
        "\tuvm_entry_pager_update(map, entry);\n")
    text = once(text, "\tuvm_mapent_splitadj(entry, new_entry, end);\n",
        "\tuvm_mapent_splitadj(entry, new_entry, end);\n"
        "\tuvm_entry_pager_copy(map, entry, new_entry);\n")
    text = once(text, "\tuvm_map_entry_link(map, entry, new_entry);\n",
        "\tuvm_map_entry_link(map, entry, new_entry);\n"
        "\tuvm_entry_pager_update(map, entry);\n")
    # Optional entry ownership cannot participate in coalescing.
    original_header = (
        "int\nuvm_map(struct vm_map *map, vaddr_t *startp /* IN/OUT */, vsize_t size,\n"
        "    struct uvm_object *uobj, voff_t uoffset, vsize_t align, uvm_flag_t flags)\n{")
    text = once(text, original_header, original_header + (
        "\n\treturn uvm_map_request(map, startp, size, uobj, uoffset, align,\n"
        "\t    flags, NULL);\n}\n\nint\n"
        "uvm_map_request(struct vm_map *map, vaddr_t *startp, vsize_t size,\n"
        "    struct uvm_object *uobj, voff_t uoffset, vsize_t align, uvm_flag_t flags,\n"
        "    struct uvm_mmap_request *request)\n{"))
    text = once(text, "\tKASSERT((size & PAGE_MASK) == 0);\n",
        "\tif (request != NULL) {\n"
        "\t\tif (request->entry_ops == NULL ||\n"
        "\t\t    request->entry_ops->pgo_entry_prepare == NULL ||\n"
        "\t\t    request->finish == NULL)\n\t\t\treturn EINVAL;\n"
        "\t\tflags |= UVM_FLAG_NOMERGE;\n\t}\n"
        "\tKASSERT((size & PAGE_MASK) == 0);\n")
    text = once(text, "\tif (!error) {\n\t\terror = uvm_map_enter(map, &args, new_entry);\n",
        "\tif (!error) {\n\t\targs.uma_request = request;\n"
        "\t\terror = uvm_map_enter(map, &args, new_entry);\n")
    text = once(text, "\targs->uma_flags = flags;\n",
        "\tif (uobj != NULL && uobj->pgops != NULL &&\n"
        "\t    uobj->pgops->pgo_entry_prepare != NULL)\n"
        "\t\tflags |= UVM_FLAG_NOMERGE;\n"
        "\targs->uma_request = NULL;\n\targs->uma_flags = flags;\n")
    text = once(text, "\t\tuvm_map_entry_link(map, prev_entry, new_entry);\n",
        "\t\tnew_entry->uobj_entry_ops = args->uma_request != NULL ?\n"
        "\t\t    args->uma_request->entry_ops : NULL;\n"
        "\t\tnew_entry->uobj_mmap_request = args->uma_request;\n"
        "\t\tconst struct uvm_pagerops *entry_ops = uvm_entry_pager(new_entry);\n"
        "\t\tif (entry_ops != NULL && entry_ops->pgo_entry_prepare != NULL) {\n"
        "\t\t\terror = (*entry_ops->pgo_entry_prepare)(map, new_entry);\n"
        "\t\t\tnew_entry->uobj_mmap_request = NULL;\n"
        "\t\t\tif (error != 0)\n\t\t\t\tgoto done;\n"
        "\t\t\t/* Native descriptor/PaX maxima remain authoritative. */\n"
        "\t\t\tnew_entry->max_protection &= maxprot;\n"
        "\t\t\tif (new_entry->protection != prot ||\n"
        "\t\t\t    (prot & new_entry->max_protection) != prot) {\n"
        "\t\t\t\terror = EACCES;\n\t\t\t\tgoto done;\n\t\t\t}\n"
        "\t\t}\n"
        "\t\tnew_entry->uobj_mmap_request = NULL;\n"
        "\t\tuvm_map_entry_link(map, prev_entry, new_entry);\n")
    text = once(text, "done:\n\tvm_map_unlock(map);\n",
        "done:\n\tif (error != 0 && new_entry != NULL)\n"
        "\t\tuvm_entry_pager_abort(map, new_entry);\n"
        "\tvm_map_unlock(map);\n")
    text = once(text, "\tif (new_entry) {\n\t\tuvm_mapent_free(new_entry);\n\t}\n",
        "\tif (new_entry) {\n"
        "\t\tuvm_entry_pager_detach(new_entry);\n"
        "\t\tif (new_entry->aref.ar_amap != NULL)\n"
        "\t\t\tuvm_map_unreference_amap(new_entry, 0);\n"
        "\t\tuvm_mapent_free(new_entry);\n\t}\n")
    # Deactivate before any physical removal, rather than only at unlink.
    text = once(text, "\t\tlen = entry->end - entry->start;\n",
        "\t\tlen = entry->end - entry->start;\n"
        "\t\tuvm_entry_pager_unlink(map, entry);\n")
    text = once(text, "\t\tif (first_entry->aref.ar_amap)\n",
        "\t\tuvm_entry_pager_detach(first_entry);\n"
        "\t\tif (first_entry->aref.ar_amap)\n")
    # Map replacement links a prepared extraction chain without using link().
    text = once(text, "\t\t\t\tuvm_rb_insert(map, tmp);\n",
        "\t\t\t\tuvm_rb_insert(map, tmp);\n"
        "\t\t\t\tuvm_entry_pager_link(map, tmp);\n")
    text = once(text, "\t\t/* now link it on the chain */\n",
        "\t\tnewentry->uobj_entry_ops = entry->uobj_entry_ops;\n"
        "\t\tuvm_entry_pager_copy(dstmap, entry, newentry);\n\n"
        "\t\t/* now link it on the chain */\n")
    text = once(text, "\t\t\tif (flags & UVM_EXTRACT_REMOVE) {\n",
        "\t\t\tif (flags & UVM_EXTRACT_REMOVE) {\n"
        "\t\t\t\tuvm_entry_pager_unlink(srcmap, entry);\n")
    text = once(text, "\t\telse\n\t\t\tcurrent->protection = new_prot;\n",
        "\t\telse\n\t\t\tcurrent->protection = new_prot;\n"
        "\t\tuvm_entry_pager_update(map, current);\n")
    text = once(text,
        "uvm_mapent_clone(struct vm_map *new_map, struct vm_map_entry *old_entry,\n"
        "    int flags)\n",
        "uvm_mapent_clone(struct vm_map *new_map, struct vm_map_entry *old_entry,\n"
        "    int flags, bool copy_pager)\n")
    text = once(text, "\t/* insert entry at end of new_map's entry list */\n",
        "\tif (copy_pager)\n"
        "\t\tuvm_entry_pager_copy(new_map, old_entry, new_entry);\n"
        "\telse\n\t\tnew_entry->uobj_entry_ops = NULL;\n\n"
        "\t/* insert entry at end of new_map's entry list */\n")
    text = once(text,
        "uvm_mapent_clone(new_map, old_entry, AMAP_SHARED)",
        "uvm_mapent_clone(new_map, old_entry, AMAP_SHARED, true)")
    anchor = "uvm_mapent_clone(new_map, old_entry, 0)"
    if text.count(anchor) != 2:
        raise ValueError("pinned fork-copy/fork-zero clone call count changed")
    text = text.replace(anchor,
        "uvm_mapent_clone(new_map, old_entry, 0, true)", 1)
    text = text.replace(anchor,
        "uvm_mapent_clone(new_map, old_entry, 0, false)", 1)
    return text


def mmap_source(text, object_helper):
    text = once(text,
        "    int, int, struct uvm_object *, voff_t, vsize_t);\n",
        "    int, int, struct uvm_object *, voff_t, vsize_t,\n"
        "    struct uvm_mmap_request *);\n")
    text = once(text,
        "    voff_t foff, vsize_t locklimit)\n",
        "    voff_t foff, vsize_t locklimit, struct uvm_mmap_request *request)\n")
    # sys_mmap owns a successful fo_mmap object until the consuming uvm_mmap.
    text = once(text,
        "\tstruct file *fp = NULL;\n\tstruct uvm_object *uobj;\n",
        "\tstruct file *fp = NULL;\n\tstruct uvm_object *uobj = NULL;\n"
        "\tstruct uvm_object *mmap_transaction = NULL;\n"
        "\tstruct uvm_mmap_request *mmap_request = NULL;\n"
        "\tbool uobj_owned = false;\n")
    text = once(text, "\t\tif (fp->f_ops->fo_mmap == NULL) {\n",
        "\t\tif (fp->f_ops->fo_mmap == NULL &&\n"
        "\t\t    fp->f_ops->fo_mmap_prepare == NULL) {\n")
    text = once(text,
        "\t\terror = (*fp->f_ops->fo_mmap)(fp, &pos, size, prot, &flags,\n"
        "\t\t    &advice, &uobj, &maxprot);\n",
        "\t\tif (fp->f_ops->fo_mmap_prepare != NULL)\n"
        "\t\t\terror = (*fp->f_ops->fo_mmap_prepare)(fp, &pos, size,\n"
        "\t\t\t    prot, &flags, &advice, &uobj, &maxprot, &mmap_request);\n"
        "\t\telse\n"
        "\t\t\terror = (*fp->f_ops->fo_mmap)(fp, &pos, size, prot, &flags,\n"
        "\t\t\t    &advice, &uobj, &maxprot);\n")
    text = once(text, "\t\tif (uobj == NULL) {\n",
        "\t\tuobj_owned = (uobj != NULL);\n"
        "\t\tif (uobj != NULL && uobj->pgops->pgo_mmap_finish != NULL) {\n"
        "\t\t\tKASSERT(uobj->pgops->pgo_reference != NULL);\n"
        "\t\t\t(*uobj->pgops->pgo_reference)(uobj);\n"
        "\t\t\tmmap_transaction = uobj;\n\t\t}\n"
        "\t\tif (uobj == NULL) {\n")
    text = once(text,
        "\terror = uvm_mmap(&p->p_vmspace->vm_map, &addr, size, prot, maxprot,\n",
        "\tuobj_owned = false; /* uvm_mmap consumes the original on every exit */\n"
        "\terror = uvm_mmap(&p->p_vmspace->vm_map, &addr, size, prot, maxprot,\n")
    text = once(text, " out:\n\tif (fp != NULL)\n",
        " out:\n\tif (uobj_owned)\n"
        "\t\t(*uobj->pgops->pgo_detach)(uobj);\n"
        "\tif (mmap_transaction != NULL) {\n"
        "\t\t(*mmap_transaction->pgops->pgo_mmap_finish)(mmap_transaction);\n"
        "\t\t(*mmap_transaction->pgops->pgo_detach)(mmap_transaction);\n"
        "\t}\n"
        "\tif (mmap_request != NULL)\n"
        "\t\t(*mmap_request->finish)(mmap_request);\n"
        "\tif (fp != NULL)\n")
    start = text.index("static int\nuvm_mmap(struct vm_map *map,")
    call = text.index("\terror = uvm_map(map, addr, size, uobj,", start)
    prefix = text[start:call]
    for value in ("0", "EINVAL", "ENOMEM"):
        prefix = prefix.replace("return " + value + ";",
            "{ error = " + value + "; goto drop_object; }")
    text = text[:start] + prefix + text[call:]
    text = once(text,
        "\terror = uvm_map(map, addr, size, uobj, foff, align, uvmflag);\n",
        "\terror = uvm_map_request(map, addr, size, uobj, foff, align,\n"
        "\t    uvmflag, request);\n")
    text = once(text,
        "\treturn 0;\n}\n\nvaddr_t\nuvm_default_mapaddr(",
        "\treturn 0;\n\ndrop_object:\n"
        "\tif (uobj != NULL)\n\t\t(*uobj->pgops->pgo_detach)(uobj);\n"
        "\treturn error;\n}\n\nvaddr_t\nuvm_default_mapaddr(")
    text = once(text,
        " * XXX This appears to leak the uobj in various error branches?  Need\n"
        " * to clean up the contract around uobj reference.\n",
        " * Consumes the caller's uobj reference on every exit.  After a\n"
        " * successful uvm_map, ownership belongs to the published map entry.\n")
    text = once(text, "\nvaddr_t\nuvm_default_mapaddr(",
        "\n" + object_helper + "\nvaddr_t\nuvm_default_mapaddr(")
    # The syscall owns its one request across BOTH hint attempts.  Old native
    # kernel callers have no per-call context and retain their NULL fallback.
    start = text.index("sys_mmap(struct lwp *l,")
    end = text.index("/*\n * sys___msync13:", start)
    body = text[start:end]
    old = "p->p_rlimit[RLIMIT_MEMLOCK].rlim_cur);"
    if body.count(old) != 2:
        raise ValueError("pinned sys_mmap hint call count changed")
    body = body.replace(old, "p->p_rlimit[RLIMIT_MEMLOCK].rlim_cur, mmap_request);")
    text = text[:start] + body + text[end:]
    for name, next_name in (("uvm_mmap_dev", "uvm_mmap_anon"),
            ("uvm_mmap_anon", None)):
        start = text.index("\n" + name + "(")
        end = text.index("\n" + next_name + "(", start) if next_name else len(text)
        body = text[start:end]
        if body.count(old) != 1:
            raise ValueError("pinned old native mmap call count changed: " + name)
        body = body.replace(old, "p->p_rlimit[RLIMIT_MEMLOCK].rlim_cur, NULL);")
        text = text[:start] + body + text[end:]
    return text


def fault_header(text):
    return once(text, "\tvsize_t size;\t\t\t/* size of interest */\n",
        "\tvsize_t size;\t\t\t/* size of interest */\n"
        "\t/* Initialized by Native lookup, never borrowed across unlock. */\n"
        "\tbool entry_fault_enabled;\n\tbool entry_fault_held;\n"
        "\tbool entry_fault_wiring;\n\tvm_prot_t entry_fault_access;\n")


def fault_inline(text):
    text = once(text, "void uvmfault_update_stats(struct uvm_faultinfo *);\n",
        "void uvmfault_update_stats(struct uvm_faultinfo *);\n\n"
        "/* The current entry is valid only beneath the actual map lock. */\n"
        "static __inline int\nuvmfault_entry_enter(struct uvm_faultinfo *ufi)\n{\n"
        "\tconst struct uvm_pagerops *ops = ufi->entry->uobj_entry_ops;\n"
        "\tint error;\n\n"
        "\tKASSERT(!ufi->entry_fault_held);\n"
        "\tif (ops == NULL || ops->pgo_entry_fault_enter == NULL)\n"
        "\t\treturn 0;\n"
        "\tKASSERT(ops->pgo_entry_fault_leave != NULL);\n"
        "\terror = (*ops->pgo_entry_fault_enter)(ufi->map, ufi->entry,\n"
        "\t    ufi->orig_rvaddr, ufi->entry_fault_access,\n"
        "\t    ufi->entry_fault_wiring);\n"
        "\tif (error == 0)\n\t\tufi->entry_fault_held = true;\n"
        "\treturn error;\n}\n")
    text = once(text, "#ifndef __HAVE_NO_PMAP_STATS\n",
        "\tif (ufi->entry_fault_held) {\n"
        "\t\tconst struct uvm_pagerops *ops = ufi->entry->uobj_entry_ops;\n"
        "\t\tKASSERT(ops != NULL && ops->pgo_entry_fault_leave != NULL);\n"
        "\t\t(*ops->pgo_entry_fault_leave)(ufi->entry);\n"
        "\t\tufi->entry_fault_held = false;\n\t}\n\n"
        "#ifndef __HAVE_NO_PMAP_STATS\n")
    text = once(text, "\tufi->map = ufi->orig_map;\n",
        "\tufi->entry_fault_enabled = false;\n"
        "\tufi->entry_fault_held = false;\n"
        "\tufi->entry_fault_wiring = false;\n"
        "\tufi->entry_fault_access = VM_PROT_NONE;\n"
        "\tufi->map = ufi->orig_map;\n")
    return once(text, "\tcpu_count(CPU_COUNT_FLTRELCKOK, 1);\n",
        "\t/* Map-version validation made the entry/owner valid again.\n"
        "\t * Backing EOF may have changed without a map-version change. */\n"
        "\tif (ufi->entry_fault_enabled && uvmfault_entry_enter(ufi) != 0) {\n"
        "\t\tuvmfault_unlockmaps(ufi, false);\n\t\treturn false;\n\t}\n"
        "\tcpu_count(CPU_COUNT_FLTRELCKOK, 1);\n")


def fault_source(text):
    start = text.index("static int\nuvm_fault_check(\n")
    body = text[start:]
    body = once(body, "\tint nback, nforw;\n", "\tint nback, nforw, error;\n")
    body = once(body, "\tflt->promote = false;\n",
        "\tflt->promote = false;\n\n"
        "\t/* Check the logical backing BEFORE private amap or resident\n"
        "\t * object lookup. Native COW must not bypass an EOF shrink. */\n"
        "\tufi->entry_fault_enabled = ufi->entry->uobj_entry_ops != NULL &&\n"
        "\t    ufi->entry->uobj_entry_ops->pgo_entry_fault_enter != NULL;\n"
        "\tufi->entry_fault_access = flt->access_type;\n"
        "\tufi->entry_fault_wiring = flt->wire_mapping || flt->wire_paging;\n"
        "\tif (ufi->entry_fault_enabled) {\n"
        "\t\tflt->narrow = true; /* Every installed page was checked. */\n"
        "\t\terror = uvmfault_entry_enter(ufi);\n"
        "\t\tif (error != 0) {\n\t\t\tuvmfault_unlockmaps(ufi, false);\n"
        "\t\t\treturn error;\n\t\t}\n\t}\n")
    return text[:start] + body


def derive(root, helper):
    result = {}
    object_helper = (Path(__file__).resolve().parent /
        "uvm_mmap_object.inc").read_text(encoding="utf-8")
    transforms = {"sys/uvm/uvm_extern.h": map_extern,
        "sys/uvm/uvm_pager.h": pager,
        "sys/uvm/uvm_map.h": map_header,
        "sys/uvm/uvm_map.c": lambda text: map_source(text, helper),
        "sys/uvm/uvm_mmap.c": lambda text: mmap_source(text, object_helper),
        "sys/uvm/uvm_fault.h": fault_header,
        "sys/uvm/uvm_fault_i.h": fault_inline,
        "sys/uvm/uvm_fault.c": fault_source}
    for relative, digest in EXPECTED.items():
        before = (root / relative).read_bytes()
        if sha(before) != digest:
            raise ValueError("pinned native file hash differs: " + relative)
        after = transforms[relative](before.decode("utf-8")).encode("utf-8")
        result[relative] = before, after
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    owner = Path(__file__).resolve().parent
    helper = (owner / "uvm_entry_helpers.inc").read_text(encoding="utf-8")
    files = derive(args.reference, helper)
    patch = "".join("".join(difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        "a/" + relative, "b/" + relative))
        for relative, (before, after) in files.items()).encode("utf-8")
    if not args.output.is_dir():
        parser.error("existing owned source output directory required")
    target = args.output / "uvm_entry_owner.patch"
    contract = args.output / "uvm_entry_owner.json"
    if target.exists() or contract.exists():
        parser.error("preserve existing generated patch and contract")
    state = {"version": 4, "netbsd_pin": PIN,
        "files": {relative: {"before_sha256": sha(before),
            "after_sha256": sha(after)}
            for relative, (before, after) in files.items()},
        "helper_sha256": sha(helper.encode("utf-8")),
        "mmap_object_helper_sha256": sha((owner /
            "uvm_mmap_object.inc").read_bytes()),
        "patch_sha256": sha(patch),
        "acceptance": "Source preparation only. Per-entry provider bodies, "
            "native compilation, lifecycle/fault/revocation tests and full "
            "kernel link remain mandatory."}
    target.write_bytes(patch)
    contract.write_text(json.dumps(state, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("PINNED_UVM_ENTRY_OWNER_PATCH_CREATED")


if __name__ == "__main__":
    main()
