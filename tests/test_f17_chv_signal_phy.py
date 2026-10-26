#!/usr/bin/env python3
"""Compile verbatim F17 signal-level C function and strict semantic mutants; generic host only."""
import pathlib, subprocess, tempfile, resource, signal, os, unittest
C=pathlib.Path(__file__).with_name('test_f17_chv_signal_phy_source.c')
FLAGS=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=undefined']
FUNCTION_FNV64=0x25d4c36ad02b2783
MUT={
 'pipe_instead_of_port_phy':('enum dpio_phy phy = vlv_dport_to_phy(dport);','enum dpio_phy phy = (enum dpio_phy)(intel_crtc->pipe >> 1);\n\t(void)&vlv_dport_to_phy;'),
 'wrong_port_d_phy':('return d->base.port==PORT_D ? DPIO_PHY1 : DPIO_PHY0;','return d->base.port==PORT_D ? DPIO_PHY0 : DPIO_PHY1;'),
 'wrong_channel':('enum dpio_channel ch = vlv_dport_to_channel(dport);','enum dpio_channel ch = (enum dpio_channel)(1 - (int)vlv_dport_to_channel(dport));'),
 'missing_dpio_lock':('vlv_dpio_get(dev_priv);','(void)&vlv_dpio_get;'),
 'missing_unlock':('vlv_dpio_put(dev_priv);','(void)&vlv_dpio_put;'),
 'wrong_write_phy':('vlv_dpio_phy_write(dev_priv, phy,','vlv_dpio_phy_write(dev_priv, (enum dpio_phy)(1-(int)phy),'),
}
def disable_core():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
class ExactF17(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.code=C.read_text();s=cls.code.split('/* BEGIN F17 EXACT PATCHED NATIVE FUNCTION */\n')[1].split('/* END F17 EXACT PATCHED NATIVE FUNCTION */')[0].strip()
  h=0xcbf29ce484222325
  for c in s:h=((h^ord(c))*0x100000001b3)&0xffffffffffffffff
  if h!=FUNCTION_FNV64: raise ValueError('actual F17 native C source snippet drift')
  cls.tmp=tempfile.TemporaryDirectory(prefix='f17-model-')
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_code(self,mut=None):
  x=self.code
  if mut:
   old,new=MUT[mut];self.assertEqual(x.count(old),1 if mut!='wrong_write_phy' else 9,mut)
   x=x.replace(old,new)
  path=pathlib.Path(self.tmp.name)/(mut or 'baseline');p=path.with_suffix('.c');p.write_text(x)
  cc=os.environ.get('CC','cc');z=subprocess.run([cc,*FLAGS,str(p),'-o',str(path)],text=True,capture_output=True,timeout=30)
  self.assertEqual(z.returncode,0,z.stderr)
  return subprocess.run([str(path)],text=True,capture_output=True,timeout=10,preexec_fn=disable_core)
 def test_actual_source(self):
  r=self.run_code();self.assertEqual(r.returncode,0,r.stderr);self.assertIn('F17_EXACT_CHV_SIGNAL_PHY_ROUTING_PASS',r.stdout)
 def fail_mut(self,name):
  r=self.run_code(name);self.assertEqual(r.returncode,-signal.SIGABRT,r.stderr);self.assertIn('CHECK_FAILED',r.stderr)
 def test_pipe_instead_of_port_phy(self):self.fail_mut('pipe_instead_of_port_phy')
 def test_wrong_port_d_phy(self):self.fail_mut('wrong_port_d_phy')
 def test_wrong_channel(self):self.fail_mut('wrong_channel')
 def test_missing_dpio_lock(self):self.fail_mut('missing_dpio_lock')
 def test_missing_unlock(self):self.fail_mut('missing_unlock')
 def test_wrong_write_phy(self):self.fail_mut('wrong_write_phy')
if __name__=='__main__':unittest.main(verbosity=2)
