#!/usr/bin/env python3
"""Port pinned Linux augmented/interval trees to the existing NetBSD rb_node.

Keep NetBSD's node type so native idr/xarray/ww_mutex retain their node layout.
Linux trees use independent Linux rb_root and Linux balancing algorithms. A
node belongs to one backend at a time: native color/position flags must never
be interpreted by the Linux backend. Namespace Linux color constants to keep
sys/tree.h's different color encoding intact in either include order.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
BASE = "sys/external/bsd/drm2/"
SOURCES = {
    "include/linux/rbtree_types.h": "include/linux/rbtree_types.h",
    "include/linux/rbtree.h": "include/linux/rbtree.h",
    "include/linux/rbtree_augmented.h": "include/linux/rbtree_augmented.h",
    "include/linux/interval_tree.h": "include/linux/interval_tree.h",
    "include/linux/interval_tree_generic.h": "include/linux/interval_tree_generic.h",
    "linux/linux_rbtree_native.c": "lib/rbtree.c",
    "linux/linux_interval_tree_native.c": "lib/interval_tree.c",
}

def read(tree, path, absent=False):
    r = subprocess.run(["git", "-C", str(tree), "show", "HEAD:" + path], capture_output=True, text=True)
    if r.returncode and not absent: raise RuntimeError(r.stderr)
    return r.stdout if r.returncode == 0 else ""

def transform(path, source):
    # NetBSD's __always_inline is an attribute only; Linux includes `inline`.
    # Keep the native macro unchanged for declarations in other OS headers.
    source = re.sub(r"\b__always_inline\b", "inline __always_inline", source)
    source = re.sub(r"\b__rb_parent_color\b", "rb_info", source)
    source = re.sub(r"\bRB_RED\b", "LINUX_RB_RED", source)
    source = re.sub(r"\bRB_BLACK\b", "LINUX_RB_BLACK", source)
    source = re.sub(r"\bRB_ROOT\b", "LINUX_RB_ROOT", source)
    if path == "linux/linux_rbtree_native.c":
        # Linux traversal deliberately returns mutable nodes from const input;
        # use the OS's explicit qualifier-removal helper under -Wcast-qual.
        source = re.sub(r"\(struct rb_node \*\)(node|parent)\b", r"__UNCONST(\1)", source)
    if path == "include/linux/rbtree_types.h":
        original = """struct rb_node {
\tunsigned long  rb_info;
\tstruct rb_node *rb_right;
\tstruct rb_node *rb_left;
} __attribute__((aligned(sizeof(long))));
/* The alignment might seem pointless, but allegedly CRIS needs it */"""
        if source.count(original) != 1: raise ValueError("unexpected pinned Linux node layout")
        replacement = """/* NetBSD owns struct rb_node. Only its pointer fields and rb_info storage
 * are reused; Linux and native rb_tree objects have independent backends.
 * Do not pass a Linux tree's node to the native rb_tree API, or vice versa.
 */
#include <sys/rbtree.h>
_Static_assert(sizeof(((struct rb_node *)0)->rb_info) == sizeof(unsigned long),
    "Linux parent/color storage must hold a native pointer");
_Static_assert(__alignof__(struct rb_node) >= 4,
    "Linux parent/color storage needs two low pointer bits");"""
        source = source.replace(original, replacement)
    if path == "include/linux/rbtree.h":
        original = "#include <linux/container_of.h>"
        if source.count(original) != 1: raise ValueError("unexpected Linux container_of input")
        source = source.replace(original, "#include <sys/container_of.h>\n#include <linux/compiler.h>")
    return "\n".join(line.rstrip() for line in source.splitlines()) + "\n"

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--linux-tree", type=Path, required=True)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    for tree, pin in [(a.linux_tree, LINUX_PIN), (a.netbsd_tree, NETBSD_PIN)]:
        head = subprocess.check_output(["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
        if head != pin: p.error("wrong frozen reference revision")
    if a.out.exists(): p.error("preserve existing output")
    changes = []
    for path, linux_path in SOURCES.items():
        target = BASE + path
        old = read(a.netbsd_tree, target, absent=True)
        new = transform(path, read(a.linux_tree, linux_path))
        changes.append("".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/" + target if old else "/dev/null", tofile="b/" + target)))
    target = BASE + "linux/files.drmkms_linux"
    old = read(a.netbsd_tree, target)
    new = old + "\n# Linux balancing and augmentation over native rb_node storage.\n" \
        + "file\texternal/bsd/drm2/linux/linux_rbtree_native.c\tdrmkms_linux\n" \
        + "file\texternal/bsd/drm2/linux/linux_interval_tree_native.c\tdrmkms_linux\n"
    changes.append("".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="a/" + target, tofile="b/" + target)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(changes))

if __name__ == "__main__":
    main()
