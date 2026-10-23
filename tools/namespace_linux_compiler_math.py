#!/usr/bin/env python3
"""Preserve pinned Linux attribute/math semantics in a native private namespace.

Only verified Linux-owned C identifiers are translated. Native OS adapters,
comments, strings, character literals and compiler attribute property names
remain unchanged. The result is a source integration, not API/runtime closure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess

PIN='fd179f8a05be3ccae366b9b96e176b51fbe54aab'
INCLUDE_CONTRACT_VERSION=3
PWM_NAMES=('pwm_polarity','pwm_enable','pwm_disable')
UUID_NAMES=('uuid_t','uuid_null','uuid_equal','uuid_copy','import_uuid',
            'export_uuid','uuid_is_null','generate_random_uuid','uuid_gen',
            'uuid_index','uuid_parse')
UUID_INCLUDE_CONTRACTS={
    'include/drm/display/drm_dp_mst_helper.h':'#include <linux/types.h>\n',
    'include/linux/vfio.h':'#include <linux/iommu.h>\n',
}
TOKEN=re.compile(r'/\*[\s\S]*?\*/|//(?:\\\r?\n|[^\n])*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*')
LEGACY_TOKEN=TOKEN
TOKEN=re.compile(r'^[ \t]*#[ \t]*(?:include|include_next|import)[ \t]+(?:\\\r?\n[ \t]*)?<[^>\r\n]+>|'+LEGACY_TOKEN.pattern,re.M)

def frozen(linux,path):
    return subprocess.check_output(['git','-C',str(linux),'show',PIN+':'+path],text=True)

def adapt_includes(text,linux_path,version=INCLUDE_CONTRACT_VERSION):
    if version not in (0,1,2,3):raise RuntimeError('unknown include-contract version')
    if version==0:return text
    if linux_path in UUID_INCLUDE_CONTRACTS:
        anchor=UUID_INCLUDE_CONTRACTS[linux_path]
        addition=anchor+'#include <linux/uuid.h>\n'
        if addition not in text:
            if text.count(anchor)!=1:raise RuntimeError('changed frozen UUID include anchor: '+linux_path)
            text=text.replace(anchor,addition)
    if version>=2:
        contracts={
            'include/drm/drm_modes.h':('struct videomode;\n','struct videomode;\nstruct device_node;\n'),
            'include/drm/drm_atomic.h':('#include <drm/drm_crtc.h>\n','#include <linux/completion.h>\n#include <drm/drm_crtc.h>\n'),
        }
        if linux_path in contracts:
            anchor,addition=contracts[linux_path]
            if addition not in text:
                if text.count(anchor)!=1:raise RuntimeError('changed complete-type include anchor: '+linux_path)
                text=text.replace(anchor,addition)
    if version>=3:
        contracts={
            'include/drm/drm_connector.h':('struct drm_connector_helper_funcs;\n','struct dentry;\nstruct drm_connector_helper_funcs;\n'),
            'include/drm/drm_crtc.h':('#include <linux/types.h>\n','#include <linux/types.h>\n#include <linux/ktime.h>\n'),
        }
        if linux_path in contracts:
            anchor,addition=contracts[linux_path]
            if addition not in text:
                if text.count(anchor)!=1:raise RuntimeError('changed direct dependency anchor: '+linux_path)
                text=text.replace(anchor,addition)
    return text

def bindings(linux):
    head=subprocess.check_output(['git','-C',str(linux),'rev-parse','HEAD'],text=True).strip()
    if head!=PIN:raise RuntimeError('wrong frozen Linux reference')
    names=set()
    for path,guard in [('include/linux/compiler_attributes.h','__LINUX_COMPILER_ATTRIBUTES_H'),('include/linux/math.h','_LINUX_MATH_H'),
                       ('include/linux/typecheck.h','TYPECHECK_H_INCLUDED'),('include/linux/wordpart.h','_LINUX_WORDPART_H'),
                       ('include/linux/container_of.h','_LINUX_CONTAINER_OF_H')]:
        names.update(re.findall(r'^\s*#\s*define\s+([A-Za-z_][A-Za-z_0-9]*)',frozen(linux,path),re.M))
        names.discard(guard)
    # Keep NetBSD's legacy assertions for native callers; Linux-owned source
    # uses the complete pinned optional-message C11 assertion wrappers.
    assertion_names=re.findall(r'^#define (static_assert|__static_assert)\(',frozen(linux,'include/linux/build_bug.h'),re.M)
    if set(assertion_names)!={'static_assert','__static_assert'}:
        raise RuntimeError('changed pinned static assertion declarations')
    names.update(assertion_names)
    uuid_header=frozen(linux,'include/linux/uuid.h')
    if any(not re.search(r'\b'+name+r'\b',uuid_header) for name in UUID_NAMES):
        raise RuntimeError('changed pinned UUID interfaces')
    names.update(UUID_NAMES)
    pwm_header=frozen(linux,'include/linux/pwm.h')
    if any(not re.search(r'\b'+name+r'\b',pwm_header) for name in PWM_NAMES):
        raise RuntimeError('changed pinned PWM interfaces')
    names.update(PWM_NAMES)
    # This spelling is also a GCC attribute property inside its own definition.
    # It is not a native collision and must retain its compiler spelling.
    names.discard('__alloc_size__')
    result={name:'netbsd_linux_'+name.lstrip('_') for name in sorted(names)}
    # The helper and public spelling differ only in leading underscores.
    result['__static_assert']='netbsd_linux_static_assert_message'
    if len(set(result.values()))!=len(result):raise RuntimeError('namespace collision')
    return result

def translate(text,mapping):
    return TOKEN.sub(lambda m:mapping.get(m[0],m[0]),text)

def legacy_translate(text,mapping):
    """Verify exact bytes from the retained version-1 translation ledger."""
    return LEGACY_TOKEN.sub(lambda m:mapping.get(m[0],m[0]),text)

def sha(data):return hashlib.sha256(data).hexdigest()

def require_native_hp():
    if (platform.system() != 'NetBSD' or platform.release().split('.', 1)[0] != '11' or
            socket.gethostname().split('.', 1)[0] != 'hp-tpnw121' or os.geteuid() == 0):
        raise RuntimeError('native source integration requires the unprivileged hp-tpnw121 / NetBSD 11 owner')

def relative_input(name):
    from pathlib import PurePosixPath
    if not isinstance(name, str) or not name:
        raise RuntimeError('nonempty relative input path required')
    path = PurePosixPath(name)
    if (path.is_absolute() or path.as_posix() != name or '\\' in name or ':' in name or
            '\x00' in name or any(part in ('', '.', '..') for part in name.split('/'))):
        raise RuntimeError('unsafe relative input path: ' + repr(name))
    return path

def disjoint(a, b):
    return a != b and a not in b.parents and b not in a.parents

def new_ledger(path, protected):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise RuntimeError('preserve existing evidence: ' + str(path))
    path = path.resolve()
    if not path.parent.is_dir() or any(not disjoint(path, p) for p in protected):
        raise RuntimeError('new ledger must have an existing parent outside protected inputs: ' + str(path))
    return path

def stage_paths(linux, tree, manifest, out, api=None):
    linux, tree, manifest = [Path(p).resolve(strict=True) for p in (linux, tree, manifest)]
    if not linux.is_dir() or not tree.is_dir() or not manifest.is_file():
        raise RuntimeError('explicit Linux, native tree and source manifest required')
    if not disjoint(linux, tree) or not disjoint(manifest, tree):
        raise RuntimeError('native output tree must be separate from Linux and source manifest')
    protected = [linux, tree, manifest]
    if api is not None:
        api = Path(api).resolve(strict=True)
        if not api.is_file():raise RuntimeError('API ledger must be a saved file')
        protected.append(api)
    return linux, tree, manifest, new_ledger(out, protected), api

def translation_identity(mapping, include_version=INCLUDE_CONTRACT_VERSION):
    return {'tokenizer_version': 2, 'include_contract_version': include_version,
            'mapping_sha256': sha(json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode())}

def integrate(linux,tree,manifest,api,out):
    linux,tree,manifest,out,api=stage_paths(linux,tree,manifest,out,api)
    mapping=bindings(linux)
    report=json.loads(api.read_text()) if api else {'linux_pin':PIN,'rows':[]}
    if report['linux_pin']!=PIN:raise RuntimeError('wrong API source pin')
    prior=report.get('compiler_math_namespace',{}).get('mapping',{})
    if any(mapping.get(k)!=v for k,v in prior.items()):raise RuntimeError('changed prior private binding')
    version=report.get('compiler_math_namespace',{}).get('tokenizer_version',1)
    if version not in (1,2):raise RuntimeError('unknown prior source tokenizer')
    previous_translate=legacy_translate if version==1 else translate
    prior_includes=report.get('compiler_math_namespace',{}).get('include_contract_version',0)
    selected=json.loads(manifest.read_text())
    if selected['linux_pin']!=PIN or not selected['linux_head_verified']:raise RuntimeError('unverified full source manifest')
    plans=[];seeds=[]
    def plan(path,old,new,source,kind):
        if tree not in path.resolve(strict=True).parents:
            raise RuntimeError('source escapes isolated native tree: '+str(path))
        data=path.read_bytes();old=old.encode();new=new.encode()
        if data not in (old,new):raise RuntimeError('changed source outside owned translation: '+str(path))
        if data!=new:plans.append((path,new))
        return {'path':str(path.relative_to(tree)),'linux_path':source,'frozen_sha256':sha(old),'sha256':sha(new),'state':kind,'changed':old!=new}
    for row in selected['files']:
        rel=row['path']
        relative_input(rel)
        if not rel.endswith(('.c','.h')):continue
        old=frozen(linux,rel)
        # Existing source-owned patch 0022 only changes this Linux initializer.
        baseline=translate(old,{'RB_ROOT':'LINUX_RB_ROOT'})
        target=tree/'sys/external/bsd/drm2/dist'/(rel.removeprefix('drivers/gpu/') if rel.startswith('drivers/gpu/') else rel)
        proof=plan(target,previous_translate(adapt_includes(baseline,rel,prior_includes),prior),
                   translate(adapt_includes(baseline,rel),mapping),rel,'LINUX_SEED_TRANSLATED_UNREVIEWED')
        proof['frozen_sha256']=sha(old.encode());seeds.append(proof)
    for row in report['rows']:
        if row['state'] not in ('IMPORTED_API_UNREVIEWED','IMPORTED_API_TRANSLATED_UNREVIEWED'):continue
        relative_input(row['path']);relative_input(row['linux_path'])
        target=tree/row['path'];old=frozen(linux,row['linux_path'])
        new=translate(adapt_includes(old,row['linux_path']),mapping)
        if sha(target.read_bytes())!=row['sha256']:raise RuntimeError('changed prior API input: '+row['path'])
        producer=row.get('translation')
        if producer is not None:
            if producer != translation_identity(mapping):
                raise RuntimeError('unrecognized API import transformation: '+row['path'])
            previous=translate(adapt_includes(old,row['linux_path']),mapping)
        elif row['state']=='IMPORTED_API_TRANSLATED_UNREVIEWED':
            # The original importer translated raw pinned identifiers without
            # include adaptation or a global namespace ledger. Reconstruct
            # precisely that producer, never accept arbitrary ledger bytes.
            previous=(previous_translate(adapt_includes(old,row['linux_path'],prior_includes),prior)
                      if report.get('compiler_math_namespace') else translate(old,mapping))
        else:
            previous=old
        proof=plan(target,previous,new,row['linux_path'],'IMPORTED_API_TRANSLATED_UNREVIEWED')
        if proof['changed']:
            row['frozen_sha256']=sha(old.encode());row['sha256']=proof['sha256'];row['state']=proof['state']
        row['translation']=translation_identity(mapping)
    if out.exists() or out.is_symlink():raise RuntimeError('preserve existing translation evidence')
    # Validate every input before any mutation; replace each file atomically.
    for path,data in plans:
        temp=path.with_name(path.name+'.compiler-math.tmp')
        if temp.exists():raise RuntimeError('preserve interrupted source write '+str(temp))
        temp.write_bytes(data);temp.replace(path)
    report['compiler_math_namespace']={'tokenizer_version':2,'include_contract_version':INCLUDE_CONTRACT_VERSION,
        'include_contracts':dict(UUID_INCLUDE_CONTRACTS, **{'include/drm/drm_modes.h':'file-scope opaque device_node', 'include/drm/drm_atomic.h':'explicit linux/completion.h', 'include/drm/drm_connector.h':'file-scope opaque dentry', 'include/drm/drm_crtc.h':'explicit real linux/ktime.h'}),'mapping':mapping,'seeds':seeds,'changed_files':len(plans),
        'acceptance':'OPEN; token bindings preserve algorithms but do not prove all OS/ABI/runtime semantics'}
    out.write_text(json.dumps(report,indent=2)+'\n')
    return len(plans),sum(row['changed'] for row in seeds)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux-tree',type=Path,required=True);p.add_argument('--netbsd-tree',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--api-ledger',type=Path);p.add_argument('--out-ledger',type=Path,required=True)
    a=p.parse_args()
    try:
        require_native_hp()
        count,seeds=integrate(a.linux_tree,a.netbsd_tree,a.manifest,a.api_ledger,a.out_ledger)
    except (OSError, ValueError, RuntimeError) as error:
        p.error(str(error))
    print('LINUX_COMPILER_MATH_NAMESPACE',count,'changed files;',seeds,'changed selected inputs')

if __name__=='__main__':main()
