#!/usr/bin/env python3
"""Generate native clear/wait/timed-wait policy from immutable source assets."""
from pathlib import Path
import argparse,difflib,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1];ASSETS=ROOT/'compat/native-bit-wait'
ap=argparse.ArgumentParser();ap.add_argument('--netbsd-tree',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
data=json.loads((ASSETS/'expected-source.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
assert not args.out.exists()
assert subprocess.check_output(['git','-C',str(args.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==data['netbsd_pin']
old=subprocess.check_output(['git','-C',str(args.netbsd_tree),'show',data['netbsd_pin']+':'+data['source_path']]);assert sha(old)==data['before_sha256']
new=(ASSETS/'linux_wait_bit.c').read_bytes();assert sha(new)==data['after_sha256']
patch=''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+data['source_path'],tofile='b/'+data['source_path'],n=3)).encode()
assert sha(patch)==data['patch_sha256']
args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_bytes(patch)
print('NATIVE_BIT_WAIT_POLICY_PATCH_GENERATED')
