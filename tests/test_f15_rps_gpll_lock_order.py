#!/usr/bin/env python3
"""Exact published GPLL/RPS source snippets, C11 UBSan lock-order tests.

This is a generic-host patch/source test, NOT a NetBSD object or HP test.
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

PATCH = Path(__file__).resolve().parents[1] / 'patches/candidates/netbsd-11-chv-gpll-rps-lock-order-20261026.patch'
SHA = '620916dac6179e6514852d795a9cc78762a4a467'
PREFIX = 'sys/external/bsd/drm2/dist/drm/i915/'
FILES = [PREFIX + 'display/intel_display.c', PREFIX + 'display/intel_display.h', PREFIX + 'gt/intel_rps.c']
FLAGS = ['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=undefined']
HEAD = r'''#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK_FAILED %s\n", #x); abort(); } } while(0)
#define CCK_CZ_CLOCK_CONTROL 0x62u
#define CCK_GPLL_CLOCK_CONTROL 0x67u
#define VLV_IOSF_SB_PUNIT 1u
#define VLV_IOSF_SB_NC 2u
#define VLV_IOSF_SB_CCK 3u
#define BIT(n) (1ul << (n))
#define DRM_DEBUG_DRIVER(...) ((void)0)
struct drm_i915_private { int hpll_freq,czclk_freq,lock,acquires,releases,reads,cz_reads,fuse_reads; };
struct intel_rps { struct drm_i915_private *i915; int gpll_ref_freq; };
static struct drm_i915_private *rps_to_i915(struct intel_rps *r) { return r->i915; }
static void vlv_cck_get(struct drm_i915_private *d) { CHECK(!d->lock); d->lock=1; d->acquires++; }
static void vlv_cck_put(struct drm_i915_private *d) { CHECK(d->lock); d->lock=0; d->releases++; }
static int vlv_get_hpll_vco(struct drm_i915_private *d) { CHECK(d->lock);d->fuse_reads++;return 1600000; }
static int vlv_get_cck_clock(struct drm_i915_private *d,const char *name,unsigned reg,int ref) {
 CHECK(d->lock);
 if(reg==CCK_CZ_CLOCK_CONTROL) { CHECK(strcmp(name,"czclk")==0);d->cz_reads++; }
 else { CHECK(reg==CCK_GPLL_CLOCK_CONTROL);CHECK(strcmp(name,"GPLL ref")==0);d->reads++; }
 return (ref*2+2)/4;
}
static void vlv_iosf_sb_get(struct drm_i915_private *d,unsigned long mask) {
 CHECK(mask==(BIT(VLV_IOSF_SB_PUNIT)|BIT(VLV_IOSF_SB_NC)|BIT(VLV_IOSF_SB_CCK)));
 vlv_cck_get(d);
}
static void vlv_iosf_sb_put(struct drm_i915_private *d,unsigned long mask) {
 CHECK(mask==(BIT(VLV_IOSF_SB_PUNIT)|BIT(VLV_IOSF_SB_NC)|BIT(VLV_IOSF_SB_CCK)));
 vlv_cck_put(d);
}
'''
TAIL = r'''int main(void) {
 struct drm_i915_private dev={0};struct intel_rps rps={.i915=&dev};
 model_vlv(&rps); CHECK(rps.gpll_ref_freq==400000);
 CHECK(dev.hpll_freq==1600000 && dev.czclk_freq==800000);
 CHECK(dev.acquires==2 && dev.releases==2 && !dev.lock && dev.reads==1 && dev.cz_reads==1 && dev.fuse_reads==1);
 model_chv(&rps); CHECK(rps.gpll_ref_freq==400000);
 CHECK(dev.acquires==4 && dev.releases==4 && !dev.lock && dev.reads==2 && dev.cz_reads==1 && dev.fuse_reads==1);
 puts("F15_PINNED_GPLL_RPS_LOCK_ORDER_2_ARCHETYPES_PASS");return 0;
}
'''

def read_sections():
    blob = subprocess.check_output(['git', 'hash-object', str(PATCH)], text=True).strip()
    if blob != SHA: raise ValueError('published integrated GPLL patch Git blob changed')
    p = PATCH.read_text()
    sections = re.split(r'(?=^diff --git a/)', p, flags=re.M)
    sections = [s for s in sections if s]
    if len(sections)!=3: raise ValueError('expected exactly three NetBSD source files')
    out = []
    for i,section in enumerate(sections):
        rows=section.splitlines()
        if rows[:3] != [f'diff --git a/{FILES[i]} b/{FILES[i]}',
                        f'--- a/{FILES[i]}',f'+++ b/{FILES[i]}']:
            raise ValueError('unexpected source/target files')
        hunks=[];cur=None
        for row in rows[3:]:
            if row.startswith('@@ '):
                m=re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@',row)
                if not m:raise ValueError('bad hunk range')
                cur=[tuple(map(int,m.groups())),[]];hunks.append(cur)
            else:
                if cur is None or not row or row[0] not in ' +-':raise ValueError('bad hunk text')
                cur[1].append(row)
        for (os,oc,ns,nc),rows in hunks:
            if sum(x[0]!='+' for x in rows)!=oc or sum(x[0]!='-' for x in rows)!=nc:
                raise ValueError('bad hunk body line counts')
        out.append(hunks)
    if list(map(len,out)) != [1,1,3]: raise ValueError('expected 1+1+3 original source hunks')
    return out

def patched_text(hunk):
    return '\n'.join(x[1:] for x in hunk[1] if x[0]!='-')+'\n'

def extracted():
    d=read_sections()
    code=patched_text(d[0][0])
    m=re.search(r'(?m)^int\nvlv_get_gpll_clock\(struct drm_i915_private \*dev_priv\)\n\{.*?^\}\n',code,re.S|re.M)
    if not m:raise ValueError('new exact GPLL function not found')
    gpll=m.group()
    if not all(needle in gpll for needle in ('vlv_cck_get(dev_priv);','vlv_cck_put(dev_priv);',
        'CCK_GPLL_CLOCK_CONTROL, dev_priv->czclk_freq')):raise ValueError('GPLL locking contract')
    if 'int vlv_get_gpll_clock(struct drm_i915_private *dev_priv);' not in patched_text(d[1][0]):
        raise ValueError('native prototype missing')
    source=patched_text(d[2][0]);match=re.search(r'rps->gpll_ref_freq = vlv_get_gpll_clock\(i915\);',source)
    if not match or 'vlv_get_cck_clock(' in source:raise ValueError('old GPLL under lock still present')
    init='static void vlv_init_gpll_ref_freq(struct intel_rps *rps) {\n' + \
         ' struct drm_i915_private *i915=rps_to_i915(rps);\n ' + match.group() + '\n DRM_DEBUG_DRIVER("GPLL %d\\n",rps->gpll_ref_freq);\n}\n'
    calls=[]
    for h in d[2][1:]:
        source=patched_text(h)
        x=re.search(r'\tvlv_init_gpll_ref_freq\(rps\);\n\n' \
                    r'\tvlv_iosf_sb_get\(i915,\n\t\t\tBIT\(VLV_IOSF_SB_PUNIT\) \|\n' \
                    r'\t\t\tBIT\(VLV_IOSF_SB_NC\) \|\n\t\t\tBIT\(VLV_IOSF_SB_CCK\)\);',source)
        if not x or source.count('vlv_init_gpll_ref_freq(rps);')!=1:
            raise ValueError('RPS GPLL call not uniquely BEFORE shared CCK lock')
        calls.append(x.group())
    return gpll,init,calls

def fake_netbsd_origins(sections, base:Path):
    for path,hunks in zip(FILES,sections):
        max_line=max(os+oc for ((os,oc,ns,nc),_) in hunks)+5
        src=['/* synthetic non-NetBSD line */']*max_line
        for ((os,oc,ns,nc),body) in hunks:
            old=[x[1:] for x in body if x[0]!='+']
            src[os-1:os-1+len(old)]=old
        p=base/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('\n'.join(src)+'\n')

def no_core():resource.setrlimit(resource.RLIMIT_CORE,(0,0))

class FullGpllWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hunks=read_sections();cls.gpll,cls.init,cls.calls=extracted()
        cls.temp=tempfile.TemporaryDirectory(prefix='f15-gpll-')
        cls.work=Path(cls.temp.name)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_original_source_patch_contract(self):
        self.assertEqual([len(x) for x in self.hunks],[1,1,3]);self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[0],self.calls[1])
    def test_native_git_check_applies_only_to_synthetic_preimages(self):
        stage=self.work/'synthetic';stage.mkdir(exist_ok=True)
        fake_netbsd_origins(self.hunks,stage)
        for params in [('--check','--whitespace=error'),('--whitespace=error',)]:
            p=subprocess.run(['git','apply',*params,str(PATCH)],cwd=stage,capture_output=True,text=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('vlv_get_gpll_clock(i915)',(stage/FILES[2]).read_text())
    def run_native_host(self,change=None):
        gpll,init=self.gpll,self.init;snippets=self.calls.copy()
        if change=='old_vlv_order':snippets[0]=snippets[0].replace('vlv_init_gpll_ref_freq(rps);\n\n\t','')+'\n\tvlv_init_gpll_ref_freq(rps);'
        elif change=='old_chv_order':snippets[1]=snippets[1].replace('vlv_init_gpll_ref_freq(rps);\n\n\t','')+'\n\tvlv_init_gpll_ref_freq(rps);'
        elif change=='missing_gpll_unlock':gpll=gpll.replace('vlv_cck_put(dev_priv);','(void)&vlv_cck_put;')
        elif change=='no_gpll_lock':gpll=gpll.replace('vlv_cck_get(dev_priv);','(void)&vlv_cck_get;')
        elif change=='wrong_gpll_ref':gpll=gpll.replace('CCK_GPLL_CLOCK_CONTROL, dev_priv->czclk_freq','CCK_GPLL_CLOCK_CONTROL, dev_priv->hpll_freq')
        elif change=='wrong_gpll_register':gpll=gpll.replace('CCK_GPLL_CLOCK_CONTROL, dev_priv->czclk_freq','CCK_CZ_CLOCK_CONTROL, dev_priv->czclk_freq')
        elif change is not None:raise ValueError(change)
        wrappers=''
        for name,snip in zip(('model_vlv','model_chv'),snippets):
            wrappers+=f'static void {name}(struct intel_rps *rps) {{\n'
            wrappers+=' struct drm_i915_private *i915=rps_to_i915(rps);\n'
            wrappers+=snip+'\n'
            wrappers+=' CHECK(i915->lock==1);\n vlv_iosf_sb_put(i915,BIT(VLV_IOSF_SB_PUNIT)|BIT(VLV_IOSF_SB_NC)|BIT(VLV_IOSF_SB_CCK));\n}\n'
        src=self.work/((change or 'good')+'.c');exe=self.work/(change or 'good')
        src.write_text(HEAD+gpll+init+wrappers+TAIL)
        compiled=subprocess.run([os.environ.get('CC','cc'),*FLAGS,str(src),'-o',str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        return subprocess.run([str(exe)],capture_output=True,text=True,timeout=10,preexec_fn=no_core)
    def test_actual_patch_c11_ubsan_two_rps_paths(self):
        r=self.run_native_host();self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('F15_PINNED_GPLL_RPS_LOCK_ORDER_2_ARCHETYPES_PASS',r.stdout)
    def reject(self,name):
        r=self.run_native_host(name)
        self.assertEqual(r.returncode,-signal.SIGABRT,f'{name}: {r.stderr}')
        self.assertIn('CHECK_FAILED',r.stderr)
    def test_old_vlv_order_rejected(self):self.reject('old_vlv_order')
    def test_old_chv_order_rejected(self):self.reject('old_chv_order')
    def test_missing_gpll_unlock_rejected(self):self.reject('missing_gpll_unlock')
    def test_no_gpll_lock_rejected(self):self.reject('no_gpll_lock')
    def test_wrong_gpll_ref_rejected(self):self.reject('wrong_gpll_ref')
    def test_wrong_gpll_register_rejected(self):self.reject('wrong_gpll_register')

if __name__=='__main__':unittest.main(verbosity=2)
