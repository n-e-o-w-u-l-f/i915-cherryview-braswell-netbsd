#!/usr/bin/env python3
"""Compile *actual* GPLL C added by F14 under controlled old NetBSD helpers."""
from pathlib import Path
import os
import resource
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/candidates/netbsd-11-chv-vlv-gpll-clock-20261026.patch'
PATCH_BLOB = '8e99fd0bea630d9c8cd75e316dd3a55e94e0f86e'
FLAGS = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined']

PRELUDE = r'''#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"CHECK_FAILED %s\n",#c); abort(); } } while(0)
#define CCK_CZ_CLOCK_CONTROL 0x62u
#define CCK_GPLL_CLOCK_CONTROL 0x67u
struct drm_i915_private { int hpll_freq,czclk_freq; int lock,gets,puts,fuse_reads,cz_reads,gpll_reads; };
static void vlv_cck_get(struct drm_i915_private *d) { CHECK(d->lock==0); d->lock=1; d->gets++; }
static void vlv_cck_put(struct drm_i915_private *d) { CHECK(d->lock==1); d->lock=0; d->puts++; }
static int vlv_get_hpll_vco(struct drm_i915_private *d) {
    CHECK(d->lock==1);d->fuse_reads++;return 1600000;
}
static int vlv_get_cck_clock(struct drm_i915_private *d,
                              const char *name,unsigned reg,int ref) {
    CHECK(d->lock==1);
    if (reg==CCK_CZ_CLOCK_CONTROL) {CHECK(strcmp(name,"czclk")==0);d->cz_reads++;}
    else {CHECK(reg==CCK_GPLL_CLOCK_CONTROL && strcmp(name,"GPLL ref")==0);d->gpll_reads++;}
    CHECK(ref>0);return (ref*2+2)/4;
}
'''
MAIN = r'''int main(void) {
 struct drm_i915_private a={0};
 CHECK(vlv_get_gpll_clock(&a)==400000);
 CHECK(a.hpll_freq==1600000 && a.czclk_freq==800000);
 CHECK(a.gets==1 && a.puts==1 && a.lock==0);
 CHECK(a.fuse_reads==1 && a.cz_reads==1 && a.gpll_reads==1);
 CHECK(vlv_get_gpll_clock(&a)==400000);
 CHECK(a.gets==2 && a.puts==2 && a.lock==0);
 CHECK(a.fuse_reads==1 && a.cz_reads==1 && a.gpll_reads==2);
 struct drm_i915_private b={.hpll_freq=1600000};
 CHECK(vlv_get_gpll_clock(&b)==400000);
 CHECK(b.fuse_reads==0 && b.cz_reads==1 && b.gpll_reads==1);
 CHECK(b.gets==1 && b.puts==1 && b.lock==0);
 struct drm_i915_private c={.czclk_freq=800000};
 CHECK(vlv_get_gpll_clock(&c)==400000);
 CHECK(c.fuse_reads==0 && c.cz_reads==0 && c.gpll_reads==1);
 CHECK(c.gets==1 && c.puts==1 && c.lock==0);
 puts("F14_GPLL_NATIVE_SOURCE_MODEL_PASS_COLD_WARM_PARTIAL_CACHE");return 0;
}
'''

def source():
    value = subprocess.check_output(['git','hash-object',str(PATCH)], text=True).strip()
    if value != PATCH_BLOB:
        raise ValueError('F14 patch Git blob drift')
    text = PATCH.read_text()
    start = text.index('\n+int\n+vlv_get_gpll_clock(')+1
    end = text.index('\n+}\n',start)+3
    lines = text[start:end].splitlines()
    if not all(line.startswith('+') for line in lines):
        raise ValueError('candidate GPLL source interrupted')
    c = '\n'.join(line[1:] for line in lines)+'\n'
    if c.count('vlv_cck_get(')!=1 or c.count('vlv_cck_put(')!=1:
        raise ValueError('CCK ownership contract missing')
    if '+int vlv_get_gpll_clock(struct drm_i915_private *dev_priv);' not in text:
        raise ValueError('native NetBSD header declaration missing')
    return c

def disable_core():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))

class F14NativeGpll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = source()
        cls.temp = tempfile.TemporaryDirectory(prefix='f14-gpll-')
        cls.root = Path(cls.temp.name)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def run_case(self,kind=None):
        c=self.actual
        if kind=='no_cck_put': c=c.replace('vlv_cck_put(dev_priv);','(void)&vlv_cck_put;')
        elif kind=='wrong_source': c=c.replace('CCK_GPLL_CLOCK_CONTROL, dev_priv->czclk_freq','CCK_GPLL_CLOCK_CONTROL, dev_priv->hpll_freq')
        elif kind=='recache_every_time': c=c.replace('if (dev_priv->czclk_freq == 0)', 'if (true)')
        elif kind=='wrong_reg': c=c.replace('CCK_GPLL_CLOCK_CONTROL, dev_priv->czclk_freq','CCK_CZ_CLOCK_CONTROL, dev_priv->czclk_freq')
        elif kind=='no_cck_get': c=c.replace('vlv_cck_get(dev_priv);','(void)&vlv_cck_get;')
        elif kind is not None: raise ValueError(kind)
        stem=kind or 'good'; p=self.root/(stem+'.c'); exe=self.root/stem
        p.write_text(PRELUDE+c+MAIN)
        result=subprocess.run([os.environ.get('CC','cc'),*FLAGS,str(p),'-o',str(exe)],capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr)
        return subprocess.run([str(exe)],capture_output=True,text=True,timeout=15,preexec_fn=disable_core)
    def test_actual_gpll_source_and_lifetime(self):
        r=self.run_case();self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('F14_GPLL_NATIVE_SOURCE_MODEL_PASS_',r.stdout)
    def neg(self,k):
        r=self.run_case(k)
        self.assertEqual(r.returncode,-signal.SIGABRT,r.stderr)
        self.assertIn('CHECK_FAILED ',r.stderr)
    def test_no_cck_put(self):self.neg('no_cck_put')
    def test_wrong_source(self):self.neg('wrong_source')
    def test_recache_every_time(self):self.neg('recache_every_time')
    def test_wrong_reg(self):self.neg('wrong_reg')
    def test_no_cck_get(self):self.neg('no_cck_get')

if __name__=='__main__':unittest.main(verbosity=2)
