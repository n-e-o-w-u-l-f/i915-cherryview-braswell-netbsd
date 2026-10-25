#!/usr/bin/env python3
"""F04 exact sys_ioctl default branch C11 UBSan oracle; synthetic stubs only."""
from pathlib import Path
import re
import resource
import signal
import subprocess
from tempfile import TemporaryDirectory

PATCH = Path(__file__).resolve().parents[1] / 'patches/candidates/netbsd-11-drm-fileops-bridge-copyout-owned-20261025.patch'
assert subprocess.check_output(['git','hash-object',str(PATCH)],text=True).strip() == 'f9e34d0d52cf30cdfdfd12e43ed2e9a1951e9638'
section = PATCH.read_text().split('diff --git a/sys/kern/sys_generic.c b/sys/kern/sys_generic.c\n')
assert len(section) == 2
added = ''.join(line[1:] for line in section[1].splitlines(keepends=True) if line.startswith('+') and not line.startswith('+++'))
m = re.search(r'^\tdefault:\n.*?^\t\tbreak;\n', added, re.M|re.S)
assert m and added.count('\tdefault:\n') == 1
body = m.group()
assert body.count('(*fp->f_ops->fo_ioctl_user)(fp, com, data,') == 1
assert body.count('if (error == 0 && (com & IOC_OUT) && size)') == 1
assert 'error == 0 ||' not in body
PREFIX = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK_FAILED %s\n",#x); abort(); } } while (0)
#define IOC_OUT 0x1000
#define UIO_READ 1
#define SCARG(p,x) ((p)->x)
#define zero_size(n) (n)
struct args { unsigned fd; unsigned char *data; };
struct file;
struct fileops { int (*fo_ioctl)(struct file*,unsigned long,void*); int (*fo_ioctl_user)(struct file*,unsigned long,void*,void*); };
struct file { const struct fileops *f_ops; };
static unsigned copies, users, legacies, traces;
static int legacy_result, user_result;
static unsigned char *expected_user;
static int copyout(const void *src,void *dst,size_t n) { copies++; memcpy(dst,src,n); return 0; }
static void ktrgenio(unsigned fd,int direction,void *user,size_t n,int result) { CHECK(fd==7 && direction==UIO_READ && user==expected_user && n==8 && result==0); traces++; }
static int legacy(struct file *f,unsigned long c,void *p) { (void)f;(void)c;legacies++;memset(p,0x11,8);return legacy_result; }
static int drm(struct file *f,unsigned long c,void *p,void *u) { (void)f;(void)c;(void)p;CHECK(u==expected_user);users++; const unsigned char v[3]={37,38,39};CHECK(copyout(v,u,3)==0);return user_result; }
static const struct fileops old={legacy,NULL}, opted={legacy,drm};
static int invoke(const struct fileops *ops,unsigned long cmd,unsigned char *buf) {
  unsigned char data_mem[8]={0}; struct file file_obj={ops}; struct file *fp=&file_obj;
  struct args args={7,buf}; struct args *uap=&args; void *data=data_mem;
  unsigned long com=cmd; size_t size=8; int error=0; expected_user=buf;
  switch(com) { case 0xffffffff: break;
/* EXACT */
  }
  return error;
}
'''
SUFFIX = r'''int main(void) {
 unsigned char out[8];
 memset(out,0xcc,8); user_result=-9;
 CHECK(invoke(&opted,IOC_OUT|9,out)==-9);
 CHECK(users==1 && legacies==0 && copies==1 && traces==0);
 CHECK(out[0]==37 && out[1]==38 && out[2]==39 && out[3]==0xcc && out[7]==0xcc);
 memset(out,0xcc,8); legacy_result=-9; copies=0;users=0;legacies=0;traces=0;
 CHECK(invoke(&old,IOC_OUT|9,out)==-9);
 CHECK(copies==0 && traces==0 && legacies==1 && out[0]==0xcc);
 memset(out,0xcc,8); legacy_result=0;copies=0;legacies=0;
 CHECK(invoke(&old,IOC_OUT|9,out)==0);
 CHECK(copies==1 && traces==1 && legacies==1 && out[0]==0x11 && out[7]==0x11);
 puts("F04_EXACT_IOCTL_SINGLE_COPYOUT_PASS");return 0;
}
'''
MUT = {
 'double': ('error = (*fp->f_ops->fo_ioctl_user)(fp, com, data,\n\t\t\t    SCARG(uap, data));', 'error = (*fp->f_ops->fo_ioctl_user)(fp, com, data,\n\t\t\t    SCARG(uap, data));\n\t\t\t(void)copyout(data, SCARG(uap, data), size);'),
 'skip': ('error = (*fp->f_ops->fo_ioctl_user)(fp, com, data,\n\t\t\t    SCARG(uap, data));','(void)SCARG(uap, data); error = 0;'),
 'legacy': ('if (error == 0 && (com & IOC_OUT) && size)', 'if ((error == 0 || error == -9) && (com & IOC_OUT) && size)'),
}
def no_core(): resource.setrlimit(resource.RLIMIT_CORE,(0,0))
with TemporaryDirectory(prefix='f04-exact-copyout-') as tmp:
 for mode in ('actual',*MUT):
  code=body
  if mode!='actual':
   old,new=MUT[mode]; assert code.count(old)==1; code=code.replace(old,new)
  src=Path(tmp)/(mode+'.c');exe=Path(tmp)/mode
  src.write_text(PREFIX.replace('/* EXACT */',code)+SUFFIX)
  compile=subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
  assert compile.returncode==0,(mode,compile.stderr)
  run=subprocess.run([str(exe)],capture_output=True,text=True,preexec_fn=no_core,timeout=20)
  if mode=='actual': assert run.returncode==0 and run.stdout=='F04_EXACT_IOCTL_SINGLE_COPYOUT_PASS\n' and not run.stderr,(mode,run.returncode,run.stdout,run.stderr)
  else: assert run.returncode==-signal.SIGABRT and 'CHECK_FAILED' in run.stderr,(mode,run.returncode,run.stderr)
  print('F04_COPYOUT_OWNER',mode,'PASS')
print('F04_EXACT_SOURCE_C11_UBSAN_1_NORMAL_3_MUTANTS_PASS')
