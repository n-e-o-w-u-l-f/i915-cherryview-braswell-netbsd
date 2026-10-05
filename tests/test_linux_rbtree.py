#!/usr/bin/env python3
"""Test the production Linux/native tree adapter on HP, including overlap queries.

Actual native rb_node and container_of definitions are used. Kernel publication
primitives are modelled by C atomics/barriers; the production READ/WRITE_ONCE
and RCU macro bodies are extracted unchanged. Export declarations are omitted
from this userland executable. Concurrency and kernel lifetime are separate gates.
"""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import tempfile
from test_linux_memory_ordering import macro

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
BASE = "sys/external/bsd/drm2/"
HEADERS = ['rbtree.h', 'rbtree_types.h', 'rbtree_augmented.h',
           'interval_tree.h', 'interval_tree_generic.h']

C = r'''
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/tree.h>
#include <linux/rbtree_augmented.h>
#include <linux/interval_tree.h>
_Static_assert(RB_RED == 1 && RB_BLACK == 0, "native sys/tree color encoding");
_Static_assert(LINUX_RB_RED == 0 && LINUX_RB_BLACK == 1, "Linux color encoding");
#define N 127
struct entry { struct interval_tree_node it; int id; bool live; } entries[N];
static unsigned rng = 0x1b9d37;
static unsigned random32(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static int depth(struct rb_node *n, struct rb_node *parent, unsigned long *max, int *count)
{
    if (!n) { *max = 0; return 1; }
    assert(rb_parent(n) == parent);
    struct interval_tree_node *v = rb_entry(n, struct interval_tree_node, rb);
    unsigned long lm, rm;
    int left = depth(n->rb_left, n, &lm, count), right = depth(n->rb_right, n, &rm, count);
    assert(left == right);
    if (rb_is_red(n)) {
        assert(!n->rb_left || rb_is_black(n->rb_left));
        assert(!n->rb_right || rb_is_black(n->rb_right));
    }
    *max = v->last;
    if (n->rb_left && lm > *max) *max = lm;
    if (n->rb_right && rm > *max) *max = rm;
    assert(v->__subtree_last == *max);
    ++*count;
    return left + !!rb_is_black(n);
}
static void verify(struct rb_root_cached *root, int expected)
{
    unsigned long max; int count = 0;
    if (root->rb_root.rb_node) assert(rb_is_black(root->rb_root.rb_node));
    depth(root->rb_root.rb_node, NULL, &max, &count);
    assert(count == expected);
    assert(rb_first_cached(root) == rb_first(&root->rb_root));
    unsigned long previous = 0; int forward = 0, reverse = 0;
    for (struct rb_node *n = rb_first(&root->rb_root); n; n = rb_next(n)) {
        struct interval_tree_node *v = rb_entry(n, struct interval_tree_node, rb);
        assert(!forward || v->start >= previous); previous = v->start; ++forward;
    }
    for (struct rb_node *n = rb_last(&root->rb_root); n; n = rb_prev(n)) ++reverse;
    assert(forward == expected && reverse == expected);
}
static void query(struct rb_root_cached *root, unsigned long start, unsigned long last)
{
    bool seen[N] = { false }; unsigned guard = 0;
    for (struct interval_tree_node *p = interval_tree_iter_first(root, start, last);
         p; p = interval_tree_iter_next(p, start, last)) {
        struct entry *e = container_of(p, struct entry, it);
        assert(e->id >= 0 && e->id < N && !seen[e->id] && e->live);
        assert(p->start <= last && p->last >= start);
        seen[e->id] = true; assert(++guard <= N);
    }
    for (int i = 0; i < N; ++i)
        assert(seen[i] == (entries[i].live && entries[i].it.start <= last && entries[i].it.last >= start));
}
struct plain { int key; struct rb_node node; };
static bool less(struct rb_node *a, const struct rb_node *b)
{ return rb_entry(a, struct plain, node)->key < rb_entry(b, struct plain, node)->key; }
static int cmp(const void *key, const struct rb_node *n)
{ int v = rb_entry(n, struct plain, node)->key; return (*(const int *)key > v) - (*(const int *)key < v); }
static int nodecmp(const struct rb_node *a, const struct rb_node *b)
{ int x=rb_entry(a,struct plain,node)->key, y=rb_entry(b,struct plain,node)->key; return (x>y)-(x<y); }
static void plain_trees(void)
{
    struct plain nodes[33] = {0}, replacement = {.key=0};
    struct rb_root_cached root = RB_ROOT_CACHED;
    for (int i = 0; i < 32; ++i) {
        nodes[i].key = i;
        RB_CLEAR_NODE(&nodes[i].node); assert(RB_EMPTY_NODE(&nodes[i].node));
        rb_add_cached(&nodes[i].node, &root, less);
        assert(!RB_EMPTY_NODE(&nodes[i].node));
    }
    nodes[32].key = 17;
    assert(rb_find_add_cached(&nodes[32].node, &root, nodecmp) == &nodes[17].node);
    for (int i = 0; i < 32; ++i) assert(rb_find(&i, &root.rb_root, cmp) == &nodes[i].node);
    rb_replace_node_cached(&nodes[0].node, &replacement.node, &root);
    assert(rb_first_cached(&root) == &replacement.node);
    assert(rb_parent(&replacement.node) == rb_parent(&nodes[0].node));
    int zero = 0; assert(rb_find_rcu(&zero, &root.rb_root, cmp) == &replacement.node);
    struct plain rcu = {.key=0};
    rb_replace_node_rcu(&replacement.node, &rcu.node, &root.rb_root);
    root.rb_leftmost = &rcu.node;
    assert(rb_find_rcu(&zero, &root.rb_root, cmp) == &rcu.node);
    rb_erase_cached(&rcu.node, &root);
    for (int i = 1; i < 32; ++i) rb_erase_cached(&nodes[i].node, &root);
    assert(RB_EMPTY_ROOT(&root.rb_root) && !rb_first_cached(&root));
}
struct native_entry { int key; struct rb_node node; };
static int native_nodes(void *ctx, const void *a, const void *b)
{ (void)ctx; return (((const struct native_entry *)a)->key > ((const struct native_entry *)b)->key) - (((const struct native_entry *)a)->key < ((const struct native_entry *)b)->key); }
static int native_key(void *ctx, const void *a, const void *b)
{ (void)ctx; return (((const struct native_entry *)a)->key > *(const int *)b) - (((const struct native_entry *)a)->key < *(const int *)b); }
static void native_coexistence(void)
{
    const rb_tree_ops_t ops = {native_nodes, native_key, offsetof(struct native_entry, node), NULL};
    rb_tree_t root; struct native_entry e[16] = {0};
    rb_tree_init(&root, &ops);
    for (int i=15; i>=0; --i) { e[i].key=i; assert(rb_tree_insert_node(&root, &e[i]) == &e[i]); }
    for (int i=0; i<16; ++i) { assert(rb_tree_find_node(&root, &i) == &e[i]); rb_tree_remove_node(&root, &e[i]); }
    assert(RB_TREE_MIN(&root) == NULL);
}
static void spans(void)
{
    struct rb_root_cached root = RB_ROOT_CACHED;
    struct interval_tree_node n[] = {{.start=2,.last=4},{.start=4,.last=8},{.start=9,.last=10},{.start=15,.last=20}};
    const unsigned long starts[]={0,2,11,15,21}, ends[]={1,10,14,20,25};
    const int holes[]={1,0,1,0,1};
    for (int i=0;i<4;++i) interval_tree_insert(&n[i], &root);
    struct interval_tree_span_iter it; int index=0;
    interval_tree_for_each_span(&it, &root, 0, 25) {
        assert(index<5 && it.is_hole==holes[index]);
        assert(it.start_hole==starts[index] && it.last_hole==ends[index]); ++index;
    }
    assert(index==5);
    interval_tree_span_iter_first(&it, &root, 0, 25);
    interval_tree_span_iter_advance(&it, &root, 7);
    assert(it.is_hole==0 && it.start_used==7 && it.last_used==10);
    interval_tree_span_iter_advance(&it, &root, 26); assert(interval_tree_span_iter_done(&it));
    for (int i=0;i<4;++i) interval_tree_remove(&n[i], &root);
}
int main(void)
{
    struct rb_root_cached root = RB_ROOT_CACHED; int order[N];
    for (int i=0;i<N;++i) {
        order[i]=i; entries[i].id=i;
        entries[i].it.start=(unsigned long)((i*37)%97);
        entries[i].it.last=entries[i].it.start+(unsigned long)((i*19)%83);
    }
    entries[0].it.start=0; entries[0].it.last=ULONG_MAX;
    entries[1].it.start=ULONG_MAX; entries[1].it.last=ULONG_MAX;
    entries[2].it.start=0; entries[2].it.last=0;
    for (int i=N-1;i>0;--i) { int j=(int)(random32()%(unsigned)(i+1)), t=order[j]; order[j]=order[i]; order[i]=t; }
    for (int i=0;i<N;++i) { entries[order[i]].live=true; interval_tree_insert(&entries[order[i]].it, &root); verify(&root,i+1); }
    for (unsigned long i=0;i<256;++i) { query(&root,i,i); query(&root,i,i+17); }
    query(&root,ULONG_MAX,ULONG_MAX); query(&root,ULONG_MAX-16,ULONG_MAX);
    bool visited[N]={false}; int post=0;
    for (struct rb_node *n=rb_first_postorder(&root.rb_root); n; n=rb_next_postorder(n)) {
        struct entry *e=container_of(rb_entry(n,struct interval_tree_node,rb),struct entry,it);
        if (n->rb_left) assert(visited[container_of(rb_entry(n->rb_left,struct interval_tree_node,rb),struct entry,it)->id]);
        if (n->rb_right) assert(visited[container_of(rb_entry(n->rb_right,struct interval_tree_node,rb),struct entry,it)->id]);
        assert(!visited[e->id]); visited[e->id]=true; ++post;
    }
    assert(post==N);
    for (int i=N-1;i>=0;--i) {
        int j=(int)(random32()%(unsigned)(i+1)), id=order[j]; order[j]=order[i];
        interval_tree_remove(&entries[id].it,&root); entries[id].live=false; verify(&root,i);
        query(&root,random32()%200,200); query(&root,ULONG_MAX,ULONG_MAX);
    }
    assert(RB_EMPTY_ROOT(&root.rb_root));
    plain_trees(); native_coexistence(); spans();
    puts("LINUX_RBTREE_OK: native coexistence; 127 overlapping/extreme intervals; augmentation, deletion, cached/RCU replacement, postorder and spans");
    return 0;
}
'''

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netbsd-tree', type=Path, required=True)
    p.add_argument('--baseline', action='store_true')
    p.add_argument('--apply-candidate', action='store_true')
    a = p.parse_args()
    if platform.system() != 'NetBSD' or not socket.gethostname().startswith('hp-tpnw121'):
        p.error('compiler-invoking checks are authorized only on HP/NetBSD')
    owner = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='i915-rbtree-') as temporary:
        temp = Path(temporary)
        def frozen(path):
            return subprocess.check_output(['git','-C','/root/netbsd-src-ref','show',PIN+':'+path],text=True)
        if a.apply_candidate:
            for name in ['rbtree.h','interval_tree.h','interval_tree_generic.h']:
                path=temp/(BASE+'include/linux/'+name); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(frozen(BASE+'include/linux/'+name))
            path=temp/(BASE+'linux/files.drmkms_linux'); path.parent.mkdir(parents=True); path.write_text(frozen(BASE+'linux/files.drmkms_linux'))
            patch=owner/'patches/0021-netbsd-linux-augmented-rbtree.patch'
            subprocess.run(['git','-C',str(temp),'apply','--check',str(patch)],check=True)
            subprocess.run(['git','-C',str(temp),'apply',str(patch)],check=True)
            production=temp
        else: production=a.netbsd_tree
        for name in HEADERS:
            path=temp/'linux'/name; path.parent.mkdir(parents=True,exist_ok=True)
            if a.baseline and name in ['rbtree.h','interval_tree.h','interval_tree_generic.h']:
                path.write_text(frozen(BASE+'include/linux/'+name))
            else: path.write_text((production/(BASE+'include/linux/'+name)).read_text())
        for name in ['rbtree.h','container_of.h','tree.h']:
            path=temp/'sys'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(frozen('sys/sys/'+name))
        compiler=frozen('sys/external/bsd/common/include/linux/compiler.h')
        shim='#include <sys/cdefs.h>\n#include <stdbool.h>\n#include <stddef.h>\n#include <string.h>\n#include <sys/atomic.h>\n'
        shim+='#define likely(X) __predict_true(X)\n#define unlikely(X) __predict_false(X)\n'
        shim+='#define atomic_store_release(P,V) __atomic_store_n(P,V,__ATOMIC_RELEASE)\n'
        shim+='#define atomic_load_consume(P) __atomic_load_n(P,__ATOMIC_CONSUME)\n'
        shim+='#define KASSERT(X) assert(X)\n'
        shim+='\n'+macro(compiler,'READ_ONCE')+macro(compiler,'WRITE_ONCE')
        (temp/'linux/compiler.h').write_text('#ifndef TEST_COMPILER_H\n#define TEST_COMPILER_H\n'+shim+'\n#endif\n')
        (temp/'linux/stddef.h').write_text('#include <stddef.h>\n')
        lib=temp/'lib/libkern/libkern.h'; lib.parent.mkdir(parents=True); lib.write_text('#include <stddef.h>\n#include <sys/container_of.h>\n')
        rcu=frozen('sys/external/bsd/common/include/linux/rcupdate.h')
        rcu_macros='\n'.join(x for x in rcu.splitlines() if x.startswith('#define') and any(x.split()[1].startswith(y) for y in ['rcu_assign_pointer','rcu_dereference(P)','rcu_dereference_raw']))
        (temp/'linux/rcupdate.h').write_text('#include <linux/compiler.h>\n'+rcu_macros+'\n')
        (temp/'linux/export.h').write_text('#define EXPORT_SYMBOL(X)\n#define EXPORT_SYMBOL_GPL(X)\n')
        fixture=temp/'fixture.c'; fixture.write_text(C)
        units=[str(fixture)]
        for name in ['linux_rbtree_native.c','linux_interval_tree_native.c']:
            source=temp/name; source.write_bytes((production/(BASE+'linux/'+name)).read_bytes()); units.append(str(source))
        exe=temp/'fixture'
        subprocess.run(['cc','-std=gnu11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
            '-fsanitize=undefined','-fno-sanitize-recover=all','-DCONFIG_INTERVAL_TREE_SPAN_ITER=1',
            '-include','stdbool.h','-include','stddef.h','-I',str(temp),*units,'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)

if __name__ == '__main__': main()
