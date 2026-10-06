#!/usr/bin/env python3
"""Reproduce frozen PWM-disabled consumer bodies; no enabled provider substitute."""
from pathlib import Path
import argparse,hashlib,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
SHA='199d50c006b2ea16186fd71d1dc8aa8ded6b5a6eb0e0d8f42a72fed8b8c7561c'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--netbsd-tree',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():p.error('preserve previous generated patch')
 if subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()!=PIN:p.error('wrong Native source pin')
 with tempfile.TemporaryDirectory(prefix='pwm-source-') as name:
  temp=Path(name);shutil.copytree(ROOT/'compat/native-pwm',temp/'assets')
  subprocess.run([sys.executable,str(temp/'assets/generate.py')],check=True)
  data=(temp/'assets/native-pwm.patch').read_bytes()
  if hashlib.sha256(data).hexdigest()!=SHA:raise RuntimeError('changed frozen PWM body projection')
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_bytes(data)
 print('NATIVE_PWM_DISABLED_PROFILE_PATCH_GENERATED enabled_provider=OPEN')
if __name__=='__main__':main()
