#!/usr/bin/env python3
"""Pure namespace controls; --native adds actual pinned-macro HP C execution.

Native execution models scalar types/compiler annotations in userland. It is
not a NetBSD kernel-header ABI, MM, DRM or hardware acceptance check.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import namespace_linux_compiler_math as ns

SOURCE=(ROOT/'tests/fixtures/linux_minmax_fd179f8.h').read_text(encoding='utf8')


class MinmaxNamespace(unittest.TestCase):
    def test_complete_pinned_macro_fixture_identity(self):
        self.assertEqual(ns.sha(SOURCE.encode()),ns.MINMAX_SHA256)

    def test_every_real_macro_has_an_available_distinct_private_definition(self):
        mapping=ns.minmax_bindings(SOURCE)
        after=ns.translate(SOURCE,mapping)
        definitions=set(re.findall(r'^\s*#\s*define\s+([A-Za-z_][A-Za-z_0-9]*)',SOURCE,re.M))
        definitions.remove('_LINUX_MINMAX_H')
        actual=set(re.findall(r'^\s*#\s*define\s+([A-Za-z_][A-Za-z_0-9]*)',after,re.M))
        self.assertTrue({mapping[name] for name in definitions}<=actual)
        self.assertNotEqual(mapping['__clamp'],mapping['clamp'])
        self.assertEqual(len(mapping),len(set(mapping.values())))

    def test_token_paste_producer_matches_both_produced_operator_names(self):
        mapping=ns.minmax_bindings(SOURCE)
        for operation in ('min','max'):
            self.assertEqual(mapping['__cmp_op_']+mapping[operation],mapping['__cmp_op_'+operation])
        after=ns.translate(SOURCE,mapping)
        self.assertIn(mapping['__cmp_op_']+'##op',after)

    def test_modified_algorithm_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'changed pinned minmax'):
            ns.minmax_bindings(SOURCE.replace('auto ux = (x);','auto ux = (x) + 1;',1))

    def test_owned_consumer_reaches_real_header_with_old_version_preserved(self):
        source='#include <linux/kernel.h>\nint f(int x,int y){return min(x,y);}\n'
        self.assertNotIn('<linux/minmax.h>',ns.adapt_includes(source,'drivers/gpu/drm/a.c',3))
        after=ns.adapt_includes(source,'drivers/gpu/drm/a.c')
        self.assertIn('#include <linux/minmax.h>\n',after)
        self.assertEqual(ns.adapt_includes(after,'drivers/gpu/drm/a.c'),after)

    def test_minmax_has_private_compiler_backend_without_self_include(self):
        after=ns.adapt_includes(SOURCE,'include/linux/minmax.h')
        self.assertIn('#include <linux/minmax_netbsd.h>',after)
        self.assertNotIn('#include <linux/minmax.h>',after)

    def test_module_consumer_explicitly_reaches_existing_native_init_owner(self):
        source='#include <linux/module.h>\nstatic int __init f(void){return 0;}\n'
        self.assertIn('#include <linux/init.h>',ns.adapt_includes(source,'drivers/gpu/drm/display/drm_display_helper_mod.c'))
        self.assertNotIn('#include <linux/init.h>',ns.adapt_includes(source,'drivers/gpu/drm/display/drm_display_helper_mod.c',3))

    def test_comments_and_header_names_do_not_authorize_minmax_dependency(self):
        source='#include <linux/minimum.h>\n/* min(x,y) */\nconst char *s="max(x,y)";\n'
        self.assertEqual(ns.adapt_includes(source,'drivers/gpu/drm/a.c'),source)


C=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <linux/minmax.h>
int main(void) {
 int x=4,y=9,z=-2;
 assert(@min@(x++,y++)==4 && x==5 && y==10);
 assert(@max@(x++,y++)==10 && x==6 && y==11);
 assert(@min3@(x,y,z)==-2 && @max3@(x,y,z)==11);
 puts("CASE_PASS single_evaluation_and_three_values");
 uint64_t a=(UINT64_C(1)<<60)+13,b=a+21;
 assert(@min@(a,b)==a && @max@(a,b)==b);
 assert(@min_t@(uint64_t,a,b)==a && @max_t@(uint64_t,a,b)==b);
 _Static_assert(sizeof(@min@(a,b))==sizeof(uint64_t),"inferred full width");
 puts("CASE_PASS full_width_and_explicit_types");
 unsigned int u=3; unsigned short small=2;
 assert(@min@(u,0)==0 && @min@(small,z)==-2);
 assert(@umin@(u,0)==0 && @umax@(u,0)==3);
 puts("CASE_PASS source_permitted_signedness");
 x=-3; assert(@clamp@(x++,0,10)==0 && x==-2);
 assert(@clamp_t@(uint64_t,b,a,b+1)==b);
 assert(@clamp_val@(u,0,2)==2 && @min_not_zero@(0,7)==7);
 puts("CASE_PASS clamp_and_zero_rules");
 const int values[]={7,-2,15,4}; const int *p=values;
 assert(@min_array@(values,4)==-2 && @max_array@(p,4)==15);
 puts("CASE_PASS const_array_and_pointer");
 uint32_t start=UINT32_MAX-3;
 assert(@in_range@((uint32_t)0,start,(uint32_t)8));
 assert(!@in_range@((uint32_t)4,start,(uint32_t)8));
 assert(@in_range@((uint64_t)0,UINT64_MAX-3,UINT64_C(8)));
 puts("CASE_PASS source_modular_range_rules");
 x=4;y=9; @swap@(x,y); assert(x==9 && y==4);
 assert(@MIN@(3,7)==3 && @MAX@(3,7)==7);
 assert(@MIN_T@(uint64_t,1,2)==1 && @MAX_T@(uint64_t,1,2)==2);
 puts("CASE_PASS swap_and_constant_only_macros");
 puts("LINUX_MINMAX_PRIMARY_MACROS_PASS count=7");
 return 0;
}
'''


def native(linux,output):
    ns.require_native_hp()
    linux=linux.resolve(strict=True)
    if (not output.is_absolute() or output.exists() or output.is_symlink() or
            not output.parent.is_dir() or output.resolve().is_relative_to(linux)):
        raise ValueError('new absolute native model evidence directory required')
    mapping=ns.bindings(linux)
    before=ns.frozen(linux,'include/linux/minmax.h')
    if ns.sha(before.encode())!=ns.MINMAX_SHA256:raise ValueError('wrong primary minmax source')
    backend,inputs=ns.minmax_backend(linux,mapping)
    policy_path=ROOT/'docs/evidence/HP_NATIVE_INODE_OWNER_20261023.json'
    policy_bytes=policy_path.read_bytes()
    native_flags=json.loads(policy_bytes)['native_make_values']['CFLAGS'].split()
    model_policy=['-Wno-type-limits','-Wno-sign-compare']
    if not {'-Werror',*model_policy}<=set(native_flags):
        raise ValueError('recorded native kernel warning policy is not available')
    header=ns.translate(ns.adapt_includes(before,'include/linux/minmax.h'),mapping)
    output.mkdir(mode=0o700)
    include=output/'include/linux';include.mkdir(parents=True)
    (include/'minmax.h').write_text(header,encoding='utf8',newline='\n')
    (output/'minmax.positive.h').write_text(header,encoding='utf8',newline='\n')
    (include/'minmax_netbsd.h').write_bytes(backend)
    # Explicit delegated userland scalar/annotation model. All comparison,
    # inferred-type, signedness, single-evaluation and assertion algorithms
    # below come from the complete pinned inputs, not test reimplementations.
    (include/'types.h').write_text('#include <stdbool.h>\n#include <stdint.h>\ntypedef uint32_t u32; typedef uint64_t u64;\n')
    (include/'compiler.h').write_text('#ifndef MINMAX_MODEL_COMPILER\n#define MINMAX_MODEL_COMPILER\n'
        '#define '+mapping['__noreturn']+' __attribute__((__noreturn__))\n'
        '#define '+mapping['__compiletime_error']+'(message) __attribute__((__error__(message)))\n#endif\n')
    for name in ('const.h','build_bug.h'):
        (include/name).write_text('/* Native APIs not invoked by this private macro family. */\n')
    program=C
    for name in ns.MINMAX_PUBLIC:program=program.replace('@'+name+'@',mapping[name])
    source=output/'test.c';source.write_text(program,encoding='utf8',newline='\n')
    # Match the two already recorded native kernel warning exceptions. The
    # signedness negative still MUST emit the genuine Linux assertion message;
    # an unrelated compiler warning/failure is not accepted as that proof.
    flags=['/usr/bin/cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',*model_policy,'-UNDEBUG',
           '-fsanitize=undefined','-fno-sanitize-recover=undefined','-I',str(output/'include')]
    env=dict(os.environ,LC_ALL='C',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    report={'state':'RUNNING','linux_pin':ns.PIN,'compiler_backend_frozen_sha256':inputs,
            'minmax_sha256':ns.MINMAX_SHA256,'backend_sha256':ns.sha(backend),'checks':[],
            'model_warning_policy':{'flags':model_policy,'source':str(policy_path),
                                    'source_sha256':ns.sha(policy_bytes),'kernel_flags_modified':False},
            'limitation':'HP native userland primary-macro model; no kernel ABI or driver acceptance.'}
    def compile_case(name,code,need=None):
        path=output/(name+'.c');path.write_text(code,encoding='utf8',newline='\n')
        command=flags+[str(path),'-o',str(output/name)]
        result=subprocess.run(command,text=True,capture_output=True,env=env,timeout=90)
        (output/(name+'.compile.log')).write_text(result.stdout+result.stderr)
        row={'name':name,'command':command,'exit':result.returncode,'source_sha256':ns.sha(code.encode()),
             'minmax_header_sha256':ns.sha((include/'minmax.h').read_bytes()),
             'compile_log_sha256':ns.sha((output/(name+'.compile.log')).read_bytes())}
        row['accepted']=(result.returncode==0 if need is None else result.returncode!=0 and need in result.stderr)
        report['checks'].append(row)
        if not row['accepted']:raise RuntimeError('primary macro compile control failed: '+name)
    try:
        compile_case('positive',program)
        ran=subprocess.run([str(output/'positive')],text=True,capture_output=True,env=env,timeout=30)
        (output/'positive.run.log').write_text(ran.stdout+ran.stderr)
        report['run_exit']=ran.returncode
        if ran.returncode or 'LINUX_MINMAX_PRIMARY_MACROS_PASS count=7' not in ran.stdout:
            raise RuntimeError('primary macro runtime assertions failed')
        compile_case('mixed_sign_rejected',program+'\nint bad(void){int x=-1; unsigned int y=2; return '+mapping['min']+'(x,y);}\n','signedness error')
        compile_case('reversed_bounds_rejected',program+'\nint bad(int x){return '+mapping['clamp']+'(x,10,2);}\n','greater than high limit')
        # Reintroduce raw pre-C23 auto only in the macro owner. GCC12 must
        # diagnose inferred declarations; accepting any failure is insufficient.
        no_auto=header.replace(mapping['auto'],'auto')
        (output/'minmax.no-auto.h').write_text(no_auto,newline='\n')
        (include/'minmax.h').write_text(no_auto,newline='\n')
        compile_case('missing_auto_adapter_rejected',program,'implicit-int')
        broken=header.replace(mapping['__cmp_op_']+'##op','__cmp_op_##op')
        (output/'minmax.broken-paste.h').write_text(broken,newline='\n')
        (include/'minmax.h').write_text(broken,newline='\n')
        compile_case('broken_token_paste_rejected',program,'__cmp_op_')
        report['state']='PASSED'
    except Exception as error:
        report['state']='FAILED';report['error']=str(error)
    finally:
        (include/'minmax.h').write_text(header,encoding='utf8',newline='\n')
    (output/'status.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8',newline='\n')
    print('HP_LINUX_MINMAX_PRIMARY_MACROS_'+report['state'],output)
    return 0 if report['state']=='PASSED' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true');parser.add_argument('--linux-tree',type=Path)
    parser.add_argument('--output',type=Path)
    arguments,remaining=parser.parse_known_args()
    if arguments.native:
        if not arguments.linux_tree or not arguments.output:parser.error('--native requires --linux-tree and --output')
        sys.exit(native(arguments.linux_tree,arguments.output))
    unittest.main(argv=[sys.argv[0],*remaining])
