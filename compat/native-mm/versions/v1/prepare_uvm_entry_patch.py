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
    "sys/uvm/uvm_pager.h": "89d472b83a9249cce27301500ffc1d313f2454c7ad0375abe573a19584d481f4",
    "sys/uvm/uvm_map.h": "a7caf1e149874521e7fbc09483ad17d8ae72fda08b9b366a35c84f3f25c92a3b",
    "sys/uvm/uvm_map.c": "4f87e2d28da17fbce3ccada6bd969ec7d1f39a79076df334f7b09014ab4a684b",
    "sys/uvm/uvm_mmap.c": "c1b1c3e16f12a9a30b777eba3f08dfec08f61d3d10c384569c5d67317bc7733d",
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
    return once(text,
        "\tvoid\t(*pgo_markdirty)(struct uvm_object *);\n",
        "\tvoid\t(*pgo_markdirty)(struct uvm_object *);\n\n"
        "\t/* Optional per-map-entry ownership, separate from object refs.\n"
        "\t * prepare runs with the actual selected range before publication;\n"
        "\t * failure leaves cleanup to entry_detach after map unlock.\n"
        "\t * copy is infallible and creates a distinct owner for a final\n"
        "\t * fork/split/extract interval.  update/link/unlink run with the\n"
        "\t * native map write locked.  unlink precedes PTE removal and may\n"
        "\t * also be called again before tree removal (idempotent).\n"
        "\t * detach runs with maps unlocked and clears uobj_private.\n"
        "\t */\n"
        "\tint\t(*pgo_entry_prepare)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_copy)(struct vm_map *,\n"
        "\t\t    const struct vm_map_entry *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_update)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_link)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_unlink)(struct vm_map *, struct vm_map_entry *);\n"
        "\tvoid\t(*pgo_entry_detach)(struct vm_map_entry *);\n")


def map_header(text):
    return once(text,
        "\tstruct vm_aref\t\taref;\t\t/* anonymous overlay */\n",
        "\tstruct vm_aref\t\taref;\t\t/* anonymous overlay */\n"
        "\tvoid\t\t\t*uobj_private; /* per-entry pager owner */\n")


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
        "\tme->uobj_private = NULL;\n")
    text = once(text, "\tpool_cache_put(&uvm_map_entry_cache, me);\n",
        "\tKASSERT(me->uobj_private == NULL);\n"
        "\tpool_cache_put(&uvm_map_entry_cache, me);\n")
    text = once(text, "\tmemcpy(dst, src, sizeof(*dst));\n\tdst->flags = 0;\n",
        "\tmemcpy(dst, src, sizeof(*dst));\n\tdst->flags = 0;\n"
        "\t/* A copied pointer is not a second VMA owner. */\n"
        "\tdst->uobj_private = NULL;\n")
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
    text = once(text, "\targs->uma_flags = flags;\n",
        "\tif (uobj != NULL && uobj->pgops != NULL &&\n"
        "\t    uobj->pgops->pgo_entry_prepare != NULL)\n"
        "\t\tflags |= UVM_FLAG_NOMERGE;\n"
        "\targs->uma_flags = flags;\n")
    text = once(text, "\t\tuvm_map_entry_link(map, prev_entry, new_entry);\n",
        "\t\tif (uobj != NULL && uobj->pgops != NULL &&\n"
        "\t\t    uobj->pgops->pgo_entry_prepare != NULL) {\n"
        "\t\t\terror = (*uobj->pgops->pgo_entry_prepare)(map, new_entry);\n"
        "\t\t\tif (error != 0)\n\t\t\t\tgoto done;\n"
        "\t\t\t/* Native descriptor/PaX maxima remain authoritative. */\n"
        "\t\t\tnew_entry->max_protection &= maxprot;\n"
        "\t\t\tif (new_entry->protection != prot ||\n"
        "\t\t\t    (prot & new_entry->max_protection) != prot) {\n"
        "\t\t\t\terror = EACCES;\n\t\t\t\tgoto done;\n\t\t\t}\n"
        "\t\t}\n"
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
        "\t\tuvm_entry_pager_copy(new_map, old_entry, new_entry);\n\n"
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


def mmap_source(text):
    # sys_mmap owns a successful fo_mmap object until the consuming uvm_mmap.
    text = once(text,
        "\tstruct file *fp = NULL;\n\tstruct uvm_object *uobj;\n",
        "\tstruct file *fp = NULL;\n\tstruct uvm_object *uobj = NULL;\n"
        "\tbool uobj_owned = false;\n")
    text = once(text, "\t\tif (uobj == NULL) {\n",
        "\t\tuobj_owned = (uobj != NULL);\n"
        "\t\tif (uobj == NULL) {\n")
    text = once(text,
        "\terror = uvm_mmap(&p->p_vmspace->vm_map, &addr, size, prot, maxprot,\n",
        "\tuobj_owned = false; /* uvm_mmap consumes the original on every exit */\n"
        "\terror = uvm_mmap(&p->p_vmspace->vm_map, &addr, size, prot, maxprot,\n")
    text = once(text, " out:\n\tif (fp != NULL)\n",
        " out:\n\tif (uobj_owned)\n"
        "\t\t(*uobj->pgops->pgo_detach)(uobj);\n"
        "\tif (fp != NULL)\n")
    start = text.index("static int\nuvm_mmap(struct vm_map *map,")
    call = text.index("\terror = uvm_map(map, addr, size, uobj,", start)
    prefix = text[start:call]
    for value in ("0", "EINVAL", "ENOMEM"):
        prefix = prefix.replace("return " + value + ";",
            "{ error = " + value + "; goto drop_object; }")
    text = text[:start] + prefix + text[call:]
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
    return text


def derive(root, helper):
    result = {}
    transforms = {"sys/uvm/uvm_pager.h": pager,
        "sys/uvm/uvm_map.h": map_header,
        "sys/uvm/uvm_map.c": lambda text: map_source(text, helper),
        "sys/uvm/uvm_mmap.c": mmap_source}
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
    state = {"netbsd_pin": PIN,
        "files": {relative: {"before_sha256": sha(before),
            "after_sha256": sha(after)}
            for relative, (before, after) in files.items()},
        "helper_sha256": sha(helper.encode("utf-8")),
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
