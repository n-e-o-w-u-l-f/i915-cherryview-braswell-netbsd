#!/usr/bin/env python3
"""C11 compile of EXACT F03 fd_get_linux_file() patch body under FD stubs.

This is NOT compilation against NetBSD headers, nor a real concurrent FD test.
Only the Git-blob-pinned bridge body is copied to the generated C fixture.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import tempfile
import unittest

PATCH = (Path(__file__).resolve().parents[1]
         / 'patches/candidates/netbsd-11-drm-fileops-bridge-20261025.patch')
PINNED_BLOB = '9c99357d2ee3ce21267ede4e2caed033e0906694'
FLAGS = ('-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined')
MUTANTS = {
    'early_fd_put': ('if (fp->f_ops != NULL && fp->f_ops->fo_linux_file != NULL)\n\t\tlinux = (*fp->f_ops->fo_linux_file)(fp);',
                     'if (fp->f_ops != NULL && fp->f_ops->fo_linux_file != NULL) {\n\t\tfd_putfile(fd);\n\t\tlinux = (*fp->f_ops->fo_linux_file)(fp);\n\t}'),
    'missing_callback': ('linux = (*fp->f_ops->fo_linux_file)(fp);',
                         'linux = NULL;'),
    'missing_fd_put': ('\tfd_putfile(fd);\n\treturn linux;',
                       '\treturn linux;'),
    'duplicate_fd_put': ('\tfd_putfile(fd);\n\treturn linux;',
                         '\tfd_putfile(fd);\n\tfd_putfile(fd);\n\treturn linux;'),
}

STUB_PREFIX = r'''#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "CHECK_FAILED %s\n", #x); abort(); } } while (0)
struct linux_file { unsigned refs; unsigned releases; };
typedef struct file file_t;
struct fileops { struct linux_file *(*fo_linux_file)(file_t *); };
struct file { const struct fileops *f_ops; struct linux_file *linux;
    unsigned pins; bool active, closing, destroyed; };
static file_t current_file;
static unsigned get_calls, put_calls;
static void linux_put(struct linux_file *lf) {
    CHECK(lf->refs > 0);
    if (--lf->refs == 0) lf->releases++;
}
static void fd_finalize(file_t *fp) {
    CHECK(fp->pins == 0 && fp->closing && !fp->destroyed);
    fp->destroyed = true;
    linux_put(fp->linux); /* native file's sole Linux ref */
}
static file_t *fd_getfile(unsigned fd) {
    ++get_calls;
    if (fd != 4 || !current_file.active) return NULL;
    CHECK(!current_file.destroyed);
    current_file.pins++;
    return &current_file;
}
static void fd_putfile(unsigned fd) {
    CHECK(fd == 4 && current_file.pins > 0 && !current_file.destroyed);
    ++put_calls;
    current_file.pins--;
    if (!current_file.pins && current_file.closing)
        fd_finalize(&current_file);
}
static void native_close(void) {
    CHECK(current_file.active && !current_file.closing);
    current_file.active = false;
    current_file.closing = true;
    if (!current_file.pins) fd_finalize(&current_file);
}
static struct linux_file *view(file_t *fp) {
    CHECK(fp->pins > 0 && !fp->destroyed);
    CHECK(fp->linux->refs > 0);
    fp->linux->refs++;
    return fp->linux;
}
static struct linux_file *view_during_close(file_t *fp) {
    CHECK(fp->pins > 0 && !fp->destroyed);
    native_close();
    CHECK(fp->pins > 0 && !fp->destroyed);
    return view(fp);
}
static void reset(struct linux_file *lf, const struct fileops *ops) {
    memset(&current_file, 0, sizeof(current_file));
    memset(lf, 0, sizeof(*lf));
    lf->refs = 1;
    current_file.linux = lf;
    current_file.f_ops = ops;
    current_file.active = true;
    get_calls = put_calls = 0;
}
'''
STUB_SUFFIX = r'''static void run_scenarios(void) {
    void (*pinned_put)(unsigned) = fd_putfile;
    (void)pinned_put; /* also present for the missing_fd_put mutant */
    struct linux_file lf;
    struct linux_file *owned;
    const struct fileops yes = {view};
    const struct fileops closing = {view_during_close};
    const struct fileops unsupported = {NULL};
    reset(&lf, &yes);
    owned = fd_get_linux_file(4);
    CHECK(owned == &lf && owned->refs == 2);
    CHECK(current_file.pins == 0 && get_calls == 1 && put_calls == 1);
    native_close();
    CHECK(current_file.destroyed && lf.refs == 1 && lf.releases == 0);
    linux_put(owned);
    CHECK(lf.refs == 0 && lf.releases == 1);
    CHECK(fd_get_linux_file(4) == NULL);
    CHECK(get_calls == 2 && put_calls == 1);

    reset(&lf, &closing);
    owned = fd_get_linux_file(4);
    CHECK(current_file.destroyed && current_file.pins == 0);
    CHECK(owned == &lf && lf.refs == 1 && lf.releases == 0);
    CHECK(get_calls == 1 && put_calls == 1);
    linux_put(owned);
    CHECK(lf.releases == 1);

    reset(&lf, &unsupported);
    CHECK(fd_get_linux_file(4) == NULL);
    CHECK(current_file.pins == 0 && get_calls == 1 && put_calls == 1);
    native_close();
    CHECK(lf.releases == 1);

    reset(&lf, NULL);
    CHECK(fd_get_linux_file(4) == NULL);
    CHECK(current_file.pins == 0 && get_calls == 1 && put_calls == 1);
    native_close();
    CHECK(lf.releases == 1);

    reset(&lf, &yes);
    CHECK(fd_get_linux_file(5) == NULL);
    CHECK(current_file.pins == 0 && get_calls == 1 && put_calls == 0);
    native_close();
    CHECK(lf.releases == 1);

    puts("F03_ACTUAL_FD_BRIDGE_SOURCE_MODEL_PASS 5_SCENARIOS");
}
int main(void) { run_scenarios(); return 0; }
'''


def no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def exact_patch_body() -> str:
    r = subprocess.run(['git', 'hash-object', str(PATCH)], text=True,
                       capture_output=True, timeout=20, check=True)
    if r.stdout.strip() != PINNED_BLOB:
        raise ValueError('candidate patch blob changed')
    chunks = re.split(r'(?=^diff --git a/)', PATCH.read_text(), flags=re.M)
    entries = [s for s in chunks if s.startswith('diff --git a/sys/kern/kern_descrip.c ')]
    if len(entries) != 1:
        raise ValueError('missing unique kern_descrip patch section')
    additions = ''.join(line[1:] for line in entries[0].splitlines(keepends=True)
                        if line.startswith('+') and not line.startswith('+++'))
    match = re.search(r'struct linux_file \*\nfd_get_linux_file\(unsigned fd\)\n\{\n.*?^\}\n',
                      additions, re.S | re.M)
    if not match:
        raise ValueError('missing exact candidate function body')
    body = match.group()
    for exact in ('fp = fd_getfile(fd);', '(*fp->f_ops->fo_linux_file)(fp);',
                  'fd_putfile(fd);', 'return linux;'):
        if body.count(exact) != 1:
            raise ValueError('source drift: '+exact)
    return body


class F03RealSourceBody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix='f03-exact-fd-source-')
        cls.root = Path(cls.work.name)
        cls.body = exact_patch_body()

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def compile_run(self, mutation: str | None = None):
        body = self.body
        if mutation:
            old, new = MUTANTS[mutation]
            if body.count(old) != 1:
                raise ValueError('mutation anchor drift '+mutation)
            body = body.replace(old, new, 1)
            if mutation == 'early_fd_put':
                trailer = '\tfd_putfile(fd);\n\treturn linux;'
                if body.count(trailer) != 1:
                    raise ValueError('mutant trailer drift')
                body = body.replace(trailer, '\treturn linux;', 1)
        name = mutation or 'actual'
        source = self.root / (name + '.c')
        exe = self.root / name
        source.write_text(STUB_PREFIX + body + STUB_SUFFIX)
        cmd = [os.environ.get('CC','cc'), *FLAGS, str(source), '-o', str(exe)]
        build = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        self.assertEqual(build.returncode, 0, f'{name}: {build.stderr}')
        return subprocess.run([str(exe)], text=True, capture_output=True,
                              timeout=30, preexec_fn=no_core)

    def test_original_function_five_scenarios(self):
        r = self.compile_run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'F03_ACTUAL_FD_BRIDGE_SOURCE_MODEL_PASS 5_SCENARIOS\n')
        self.assertEqual(r.stderr, '')

    def test_early_fd_unpin_rejected(self):
        self.assert_mutant('early_fd_put', 'fp->pins > 0 && !fp->destroyed')

    def test_missing_callback_rejected(self):
        self.assert_mutant('missing_callback', 'owned == &lf && owned->refs == 2')

    def test_missing_fd_unpin_rejected(self):
        self.assert_mutant('missing_fd_put', 'current_file.pins == 0 && get_calls == 1 && put_calls == 1')

    def test_double_fd_unpin_rejected(self):
        self.assert_mutant('duplicate_fd_put', 'fd == 4 && current_file.pins > 0 && !current_file.destroyed')

    def assert_mutant(self, name, reason):
        r = self.compile_run(name)
        self.assertEqual(r.returncode, -signal.SIGABRT, f'{name}: {r.stderr}')
        self.assertEqual(r.stdout, '')
        self.assertIn('CHECK_FAILED '+reason, r.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
