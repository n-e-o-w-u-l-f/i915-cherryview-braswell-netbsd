#!/usr/bin/env python3
"""Read-only pinned NetBSD mountroot/deferred and i915 candidate-0008 oracle.

This checks source structure and error propagation, not kernel compilation,
callback execution, or device safety. Inputs are content-addressed Git blobs.
"""
import argparse
import hashlib
import json
from pathlib import Path

PIN_NETBSD = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
PIN_LINUX = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
SOURCES = {
    'autoconf': ('netbsd', 'sys/kern/subr_autoconf.c', '5ee8a7998b07fd570d7b1f67d23cdb814de63039'),
    'drvctl': ('netbsd', 'sys/kern/kern_drvctl.c', '5712a8a762d62219deae80c17698bb92f591d43c'),
    'initmain': ('netbsd', 'sys/kern/init_main.c', 'ded47067618eef50fe63f0b2bcde0fa3c970fd48'),
    'i915': ('netbsd', 'sys/external/bsd/drm2/dist/drm/i915/i915_drv.c', 'bf64ff40059fc38188f6f3d7b55bef9793abeb57'),
    'drm': ('netbsd', 'sys/external/bsd/drm2/dist/drm/drm_drv.c', 'f91332cbebb57ab9a6ee3e1955722663df7e4929'),
    'linux': ('linux', 'drivers/gpu/drm/i915/i915_driver.c', 'ce6d20958320c1f91a50678230eb96f88f0b357b'),
    'patch8': ('i915', 'candidates/0008-i915-drm-registration-unwind-netbsd11.patch', '6634a4d122d2e8524a14e60414b5043075caf3a0'),
    'patch9': ('i915', 'candidates/0009-netbsd-opregion-optional-asle-cleanup.patch', 'b257d451560584a86c6f092dcde6b0b69b0e33c8'),
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def take(s: str, begin: str, end: str) -> str:
    assert s.count(begin) == 1, 'non-unique source marker ' + begin
    start = s.index(begin)
    stop = s.index(end, start + len(begin))
    return s[start:stop]


def predicates(d: dict) -> dict:
    a = d['autoconf']
    mountroot = take(a, 'void\nconfig_mountroot(', '/*\n * Process a deferred configuration queue.')
    deferred = take(a, 'void\nconfig_deferred(', 'static void\nconfig_interrupts_thread(')
    process = take(a, 'static void\nconfig_process_deferred(', '/*\n * Manipulate the config_pending semaphore.')
    detach = take(a, 'static int\nconfig_detach_enter(', 'static void\nconfig_detach_exit(')
    register = take(d['i915'], 'static void i915_driver_register(', '/**\n * i915_driver_unregister')
    probe = take(d['i915'], 'int i915_driver_probe(', 'void i915_driver_remove(')
    drm_register = take(d['drm'], 'int drm_dev_register(', 'EXPORT_SYMBOL(drm_dev_register);')
    compat = take(d['drm'], 'static int create_compat_control_link(', 'static void remove_compat_control_link(')
    ld = take(d['linux'], 'static int i915_driver_register(', '/**\n * i915_driver_unregister')
    p8, p9 = d['patch8'], d['patch9']
    return {
        'pinned_drvctl_rescan_processes_all': 'config_deferred(NULL);' in d['drvctl'],
        'pinned_config_deferred_mountroot': 'config_process_deferred(&mountroot_config_queue, dev);' in deferred,
        'generic_deferred_decrements': 'config_pending_decr(dc->dc_dev);' in process,
        'mountroot_enqueues_without_pending_increment': 'TAILQ_INSERT_TAIL(&mountroot_config_queue' in mountroot and 'config_pending_incr(' not in mountroot,
        'detach_does_not_wait_mountroot_queue': 'while (dev->dv_pending || dev->dv_detaching)' in detach and 'mountroot_config_queue' not in detach,
        'boot_starts_and_joins_mountroot_workers': 'config_create_mountrootthreads();' in d['initmain'] and 'config_finalize_mountroot();' in d['initmain'],
        'drm_register_fallible_before_dev_registered': drm_register.index('ret = create_compat_control_link(dev);') < drm_register.index('dev->registered = true;') and 'return -ENOMEM;' in compat,
        'i915_void_register_logs_error': 'if (drm_dev_register(dev, 0) == 0)' in register,
        'i915_probe_ignores_void_register': 'i915_driver_register(dev_priv);' in probe,
        'linux_register_propagates_failure': 'ret = drm_dev_register(&dev_priv->drm, 0);' in ld and 'drm_dev_unregister(&dev_priv->drm);' in ld and 'return ret;' in ld,
        'existing_0008_propagates': '+\tret = drm_dev_register(dev, 0);' in p8 and '+\t\treturn ret;' in p8 and '+\t\tgoto out_cleanup_registration;' in p8,
        'existing_0008_drm_unreg_on_error': '+\t\tdrm_dev_unregister(dev);' in p8,
        '0008_opregion_prerequisite_0009': '+\tintel_opregion_unregister(dev_priv);' in p8 and '+\tsize_t rvds = opregion->rvda ? opregion->asle->rvds : 0;' in p9,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--netbsd-tree', type=Path)
    p.add_argument('--linux-tree', type=Path)
    p.add_argument('--i915-repo', type=Path)
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    if args.self_test:
        assert git_blob_sha(b'hello') == 'b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0'
        assert take('before START middle END after', 'START', 'END') == 'START middle '
        try:
            take('START START END', 'START', 'END')
            raise AssertionError('non-unique marker went undetected')
        except AssertionError as e:
            assert 'non-unique' in str(e)
        print(json.dumps({'status':'SELF_TEST_PASS','tests':3,'native_kernel':'NOT_RUN'}))
        return 0
    roots = {'netbsd':args.netbsd_tree, 'linux':args.linux_tree, 'i915':args.i915_repo}
    if any(x is None for x in roots.values()):
        p.error('require all three source roots, or --self-test')
    content = {}
    for key, (root, rel, sha) in SOURCES.items():
        blob = (roots[root] / rel).read_bytes()
        real = git_blob_sha(blob)
        if real != sha:
            print(json.dumps({'status':'PIN_MISMATCH','file':rel,'expected':sha,'actual':real}))
            return 2
        content[key] = blob.decode('utf-8')
    facts = predicates(content)
    passed = sum(facts.values())
    print(json.dumps({'status':'SOURCE_CONTRACT_PASS' if passed == len(facts) else 'CONTRACT_CHANGED',
                      'facts':facts,'passed':passed,'total':len(facts),
                      'kernel_compilation':'NOT_RUN','HP_runtime':'NOT_RUN'}, indent=2))
    return 0 if passed == len(facts) else 3


if __name__ == '__main__':
    raise SystemExit(main())
