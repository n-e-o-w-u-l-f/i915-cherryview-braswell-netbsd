#!/usr/bin/env python3
"""Generate the real NetBSD fatal wait backend atop the immutable0032 runtime."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1];ASSETS=ROOT/'compat/native-fatal'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--netbsd-tree',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
 data=json.loads((ASSETS/'expected-source.json').read_text())
 if args.out.exists():ap.error('preserve prior patch')
 assert subprocess.check_output(['git','-C',str(args.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==data['netbsd_pin']
 for name,digest in data['asset_patch_sha256'].items():assert sha(ASSETS/name)==digest,name
 patch=(ASSETS/'native-backend.patch').read_bytes()+(ASSETS/'task-runtime.patch').read_bytes()
 assert hashlib.sha256(patch).hexdigest()==data['patch_sha256']
 with tempfile.TemporaryDirectory(prefix='fatal-patch-contract-') as name:
  temp=Path(name);p=temp/'fatal.patch';p.write_bytes(patch)
  for rel,row in data['files'].items():
   target=temp/rel;target.parent.mkdir(parents=True,exist_ok=True)
   old=(ROOT/'compat/native-runtime/task/linux_task.c').read_bytes() if rel.endswith('/linux_task.c') else subprocess.check_output(['git','-C',str(args.netbsd_tree),'show',data['netbsd_pin']+':'+rel])
   target.write_bytes(old);assert sha(target)==row['before'],rel
  subprocess.run(['git','-C',str(temp),'apply','--check',str(p)],check=True)
  subprocess.run(['git','-C',str(temp),'apply',str(p)],check=True)
  for rel,row in data['files'].items():assert sha(temp/rel)==row['after'],rel
 args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_bytes(patch)
 print('REAL_NATIVE_FATAL_WAIT_PATCH_GENERATED core_kernel_backend_required=1')
if __name__=='__main__':main()
