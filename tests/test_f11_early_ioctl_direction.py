#!/usr/bin/env python3
"""Compile exact F11 added NetBSD direction code with pinned F10 prep fixture.

These are minimal generic host stubs, not real NetBSD headers or concurrency.
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

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/candidates/netbsd-11-drm-fileops-bridge-early-direction-20261025.patch'
FIXTURE = ROOT / 'tests/fixtures/f10_netbsd_sys_ioctl_prep_03d918f6.inc'
PATCH_SHA = 'fc1fa75dcb653d55dd7ff692bbdd7b0e1fd31676'
FIXTURE_SHA = '26aa9e2f12e3fb9077dc594e22cf13808f03b1ec'
FLAGS = ['-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
         '-fsanitize=undefined','-fno-sanitize-recover=undefined']

PREFIX = r'''#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "CHECK_FAILED %s\n", #x); abort(); } } while(0)
#define IOC_IN 0x80000000UL
#define IOC_OUT 0x40000000UL
#define IOC_VOID 0x20000000UL
#define IOCPARM_LEN(c) (((c)>>16)&0x1fffUL)
#define IOCGROUP(c) (((c)>>8)&0xffUL)
#define ENOTTY 25
#define EFAULT 14
#define UIO_WRITE 1
#define SCARG(p,n) ((p)->n)
#define zero_size(n) (n)
#define __predict_false(x) (x)
struct args { unsigned fd; unsigned char *data; };
struct file;
struct fileops { int (*fo_ioctl_user)(struct file *,unsigned long,void*,void*); };
struct file { const struct fileops *f_ops; };
static unsigned copied,traced;
static bool unreadable;
static int cb(struct file *f,unsigned long c,void *p,void *u) { (void)f;(void)c;(void)p;(void)u;return 0; }
static const struct fileops drm_ops = { cb }, native_ops = { NULL };
static int copyin(const void *src,void *dst,size_t count) {
    copied++; if(unreadable) return EFAULT;
    memcpy(dst,src,count);return 0;
}
static void ktrgenio(unsigned fd,int mode,void *user,size_t count,int err) {
    (void)user; CHECK(fd==7 && mode==UIO_WRITE && count==16 && err==0); traced++;
}
static unsigned long cmd(unsigned long dir,int group) {
    return dir | (16UL<<16) | ((unsigned long)group<<8) | 0x0dUL;
}
static int marshal(unsigned long command,const struct fileops *ops,
                   unsigned char *user,unsigned char *outdata) {
    unsigned char buffer[16]; memset(buffer,0xcc,sizeof buffer);
    struct file f = {ops}; struct file *fp = &f;
    struct args a = {7,user}; struct args *uap = &a;
    void *data = buffer; size_t size = IOCPARM_LEN(command);
    size_t alloc_size = size; unsigned long com = command,prep_com = 0;
    bool linux_drm_ioctl=false; int error=0;
    copied=traced=0;
    if (size != 16 && size != 0) abort();
/* EXACT EARLY */
/* EXACT PREP */
    if (size) {
/* EXACT NETBSD PREP */
    }
out:
    CHECK(com==command);
    memcpy(outdata,buffer,sizeof buffer);
    return error;
}
'''
SUFFIX = r'''int main(void) {
    unsigned char u[16],out[16]; memset(u,0x42,sizeof u);
    unreadable=false;
    CHECK(marshal(cmd(IOC_OUT,'d'),&drm_ops,u,out)==0);
    CHECK(out[0]==0x42 && out[15]==0x42 && copied==1);
    unreadable=true;
    CHECK(marshal(cmd(IOC_IN,'d'),&drm_ops,u,out)==0);
    CHECK(out[0]==0 && out[15]==0 && copied==0);
    unreadable=false;
    CHECK(marshal(cmd(IOC_IN|IOC_OUT,'d'),&drm_ops,u,out)==0);
    CHECK(out[0]==0x42 && copied==1);
    CHECK(marshal(cmd(0,'d'),&drm_ops,u,out)==0);
    CHECK(out[0]==0xcc && copied==0);
    CHECK(marshal(cmd(IOC_OUT,'d'),&native_ops,u,out)==0);
    CHECK(out[0]==0 && copied==0);
    CHECK(marshal(cmd(IOC_IN,'d'),&native_ops,u,out)==0);
    CHECK(out[0]==0x42 && copied==1);
    CHECK(marshal(cmd(IOC_OUT,'x'),&drm_ops,u,out)==0);
    CHECK(out[0]==0 && copied==0);
    unreadable=true;
    CHECK(marshal(((8192UL<<16)|((unsigned long)'d'<<8)|0x0dUL),&drm_ops,u,out)==ENOTTY);
    CHECK(copied==0);
    puts("F11_EARLY_DIRECTION_SOURCE_PASS 8_CASES"); return 0;
}
'''


def git_hash(path:Path)->str:
    return subprocess.check_output(['git','hash-object',str(path)],text=True).strip()


def extract():
    if git_hash(PATCH)!=PATCH_SHA or git_hash(FIXTURE)!=FIXTURE_SHA:
        raise ValueError('source Git-blob identity drift')
    content=PATCH.read_text()
    parts=content.split('diff --git a/sys/kern/sys_generic.c b/sys/kern/sys_generic.c\n')
    if len(parts)!=2:raise ValueError('patch section not unique')
    added=''.join(x[1:] for x in parts[1].splitlines(keepends=True)
                  if x.startswith('+') and not x.startswith('+++'))
    early=re.search(r'^\tlinux_drm_ioctl = .*?^\t}\n',added,re.S|re.M)
    prep=re.search(r'^\tprep_com = com;\n.*?^\t}\n',added,re.S|re.M)
    if early is None or prep is None: raise ValueError('early/prep fragment missing')
    if early.group().count('IOCGROUP(com)')!=1 or prep.group().count('prep_com =')!=2:
        raise ValueError('unexpected direction fragment')
    for source_fragment in ('+\t\tif (prep_com&IOC_IN) {',
        '+\t\t} else if ((prep_com&IOC_OUT) && size) {',
        '+\t\t} else if (prep_com&IOC_VOID) {',
        "+\tif (IOCGROUP(com) == 'd' && !linux_drm_ioctl) {"):
        if source_fragment not in content: raise ValueError('early native pre-copy or disklabel source missing')
    original=FIXTURE.read_text()
    if original.count('com&IOC_IN')!=1 or original.count('com&IOC_OUT')!=1:
        raise ValueError('pinned native fragment changed')
    converted=(original.replace('com&IOC_IN','prep_com&IOC_IN')
               .replace('com&IOC_OUT','prep_com&IOC_OUT')
               .replace('com&IOC_VOID','prep_com&IOC_VOID'))
    return early.group(),prep.group(),converted


def suppress_core():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))

class TestF11(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.early,cls.prep,cls.original_prep=extract()
        cls.temp=tempfile.TemporaryDirectory(prefix='f11-dir-model-')
        cls.root=Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self,mutant=None):
        early,prep=self.early,self.prep
        if mutant=='no_swap':
            prep=prep.replace('if (linux_drm_ioctl)', 'if (false)',1)
        elif mutant=='no_guard':
            early=early.replace('if (linux_drm_ioctl && (com & IOC_VOID) != 0)', 'if (false)',1)
        elif mutant=='scope_all':
            early=early.replace("IOCGROUP(com) == 'd'",'true',1)
        elif mutant=='change_cmd':
            prep=prep.replace('\t}\n','\t}\n\tcom = prep_com;\n',1)
        elif mutant=='legacy_swap':
            prep=prep.replace('if (linux_drm_ioctl)', 'if (true)',1)
        elif mutant is not None: raise ValueError(mutant)
        code=PREFIX.replace('/* EXACT EARLY */',early).replace('/* EXACT PREP */',prep)
        code=code.replace('/* EXACT NETBSD PREP */',self.original_prep)+SUFFIX
        name=mutant or 'original'
        src=self.root/(name+'.c'); exe=self.root/name
        src.write_text(code)
        compiled=subprocess.run([os.environ.get('CC','cc'),*FLAGS,str(src),'-o',str(exe)],
                                capture_output=True,text=True,timeout=60)
        self.assertEqual(compiled.returncode,0,f'{name}: {compiled.stderr}')
        return subprocess.run([str(exe)],capture_output=True,text=True,timeout=20,
                              preexec_fn=suppress_core)

    def test_actual_8_cases(self):
        r=self.run_case()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout,'F11_EARLY_DIRECTION_SOURCE_PASS 8_CASES\n')
        self.assertEqual(r.stderr,'')

    def check_mutant(self,name):
        r=self.run_case(name)
        self.assertEqual(r.returncode,-signal.SIGABRT,r.stderr)
        self.assertIn('CHECK_FAILED ',r.stderr)

    def test_no_swap(self):self.check_mutant('no_swap')
    def test_no_guard(self):self.check_mutant('no_guard')
    def test_scope_all(self):self.check_mutant('scope_all')
    def test_change_cmd(self):self.check_mutant('change_cmd')
    def test_legacy_swap(self):self.check_mutant('legacy_swap')

if __name__=='__main__': unittest.main(verbosity=2)
