#!/usr/bin/env python3
"""Pinned NetBSD zero-size ioctl pointer source, generic C11 stub test only."""
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import unittest

FIXTURE = Path(__file__).resolve().parent / 'fixtures/f12_netbsd_sys_ioctl_zero_size_03d918f6.inc'
SHA = '7b349ede04b223bb93f61de53c341c1c33388c2b'
FLAGS = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined', '-fno-sanitize-recover=undefined']
PREFIX = r'''#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK_FAILED %s\n", #x); abort(); } } while (0)
#ifndef IOCPARM_SHIFT
#define IOCPARM_SHIFT 16
#endif
#define SCARG(p,x) ((p)->x)
struct args { void *data; };
static void *marshalled(unsigned long com, void *user, void *kernel_buf) {
  struct args a={user}; struct args *uap=&a; (void)uap; void *data = NULL;
#include "fixtures/f12_netbsd_sys_ioctl_zero_size_03d918f6.inc"
    data=kernel_buf;
  }
  return data;
}
int main(void) {
  unsigned char userbuf[32]={0xaa}, kernelbuf[128]={0};
  void *user=userbuf, *kernel=kernelbuf;
  const unsigned long set_master=((unsigned long)'d'<<8)|0x1eUL;
  const unsigned long forged_get_cap=((unsigned long)'d'<<8)|0x0cUL;
  const unsigned long get_cap16=((unsigned long)'d'<<8)|0x0cUL|(16UL<<16);
  CHECK((set_master>>16)==0 && (forged_get_cap>>16)==0);
  CHECK(marshalled(set_master,user,kernel)==user);
  CHECK(marshalled(forged_get_cap,user,kernel)==user);
  CHECK(marshalled(forged_get_cap,NULL,kernel)==NULL);
  CHECK(marshalled(get_cap16,user,kernel)==kernel);
  CHECK(kernel!=user);
#ifdef REQUIRE_KERNEL_POINTER
  /* Expected to FAIL for the actual F11 size-zero path. */
  CHECK(marshalled(forged_get_cap,user,kernel)!=user);
#endif
  puts("F12_F11_ZERO_SIZE_USER_POINTER_ALIAS_CONFIRMED");
  return 0;
}
'''

def suppress_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class SourceZeroSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.working = tempfile.TemporaryDirectory(prefix='f12-native-zero-size-')
        cls.root = Path(cls.working.name)
        (cls.root/'fixtures').mkdir()
        assert FIXTURE.is_file()
        sha=subprocess.check_output(['git','hash-object',str(FIXTURE)],text=True).strip()
        if sha!=SHA: raise ValueError('pinned zero-size source fixture changed')
        cls.original=FIXTURE.read_text()
        assert cls.original.count('data = SCARG(uap, data);')==1
    @classmethod
    def tearDownClass(cls):
        cls.working.cleanup()
    def run_case(self, mode='baseline'):
        fixture=self.original
        flags=[]
        if mode=='fixed_alias_mutant':
            fixture=fixture.replace('data = SCARG(uap, data);','data = kernel_buf;')
        elif mode=='oversized_shift_mutant': flags=['-DIOCPARM_SHIFT=32']
        elif mode=='undersized_shift_mutant': flags=['-DIOCPARM_SHIFT=8']
        elif mode=='kernel_pointer_admission': flags=['-DREQUIRE_KERNEL_POINTER']
        elif mode!='baseline': raise ValueError(mode)
        (self.root/'fixtures'/FIXTURE.name).write_text(fixture)
        src=self.root/(mode+'.c'); exe=self.root/mode
        src.write_text(PREFIX)
        p=subprocess.run([os.environ.get('CC','cc'),*FLAGS,*flags,str(src),'-o',str(exe)],capture_output=True,text=True,timeout=45)
        self.assertEqual(p.returncode,0,f'{mode} compiler: {p.stderr}')
        return subprocess.run([str(exe)],capture_output=True,text=True,timeout=20,preexec_fn=suppress_core)
    def test_source_alias_four_cases(self):
        r=self.run_case()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout,'F12_F11_ZERO_SIZE_USER_POINTER_ALIAS_CONFIRMED\n')
    def assert_reject(self,mode):
        r=self.run_case(mode)
        self.assertEqual(r.returncode,-signal.SIGABRT,f'{mode}: {r.stderr}')
        self.assertIn('CHECK_FAILED',r.stderr)
    def test_kernel_pointer_admission_fails_as_expected(self):
        self.assert_reject('kernel_pointer_admission')
    def test_fix_alias_mutant_detected(self):
        self.assert_reject('fixed_alias_mutant')
    def test_oversized_shift_detected(self):
        self.assert_reject('oversized_shift_mutant')
    def test_undersized_shift_detected(self):
        self.assert_reject('undersized_shift_mutant')

if __name__=='__main__': unittest.main(verbosity=2)
