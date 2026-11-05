#!/usr/bin/env python3
"""Prepare native process-MM ownership after the exact entry-owner patch.

No compiler or host operation is performed.  The generated patch adds an
opaque per-vmspace owner and a native exec/publication interlock, with no Linux
type in the UVM core.  MM owners force exec into a fresh native vmspace so
structure-only MM references never silently change process image identity.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

import prepare_uvm_entry_patch as entry

EXTERN_SHA = "757a2219c2f1a285d3e8d36711e08d4a765a5a6f9c7858651706c77f025fcec1"
PRIOR_PATCH_SHA = "88de7a07d12895248023f06cdbea4feced1fbc9a4b5b5a0ae39f6d0525313ea9"
PRIOR_MAP_SHA = "0abe7619762dda588bc24882066d23f25cfff32de4bfabcc70c0aa5fceae1674"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, old, new):
    return entry.once(text, old, new)


def header(text):
    text = once(text, "struct vmspace {\n",
        "struct vmspace;\n"
        "struct uvmspace_runtime_ops {\n"
        "\t/* Native vm_refcnt is already zero; no new users can enter.\n"
        "\t * Called with vm_runtime_lock held, before any native storage\n"
        "\t * is freed.  Clear vm_runtime and vm_runtime_ops on return. */\n"
        "\tvoid (*uro_release)(struct vmspace *);\n"
        "};\n\nstruct vmspace {\n")
    return once(text,
        "\tvolatile int vm_refcnt;\t/* number of references */\n",
        "\tvolatile int vm_refcnt;\t/* number of references */\n"
        "\t/* Runtime identity is not copied by vm_startcopy on fork. */\n"
        "\tkmutex_t vm_runtime_lock;\n"
        "\tunsigned int vm_runtime_execs;\n"
        "\tvoid *vm_runtime;\n"
        "\tconst struct uvmspace_runtime_ops *vm_runtime_ops;\n")


def source(text):
    text = once(text, "\tmemset(vm, 0, sizeof(*vm));\n",
        "\tmemset(vm, 0, sizeof(*vm));\n"
        "\tmutex_init(&vm->vm_runtime_lock, MUTEX_DEFAULT, IPL_NONE);\n")
    start = text.index("void\nuvmspace_exec(")
    end = text.index("\n/*\n * uvmspace_addref:", start)
    body = text[start:end]
    body = once(body, "\tint flags;\n", "\tint flags;\n"
        "\tbool runtime_separate, runtime_switched = false;\n")
    body = once(body, "\tKASSERT(ovm != NULL);\n",
        "\tKASSERT(ovm != NULL);\n"
        "\t/* Publication of a runtime identity and exec's reuse decision\n"
        "\t * share one actual native interlock.  Existing runtime-MM users\n"
        "\t * may keep the old address space just as across Linux exec. */\n"
        "\tmutex_enter(&ovm->vm_runtime_lock);\n"
        "\truntime_separate = ovm->vm_runtime_ops != NULL ||\n"
        "\t    ovm->vm_runtime_execs != 0;\n"
        "\tif (__predict_false(ovm->vm_runtime_execs == UINT_MAX))\n"
        "\t\tpanic(\"vmspace runtime exec counter overflow\");\n"
        "\tovm->vm_runtime_execs++;\n"
        "\tmutex_exit(&ovm->vm_runtime_lock);\n")
    body = once(body, "if (ovm->vm_refcnt == 1 && map->nentries != 0)",
        "if (!runtime_separate && ovm->vm_refcnt == 1 && map->nentries != 0)")
    body = once(body, "if (ovm->vm_refcnt == 1) {",
        "if (!runtime_separate && ovm->vm_refcnt == 1) {")
    body = once(body, "\t\tuvmspace_free(ovm);\n",
        "\t\truntime_switched = true;\n")
    tail = "\t}\n}\n"
    if not body.endswith(tail):
        raise ValueError("pinned native exec function tail changed")
    body = body[:-len(tail)] + "\t}\n" + (
        "\tmutex_enter(&ovm->vm_runtime_lock);\n"
        "\tKASSERT(ovm->vm_runtime_execs != 0);\n"
        "\tovm->vm_runtime_execs--;\n"
        "\tmutex_exit(&ovm->vm_runtime_lock);\n"
        "\tif (runtime_switched)\n\t\tuvmspace_free(ovm);\n}\n")
    text = text[:start] + body + text[end:]
    text = once(text, "\tmap->flags |= VM_MAP_DYING;\n\tflags = pmap_remove_all",
        "\tmap->flags |= VM_MAP_DYING;\n"
        "\tmutex_enter(&vm->vm_runtime_lock);\n"
        "\tKASSERT(vm->vm_runtime_execs == 0);\n"
        "\tif (vm->vm_runtime_ops != NULL) {\n"
        "\t\t(*vm->vm_runtime_ops->uro_release)(vm);\n"
        "\t\tKASSERT(vm->vm_runtime == NULL && vm->vm_runtime_ops == NULL);\n"
        "\t}\n"
        "\tmutex_exit(&vm->vm_runtime_lock);\n"
        "\tflags = pmap_remove_all")
    text = once(text, "\tpmap_destroy(map->pmap);\n\tkmem_free(vm, sizeof(*vm));\n",
        "\tpmap_destroy(map->pmap);\n"
        "\tmutex_destroy(&vm->vm_runtime_lock);\n"
        "\tkmem_free(vm, sizeof(*vm));\n")
    return text


def derive(reference):
    owner = Path(__file__).resolve().parent
    prior_patch = (owner / "uvm_entry_owner.patch").read_bytes()
    if sha(prior_patch) != PRIOR_PATCH_SHA:
        raise ValueError("reviewed native entry patch changed")
    helper = (owner / "uvm_entry_helpers.inc").read_text(encoding="utf-8")
    prior_files = entry.derive(reference, helper)
    prior = prior_files["sys/uvm/uvm_map.c"][1]
    if sha(prior) != PRIOR_MAP_SHA:
        raise ValueError("composed native entry-source SHA256 changed")
    native_header = prior_files["sys/uvm/uvm_extern.h"][1]
    if sha(native_header) != EXTERN_SHA:
        raise ValueError("pinned native vmspace header SHA256 changed")
    return {
        "sys/uvm/uvm_extern.h": (native_header,
            header(native_header.decode("utf-8")).encode("utf-8")),
        "sys/uvm/uvm_map.c": (prior,
            source(prior.decode("utf-8")).encode("utf-8")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = derive(args.reference)
    patch = "".join("".join(difflib.unified_diff(
        old.decode("utf-8").splitlines(keepends=True),
        new.decode("utf-8").splitlines(keepends=True),
        "a/" + rel, "b/" + rel))
        for rel, (old, new) in files.items()).encode("utf-8")
    if not args.output.is_dir():
        parser.error("existing owned output required")
    target = args.output / "uvm_mm_identity.patch"
    contract = args.output / "uvm_mm_identity.json"
    if target.exists() or contract.exists():
        parser.error("preserve existing patch/contract")
    state = {"version": 2, "netbsd_pin": entry.PIN,
        "prior_entry_patch_sha256": PRIOR_PATCH_SHA,
        "files": {rel: {"before_sha256": sha(old), "after_sha256": sha(new)}
            for rel, (old, new) in files.items()},
        "patch_sha256": sha(patch),
        "acceptance": "Native source preparation only. MM owner component, "
            "native kernel compilation, publication/exec/pin race tests, "
            "code-owner rundown and full link remain separate mandatory gates."}
    target.write_bytes(patch)
    contract.write_text(json.dumps(state, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("PINNED_UVM_MM_IDENTITY_PATCH_CREATED")


if __name__ == "__main__":
    main()
