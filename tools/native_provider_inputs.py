"""Reviewed native FILE provider identities and independent dependency admission."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from native_hp_build import core_toolchain_receipt
from native_source_archive import (
    ARCHIVE_SHA256, PIN, archive_expectations, bind_dependencies,
    declared_configuration_inputs, digest, recheck_prior_artifacts,
    selected_generated_configuration, source_relative)

REPOSITORY = Path(__file__).resolve().parents[1]
CONTRACT_PATH = 'compat/native-file/provider-inputs-f33.json'
CONTRACT_SHA256 = 'f806ae775782b60513fae522bbe3c3325858152e77e39eb6ccea0f6f405a12b3'
ANON_CONTRACT_PATH = 'compat/native-file/provider-inputs-f35-anon.json'
ANON_CONTRACT_SHA256 = 'c45f3ab9f59602955ec5ebe27974a926316787faa0ff57935e3f1c95ac00214d'
FILE_CONTRACT_PATH = 'compat/native-file/provider-inputs-f37-file.json'
FILE_CONTRACT_SHA256 = 'a79eaf94d6f0c9b0ee0b64ed998f7e158b6ad0cb5b305878c79ef1c49a4f2e09'
TASK_CONTRACT_PATH = 'compat/native-runtime/task/provider-inputs-f39-task.json'
TASK_CONTRACT_SHA256 = '5709061e886f4334c32b2485b98a38c8854ab3929e27ff41ce23192535c273df'
TASK_WORKER_CONTRACT_PATH = 'compat/native-runtime/task/provider-inputs-f41-task-worker.json'
TASK_WORKER_CONTRACT_SHA256 = '0741fbe18dfd9600edad6cc490e4f9609fcf706c461e21c067cb1a132adeb0a4'
WAIT_CONTRACT_PATH = 'compat/native-runtime/wait-contracts/provider-inputs-f44-wait.json'
WAIT_CONTRACT_SHA256 = '5561d9005df2e8018262fb81437ae5abc88e2cb13a6f7306f604a3d4e728309c'
POLL_CONTRACT_PATH = 'compat/native-file/provider-inputs-f46-poll.json'
POLL_CONTRACT_SHA256 = '9f477521b790e036aaa0dbfddccee1c1ebb06bf62c6034c3d5b4d8b4e5e0db60'
WORKER_CONTRACT_PATH = 'compat/native-runtime/worker-contracts/provider-inputs-f50-worker.json'
WORKER_CONTRACT_SHA256 = '996f8a34b35e4345c16814f5d72dbd0bdbb1691bdd9a281b3a0bd9fb18560dc3'
_WORKER_PROVENANCE_PATH = 'compat/native-runtime/worker-f49/provenance.json'
_WORKER_PROVENANCE_SHA256 = '91f22a4fda6bdb0c9e61020acf31ac698c7ee009d65b07d58c7fa55c22a07fa1'
_WORKER_INPUT_COMMIT = 'e7d7100c44322d3209d8f43d1d3a3842b52b340b'
_WORKER_INPUT_ROLES = {'compat/native-runtime/worker-f49/linux_kthread.c': 'translation_unit',
 'compat/native-runtime/worker-f49/include/linux/kthread.h': 'worker_header',
 'compat/native-runtime/include/linux/sched.h': 'task_mapping_header',
 'compat/native-runtime/include/linux/task_netbsd.h': 'task_mapping_header',
 'compat/native-runtime/include/linux/raw_spinlock.h': 'task_mapping_header',
 'compat/native-runtime/task/sched.h': 'task_scheduler_header',
 'compat/native-runtime/task/task_netbsd.h': 'task_header',
 'compat/linux/raw_spinlock.h': 'raw_spinlock_header',
 'compat/native-runtime/worker-f49/provenance.json': 'generation_proof_owner',
 'tools/recover_native_worker.py': 'generation_proof_owner',
 'compat/native-runtime/worker/INTEGRATION.txt': 'generation_proof_owner',
 'compat/native-runtime/worker/base/kthread.h': 'generation_proof_owner',
 'compat/native-runtime/worker/base/linux_kthread.c': 'generation_proof_owner',
 'compat/native-runtime/worker/generate.py': 'generation_proof_owner',
 'compat/native-runtime/worker/worker.inc': 'generation_proof_owner',
 'compat/native-runtime/worker/worker_header.inc': 'generation_proof_owner',
 'patches/0032-netbsd-linux-task-wait-worker.patch': 'generation_proof_owner'}
_WORKER_SOURCE_IDENTITIES = {'compat/native-runtime/worker/INTEGRATION.txt': {'blob': '2ecf30dbfba159795fee0a2951cf1dc2c3f9d30f',
                                                  'role': 'historical_and_final_patch_identity_record',
                                                  'sha256': '641fea8eb59177617cd1e54dd60bab45a59dec1c97205a6815bc74b859d7a12b',
                                                  'size': 6579},
 'compat/native-runtime/worker/base/kthread.h': {'blob': '74af400efc77e55c821f11e7bafd7a499e141962',
                                                 'role': 'pinned_native_header',
                                                 'sha256': '4384d635d5049d38bd322009007b04808afeb30e4c99c0e484ba95bfbd10933b',
                                                 'size': 2546},
 'compat/native-runtime/worker/base/linux_kthread.c': {'blob': 'a7735f8eb62a1ae697756deed51c718396e9b579',
                                                       'role': 'pinned_native_source',
                                                       'sha256': '566260787e456fe3ea40fb50f2cc93500faf0ccb4927a0a5e977777ad89d61bf',
                                                       'size': 7207},
 'compat/native-runtime/worker/generate.py': {'blob': '2ac669aba5f269d5e9b5c49fdfb43a2aaf3b3fde',
                                              'role': 'historical_recipe_read_only_not_executed',
                                              'sha256': '722d9acb293caa2a1447a61656f954e82f9a54be63f4628362ad7d1e9180274b',
                                              'size': 8005},
 'compat/native-runtime/worker/worker.inc': {'blob': '54576a3a96d24f51788c40ae38fbb1f9b2f5d4e4',
                                             'role': 'embedded_worker_implementation_witness',
                                             'sha256': '2ad653da9cb181aa9966e4e0e98b12c3fa0c197574f9d4f0021b9e744359001d',
                                             'size': 10512},
 'compat/native-runtime/worker/worker_header.inc': {'blob': '70aa0ef127e2b4c8f242f5868d6efda2fdd13c6f',
                                                    'role': 'embedded_worker_declaration_witness',
                                                    'sha256': '9f3887613605b06fad70f45bd69f92cd7015de7775a859082bbedb991a2dc1a2',
                                                    'size': 2098},
 'patches/0032-netbsd-linux-task-wait-worker.patch': {'blob': '20e0b8bdcaaa29b5050e1ac353086604308f0cad',
                                                      'role': 'selected_final_patch_authority',
                                                      'sha256': '9b53ce73daba8b6937c54209e2ff28087775409c9be2c386a97301f3781737fd',
                                                      'size': 130848}}
_WORKER_OUTPUT_IDENTITIES = {'include/linux/kthread.h': {'blob': '87bfe919c26654f034351f97acffc88d138cd861',
                             'sha256': '97c094ab5fbc3688334875500c23d5053186d35e6342d2668ce63659335b8814',
                             'size': 4700},
 'linux_kthread.c': {'blob': 'c8f72ebd33119c9a4e47cc58b3397074c0523887',
                     'sha256': '31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274',
                     'size': 19566}}
_WORKER_SECTIONS = {'sys/external/bsd/drm2/include/linux/kthread.h': {'hunks': 2,
                                                   'sha256': 'cd3bf675e1335dfe671d832178ce6a9828d198d7b4abc80387378f86ed489477',
                                                   'size': 2431},
 'sys/external/bsd/drm2/linux/linux_kthread.c': {'hunks': 25,
                                                 'sha256': '25f4bae7984a11a355b06aefd2ba7ac37f424ca0b4390d89d95942f715c2091a',
                                                 'size': 17013}}
_WORKER_RECOVERY_TOOL_SHA256 = '83a2a0190b0b66714dedbfac9c025e2ba6828f00f64362fbaf65519329fc4379'
_WORKER_AUDIT_SHA256 = '3b7fd8d098fc40b9d4401f18121d461fb7821e0477587aba0843413bb73454ed'
_WORKER_DEFINITION_OWNERSHIP = {'linux_kthread_wake_locked': {'declaration': 'include/linux/kthread.h:132',
                               'file': 'linux_kthread.c',
                               'line': 415},
 'private_kthread_structure': {'file': 'linux_kthread.c', 'line': 55},
 'private_static_spawn': {'file': 'linux_kthread.c', 'line': 183},
 'task_system_fini_checked': {'assertion_line': 87, 'call_line': 86, 'file': 'linux_kthread.c'}}
_WORKER_HISTORICAL_RECIPE = {'executed': False,
 'limitation': 'Its fini replacement discards the task-system return; the final selected patch retains '
               'the checked return.',
 'path': 'compat/native-runtime/worker/generate.py'}
_WORKER_HISTORICAL_INTEGRATION = {'interpretation': 'Historical candidate claims remain historical; the final selected patch output '
                   'matches the later final identity record. No historical generator, compile or link '
                   'is reproduced.',
 'path': 'compat/native-runtime/worker/INTEGRATION.txt'}
_WORKER_OPEN_GATES = ['separate exact provider input contract',
 'actual native preprocessing and compilation',
 'Task/Wait/Worker ownership and link closure',
 'worker stop/park/drain/lifetime behavior',
 'full kernel and physical hardware acceptance']
_WORKER_SCOPE = {'applied_owner_sections': 2,
 'booted': False,
 'historical_recipe_executed': False,
 'installed': False,
 'linked': False,
 'native_compilation': 'NOT_RUN',
 'native_preprocessing': 'NOT_RUN',
 'patch_owner_sections': 14,
 'runtime': 'NOT_RUN',
 'source_mode': 'PINNED_NETBSD_BLOBS_PLUS_EXACT_TWO_REVIEWED_PATCH_SECTIONS',
 'state': 'RECOVERED_SOURCE_ONLY_NOT_INSTALLED',
 'unexecuted_owner_sections': 12,
 'whole_patch_applied': False}
_WORKER_REQUIRED_INPUTS = frozenset(name for name, role in _WORKER_INPUT_ROLES.items()
                                    if role != 'generation_proof_owner')
_WORKER_PROVENANCE_KEYS = frozenset(['applied_owner_sections', 'booted', 'definition_ownership', 'files', 'historical_integration', 'historical_recipe', 'historical_recipe_executed', 'installed', 'linked', 'native_compilation', 'native_preprocessing', 'netbsd_pin', 'open_gates', 'operations', 'patch_owner_sections', 'recovery_tool_sha256', 'repository_input_commit', 'repository_inputs', 'runtime', 'schema', 'selected_sections', 'source_mode', 'state', 'unexecuted_owner_sections', 'whole_patch_applied'])
WAIT_LINUX_PIN = 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'
_WAIT_INPUT_ROLES = {
    'compat/native-runtime/wait-f43/linux_wait.c': 'translation_unit',
    'compat/native-runtime/wait-f43/include/linux/wait.h': 'wait_header',
    'compat/native-runtime/include/linux/sched.h': 'task_mapping_header',
    'compat/native-runtime/include/linux/task_netbsd.h': 'task_mapping_header',
    'compat/native-runtime/include/linux/raw_spinlock.h': 'task_mapping_header',
    'compat/native-runtime/task/sched.h': 'task_scheduler_header',
    'compat/native-runtime/task/task_netbsd.h': 'task_header',
    'compat/linux/raw_spinlock.h': 'raw_spinlock_header',
    'compat/native-runtime/wait-inputs-f43/include/linux/wait.h': 'generation_proof_owner',
    'compat/native-runtime/wait-inputs-f43/kernel/sched/wait.c': 'generation_proof_owner',
    'compat/native-runtime/wait-inputs-f43/provenance.json': 'generation_proof_owner',
    'compat/native-runtime/wait-f43/provenance.json': 'generation_proof_owner',
    'compat/native-runtime/task/generate_wait.py': 'generation_proof_owner',
    'compat/native-runtime/task/SOURCE_SHA256.json': 'generation_proof_owner',
    'tools/recover_native_wait.py': 'generation_proof_owner',
}
_POLL_INPUT_ROLES = dict(_WAIT_INPUT_ROLES)
_POLL_INPUT_ROLES.update({'compat/native-runtime/wait-f43/linux_wait.c': 'generation_proof_owner', 'compat/native-file/linux_poll_owner.c': 'translation_unit', 'compat/native-file/linux_poll.c': 'poll_implementation_owner', 'compat/native-file/include/linux/poll_netbsd.h': 'poll_header', 'compat/native-file/include/linux/file_netbsd.h': 'file_header', 'compat/native-file/include/linux/fs_netbsd.h': 'file_header', 'compat/native-file/include/linux/file_api_netbsd.h': 'file_header', 'compat/native-file/include/linux/file_ref_netbsd.h': 'file_header', 'compat/native-mm/include/linux/mm_abi_types_netbsd.h': 'mm_abi_header', 'compat/native-uio/include/linux/kiocb_netbsd.h': 'uio_header', 'compat/native-runtime/task/task_entry_netbsd.h': 'task_entry_header', 'compat/native-entry/task_entry.inc': 'api_definition_owner'})
_POLL_REQUIRED_INPUTS = frozenset(name for name, role in _POLL_INPUT_ROLES.items()
                                  if role not in ('generation_proof_owner', 'api_definition_owner'))
_WAIT_REQUIRED_INPUTS = frozenset(name for name, role in _WAIT_INPUT_ROLES.items()
                                  if role != 'generation_proof_owner')
_WAIT_PROVENANCE_PATH = 'compat/native-runtime/wait-f43/provenance.json'
_WAIT_PROVENANCE_SHA256 = 'a84ac39db9642f7a935a25a6ac3b0721b568be6132a8221cab42b454f7972078'
_WAIT_SOURCE_IDENTITIES = {
    'include/linux/wait.h': {'size': 45202, 'sha256': 'f9f53a02fd25a1a1fefdc41310285975d5c1fdce1a1b62282cc05e737ae96417', 'git_blob': '7e215330199cfea27008f718e0336d0f48bfe17d', 'source_url': 'https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/include/linux/wait.h'},
    'kernel/sched/wait.c': {'size': 14840, 'sha256': '05a9c8d9b1b4cb3a63e1dd59744adf24c8912d108307f46d7e3a6b1f26013e5f', 'git_blob': 'd033f600f48c6fc3a0a088ea5d9f6ed95ec4c86e', 'source_url': 'https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/kernel/sched/wait.c'},
}
_WAIT_OUTPUT_IDENTITIES = {
    'include/linux/wait.h': {'size': 49625, 'sha256': '61ef59279676174b3394e88451ff828a83bff7c50d679b4a946d3daee45dfa86'},
    'linux_wait.c': {'size': 14091, 'sha256': '4a933c0bb0cbf5c2483c22d8fb7a36b7166d0b52b2e30bf9223d69d9a8cd0c69'},
}
_WAIT_WITNESSES = {
    'recipe': {'path': 'compat/native-runtime/task/generate_wait.py', 'sha256': '598d3de2afdf1e6c02ff8aecdde0f4a83c7f32341adbfc791b367a007df378d6', 'git_blob': '384872c7c87595d62497227d7c2c8aaff31e2dd0'},
    'historical_ledger': {'path': 'compat/native-runtime/task/SOURCE_SHA256.json', 'sha256': '99b37dca5385fa243e3bad9867a36405caab52804423010690c5427193c82662', 'git_blob': '0b1cf16eb8cd424c2c87c4d7e6d19513edc6771f'},
}
_WAIT_RECOVERY_TOOL_SHA256 = 'daa986375fe841baf5cf85f80dadbf675c9030695a221a065dbd8ea70b45b521'
_WAIT_PROVENANCE_KEYS = frozenset(['schema', 'state', 'linux_pin', 'netbsd_pin', 'source_mode', 'inputs', 'witnesses', 'recovery_tool_sha256', 'files', 'operations', 'open_gates', 'native_preprocessing', 'native_compilation', 'linked', 'installed', 'runtime'])
_WAIT_OPEN_GATES = ['fatal-only sleeps', 'static native waitqueue initializer', 'PID/mm/IO accounting', 'generic native boundary attachment', 'module unload/owner draining', 'sync/current-CPU scheduler hints', 'poll registrations/RCU/free lifetime', 'bit wait/lock/IO/timeouts']
_WAIT_AUDIT_SHA256 = '60cb1ad3622830b964aeb95a3b37645e498abf6ff744e78159bfb02e5d051964'
_TASK_INPUT_ROLES = {
    'compat/native-runtime/task/linux_task.c': 'translation_unit',
    'compat/native-runtime/task/task_entry_netbsd.h': 'task_entry_header',
    'compat/native-runtime/include/linux/sched.h': 'task_mapping_header',
    'compat/native-runtime/include/linux/task_netbsd.h': 'task_mapping_header',
    'compat/native-runtime/include/linux/raw_spinlock.h': 'task_mapping_header',
    'compat/native-runtime/task/sched.h': 'task_scheduler_header',
    'compat/native-runtime/task/task_netbsd.h': 'task_header',
    'compat/linux/raw_spinlock.h': 'raw_spinlock_header',
    'compat/native-entry/task_entry.inc': 'task_fragment',
    'compat/native-file/task_entry_preallocated.inc': 'task_fragment',
    'compat/native-file/task_quiesce_retained.inc': 'task_fragment',
}
_TASK_FRAGMENTS = frozenset(name for name, role in _TASK_INPUT_ROLES.items()
                            if role == 'task_fragment')
_TASK_WORKER_INPUT_ROLES = {
    'compat/native-runtime/task/linux_task.c': 'task_implementation_owner',
    'compat/native-runtime/task/task_entry_netbsd.h': 'task_entry_header',
    'compat/native-runtime/include/linux/sched.h': 'task_mapping_header',
    'compat/native-runtime/include/linux/task_netbsd.h': 'task_mapping_header',
    'compat/native-runtime/include/linux/raw_spinlock.h': 'task_mapping_header',
    'compat/native-runtime/task/sched.h': 'task_scheduler_header',
    'compat/native-runtime/task/task_netbsd.h': 'task_header',
    'compat/linux/raw_spinlock.h': 'raw_spinlock_header',
    'compat/native-entry/task_entry.inc': 'task_fragment',
    'compat/native-file/task_entry_preallocated.inc': 'task_fragment',
    'compat/native-file/task_quiesce_retained.inc': 'task_fragment',
    'compat/native-runtime/task/linux_task_worker_owner.c': 'translation_unit',
    'compat/native-runtime/task/task_worker_wake_netbsd.h': 'task_worker_api_header',
    'compat/native-runtime/worker/worker_header.inc': 'api_definition_owner',
    'compat/native-runtime/worker/worker.inc': 'api_definition_owner',
}
_TASK_WORKER_REQUIRED_INPUTS = (
    'compat/native-runtime/task/linux_task.c',
    'compat/native-runtime/task/task_worker_wake_netbsd.h')


def regular_bytes(path):
    """Read one real regular file through one descriptor, without following a link."""
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('regular input required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read()
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or path.is_symlink():
            raise ValueError('input changed during read: ' + str(path))
        return raw
    finally:
        os.close(fd)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def reviewed_contract_sha256(path, repository=REPOSITORY):
    """Select only an explicitly reviewed source-owned path and its fixed digest."""
    repository = Path(repository).resolve(strict=True)
    path = Path(path)
    if not path.is_symlink():
        resolved = path.resolve(strict=True)
        for relative, expected in ((CONTRACT_PATH, CONTRACT_SHA256),
                                   (ANON_CONTRACT_PATH, ANON_CONTRACT_SHA256),
                                   (FILE_CONTRACT_PATH, FILE_CONTRACT_SHA256),
                                   (TASK_CONTRACT_PATH, TASK_CONTRACT_SHA256),
                                   (TASK_WORKER_CONTRACT_PATH, TASK_WORKER_CONTRACT_SHA256),
                                   (WAIT_CONTRACT_PATH, WAIT_CONTRACT_SHA256),
                                   (POLL_CONTRACT_PATH, POLL_CONTRACT_SHA256),
                                   (WORKER_CONTRACT_PATH, WORKER_CONTRACT_SHA256)):
            if resolved == repository / relative:
                return expected
    raise ValueError('a reviewed source-owned native FILE provider contract is required')


def load_contract(path, repository=REPOSITORY):
    expected = reviewed_contract_sha256(path, repository)
    raw = regular_bytes(path)
    if sha_bytes(raw) != expected:
        raise ValueError('provider contract bytes differ from reviewed identity')
    document = json.loads(raw, object_pairs_hook=unique_object)
    if document['netbsd_pin'] != PIN or document['archive_sha256'] != ARCHIVE_SHA256:
        raise ValueError('provider contract native archive identity differs')
    return document


def git_environment():
    """Identity reads cannot inherit another index, worktree, or replacement object."""
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_')}
    environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
                       GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    return environment


def repository_inputs(repository, contract):
    repository = Path(repository).resolve(strict=True)
    result = {}
    for relative, expected in contract['repository_inputs'].items():
        source_relative(relative)
        path = repository / relative
        if path.is_symlink() or path.resolve(strict=True) != path:
            raise ValueError('provider input path aliases another file: ' + relative)
        raw = regular_bytes(path)
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if sha_bytes(raw) != expected['sha256'] or blob != expected['blob']:
            raise ValueError('provider working bytes differ: ' + relative)
        tree = subprocess.check_output(
            ['git', '--no-replace-objects', '-C', str(repository), 'ls-tree',
             '--full-tree', contract['repository_commit'], '--', relative],
            env=git_environment(), timeout=30).decode().rstrip('\n')
        required = '100644 blob ' + expected['blob'] + '\t' + relative
        if tree != required:
            raise ValueError('provider commit/path/blob differs: ' + relative)
        result[str(path)] = dict(kind='repository', relative=relative, **expected)
    return result


def selected_inputs(contract, repository, source, provider, units, includes):
    repository, source = Path(repository), Path(source)
    if Path(provider) != repository / contract['provider_root']:
        raise ValueError('the reviewed native FILE provider root is required')
    if list(units) != contract['units']:
        raise ValueError('provider units differ from the reviewed selection')
    required = ([repository / name for name in contract['repository_include_roots']] +
                [source / name for name in contract['native_include_roots']])
    if includes and list(map(Path, includes)) != required:
        raise ValueError('provider include roots/order differs from reviewed roles')
    for path in required:
        if not path.is_dir() or path.resolve(strict=True) != path:
            raise ValueError('provider include root is missing or aliased: ' + str(path))
    return required


def frozen_hashes(mapping, label):
    for name, expected in mapping.items():
        if sha_bytes(regular_bytes(name)) != expected:
            raise ValueError(label + ' drift: ' + name)


def verify_core(path, contract, source, obj, tools, core=None):
    """Hash and parse the same payload, then recheck all frozen F32 inputs."""
    path, source, obj = Path(path), Path(source), Path(obj)
    raw = regular_bytes(path)
    if sha_bytes(raw) != contract['core_status_sha256']:
        raise ValueError('reviewed full F32 core receipt identity required')
    parsed = json.loads(raw, object_pairs_hook=unique_object)
    if core is not None and parsed != core:
        raise ValueError('core receipt changed')
    core = parsed
    if (core.get('state') != 'PASS' or core.get('stage') != 'COMPLETE'
            or core.get('netbsd_pin') != PIN
            or set(core['objects']) != {'sys_generic', 'kern_descrip', 'netbsd32_ioctl'}):
        raise ValueError('completed three-owner F32 core required')
    core_toolchain_receipt(core, tools)
    overlay = path.parent / 'source'
    frozen_hashes({str(overlay / rel): value for rel, value
                   in core['patched_inputs'].items()}, 'core overlay')
    for step in core['patch_chain']:
        frozen_hashes({step['patch']: step['patch_sha256'],
                       step['contract']: step['contract_sha256']}, 'core patch input')
    declared, origins = selected_generated_configuration(core['patch_chain'], True)
    if (declared != core['declared_generated_configuration']
            or origins != core['generated_configuration_contracts']
            or declared_configuration_inputs(obj, declared)
            != core['declared_generated_configuration_inputs']):
        raise ValueError('core declared configuration differs')
    frozen_hashes(core['generated_configuration_sha256'], 'core configuration')
    frozen_hashes(core['declared_generated_configuration_inputs'], 'core declared input')
    provenance = core['source_provenance']
    if (provenance['mode'] != 'ARCHIVE_USED_SUBSET'
            or provenance['netbsd_pin'] != PIN
            or provenance['archive_sha256'] != ARCHIVE_SHA256):
        raise ValueError('actual archive-backed F32 core required')
    frozen_hashes({str(source / relative): value for relative, value
                   in provenance['verified_source_members'].items()}, 'core archive source')
    for unit, row in core['objects'].items():
        frozen_hashes({str(path.parent / (unit + '.o')): row['sha256']}, 'core object')
        frozen_hashes(row['headers_sha256'], 'core header')
        before = core['precompile_dependencies'][unit]
        if row['dependency_proof'] != before:
            raise ValueError('core dependency proof differs from independent scan')
        rebound = bind_dependencies(set(map(Path, before)), source, overlay, obj,
                                    core['patched_inputs'], declared)
        if rebound != before:
            raise ValueError('core dependency/configuration identity drift')
    recheck_prior_artifacts(obj, core['prior_artifacts'])
    frozen_hashes({str(obj / 'Makefile'): core['configured_makefile_sha256'],
                   str(obj / 'netbsd'): core['prior_kernel_sha256']}, 'native configuration/kernel')
    return core


def provider_dependencies(paths, repository, repository_bindings, source, overlay, obj,
                          patched, declared):
    """Directory location never admits a repository input without its reviewed blob."""
    repository = Path(repository).resolve(strict=True)
    native, result = set(), {}
    for path in paths:
        path = Path(path).resolve(strict=True)
        if path.is_relative_to(repository):
            if str(path) not in repository_bindings:
                raise ValueError('unreviewed repository dependency: ' + str(path))
            row = repository_bindings[str(path)]
            if row.get('role') == 'api_definition_owner':
                raise ValueError('API definition owner is not a provider dependency: ' + str(path))
            if row.get('role') == 'generation_proof_owner':
                raise ValueError('generation proof owner is not a provider dependency: ' + str(path))
            raw = regular_bytes(path)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if sha_bytes(raw) != row['sha256'] or blob != row['blob']:
                raise ValueError('reviewed repository dependency drift: ' + str(path))
            result[str(path)] = row
        else:
            native.add(path)
    if native:
        result.update(bind_dependencies(native, source, overlay, obj, patched, declared))
    if not result:
        raise ValueError('empty provider dependency proof')
    return result


def recheck_provider_dependencies(paths, before, *arguments):
    current = provider_dependencies(paths, *arguments)
    if current != before:
        raise ValueError('actual provider dependencies differ from independent scan')
    return current


def native_archive_expectations(core, bindings):
    native = {path: row for path, row in bindings.items() if row['kind'] != 'repository'}
    return archive_expectations(core['source_provenance']['verified_source_members'], native)


def worker_input_policy(contract=None, reviewed_sha256=None):
    """Only the eighth fixed selection admits the complete recovered Worker owner."""
    if reviewed_sha256 != WORKER_CONTRACT_SHA256:
        rows = contract.get('repository_inputs', {}) if isinstance(contract, dict) else {}
        if (isinstance(contract, dict) and contract.get('units') == ['linux_kthread.c'] or
                isinstance(rows, dict) and any(isinstance(row, dict) and row.get('role') == 'worker_header'
                                               for row in rows.values())):
            raise ValueError('Worker inputs require the exact reviewed Worker contract')
        return []
    if not isinstance(contract, dict):
        raise ValueError('reviewed Worker provider identity/shape differs')
    rows = contract.get('repository_inputs')
    shape = dict(schema=1, provider_root='compat/native-runtime/worker-f49',
                 units=['linux_kthread.c'], required_patched_headers=[],
                 repository_include_roots=['compat/native-runtime/worker-f49/include',
                                           'compat/native-runtime/include'],
                 native_include_roots=['sys/external/bsd/common/include',
                                       'sys/external/bsd/drm2/include'],
                 generation_provenance_sha256=_WORKER_PROVENANCE_SHA256)
    if (type(contract.get('schema')) is not int or
            any(contract.get(key) != value for key, value in shape.items()) or
            not isinstance(rows, dict) or any(not isinstance(row, dict) for row in rows.values()) or
            {name: row.get('role') for name, row in rows.items()} != _WORKER_INPUT_ROLES):
        raise ValueError('reviewed Worker provider identity/shape differs')
    return sorted(_WORKER_REQUIRED_INPUTS)


def require_worker_inputs(bindings, repository, contract=None, reviewed_sha256=None):
    for name in worker_input_policy(contract, reviewed_sha256):
        expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
        if bindings.get(str(Path(repository) / name)) != expected:
            raise ValueError('provider did not consume the required Worker input: ' + name)


def verify_worker_generation(repository, contract, repository_bindings, reviewed_sha256=None):
    """Cross-link same-read F49 source evidence; never import/run producer or recipe."""
    if not worker_input_policy(contract, reviewed_sha256):
        return {}
    repository = Path(repository).resolve(strict=True)
    try:
        if set(repository_bindings) != {str(repository / name) for name in _WORKER_INPUT_ROLES}:
            raise ValueError('exactly seventeen Git-bound rows required')

        def read_bound(name):
            expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
            if repository_bindings.get(str(repository / name)) != expected:
                raise ValueError('Git-bound generation row differs: ' + name)
            path = repository / name
            if path.is_symlink() or path.resolve(strict=True) != path:
                raise ValueError('generation input is aliased: ' + name)
            raw = regular_bytes(path)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if (sha_bytes(raw) != expected['sha256'] or blob != expected['blob'] or
                    path.is_symlink() or path.resolve(strict=True) != path):
                raise ValueError('same-read generation SHA256/blob differs: ' + name)
            return raw

        payloads = {name: read_bound(name) for name in _WORKER_INPUT_ROLES}
        raw = payloads[_WORKER_PROVENANCE_PATH]
        if sha_bytes(raw) != contract['generation_provenance_sha256']:
            raise ValueError('generation provenance pin differs')
        document = json.loads(raw, object_pairs_hook=unique_object)
        if (not isinstance(document, dict) or set(document) != _WORKER_PROVENANCE_KEYS or
                type(document.get('schema')) is not int):
            raise ValueError('generation scope/pins/flags differ')
        expected = dict(_WORKER_SCOPE)
        expected.update(schema=1, netbsd_pin=PIN, repository_input_commit=_WORKER_INPUT_COMMIT,
            repository_inputs=_WORKER_SOURCE_IDENTITIES, files=_WORKER_OUTPUT_IDENTITIES,
            selected_sections=_WORKER_SECTIONS, recovery_tool_sha256=_WORKER_RECOVERY_TOOL_SHA256,
            definition_ownership=_WORKER_DEFINITION_OWNERSHIP, open_gates=_WORKER_OPEN_GATES,
            historical_recipe=_WORKER_HISTORICAL_RECIPE,
            historical_integration=_WORKER_HISTORICAL_INTEGRATION)
        metadata = {key: value for key, value in document.items() if key != 'operations'}
        canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'))
        if canonical(metadata) != canonical(expected):
            raise ValueError('generation declared identities/scope/flags differ')
        operations = document['operations']
        if (not isinstance(operations, list) or len(operations) != 27 or
                any(not isinstance(row, dict) for row in operations) or
                sha_bytes(canonical(operations).encode()) != _WORKER_AUDIT_SHA256):
            raise ValueError('generation operation audit differs')
        for name, row in _WORKER_SOURCE_IDENTITIES.items():
            payload = payloads[name]
            blob = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
            if len(payload) != row['size'] or sha_bytes(payload) != row['sha256'] or blob != row['blob']:
                raise ValueError('origin provenance cross-link differs: ' + name)
        for name, row in _WORKER_OUTPUT_IDENTITIES.items():
            payload = payloads['compat/native-runtime/worker-f49/' + name]
            blob = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
            if len(payload) != row['size'] or sha_bytes(payload) != row['sha256'] or blob != row['blob']:
                raise ValueError('recovered output cross-link differs: ' + name)
        if sha_bytes(payloads['tools/recover_native_worker.py']) != document['recovery_tool_sha256']:
            raise ValueError('producer cross-link differs')
        patch = payloads['patches/0032-netbsd-linux-task-wait-worker.patch'].splitlines(keepends=True)
        starts = [index for index, line in enumerate(patch) if line.startswith(b'--- a/')]
        if len(starts) != 14:
            raise ValueError('exact fourteen source patch owners required')
        for owner, row in _WORKER_SECTIONS.items():
            matching = [index for index in starts if patch[index] == b'--- a/' + owner.encode() + b'\n']
            if len(matching) != 1:
                raise ValueError('selected source patch owner differs: ' + owner)
            first = matching[0]
            last = next((index for index in starts if index > first), len(patch))
            section = b''.join(patch[first:last])
            if (patch[first + 1] != b'+++ b/' + owner.encode() + b'\n' or len(section) != row['size'] or
                    sha_bytes(section) != row['sha256'] or
                    sum(line.startswith(b'@@ ') for line in patch[first:last]) != row['hunks']):
                raise ValueError('selected source patch section differs: ' + owner)
        recovered_c = payloads['compat/native-runtime/worker-f49/linux_kthread.c']
        recovered_h = payloads['compat/native-runtime/worker-f49/include/linux/kthread.h']
        if not recovered_c.endswith(payloads['compat/native-runtime/worker/worker.inc']):
            raise ValueError('complete Worker implementation witness differs')
        if recovered_h.count(payloads['compat/native-runtime/worker/worker_header.inc']) != 1:
            raise ValueError('complete Worker declaration witness differs')
        checked_fini = (b'void\nlinux_kthread_fini(void)\n{\n\tint error;\n\n'
                        b'\terror = linux_task_system_fini();\n\tKASSERT(error == 0);\n}\n')
        if recovered_c.count(checked_fini) != 1:
            raise ValueError('checked Task fini result differs')
        integration = payloads['compat/native-runtime/worker/INTEGRATION.txt']
        if any(row['sha256'].encode() not in integration for row in _WORKER_OUTPUT_IDENTITIES.values()):
            raise ValueError('final integration identity record differs')
        return dict(state='VERIFIED_WORKER_SOURCE_GENERATION_ONLY', provenance=_WORKER_PROVENANCE_PATH,
            provenance_sha256=contract['generation_provenance_sha256'], netbsd_pin=PIN,
            repository_input_commit=_WORKER_INPUT_COMMIT, operation_count=27,
            inputs=copy.deepcopy(_WORKER_SOURCE_IDENTITIES), outputs=copy.deepcopy(_WORKER_OUTPUT_IDENTITIES),
            selected_sections=copy.deepcopy(_WORKER_SECTIONS), recovery_tool_sha256=_WORKER_RECOVERY_TOOL_SHA256,
            definition_ownership=copy.deepcopy(_WORKER_DEFINITION_OWNERSHIP),
            historical_recipe=copy.deepcopy(_WORKER_HISTORICAL_RECIPE),
            historical_integration=copy.deepcopy(_WORKER_HISTORICAL_INTEGRATION), open_gates=list(_WORKER_OPEN_GATES),
            native_preprocessing='NOT_RUN', native_compilation='NOT_RUN', linked=False,
            installed=False, booted=False, runtime='NOT_RUN')
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        raise ValueError('Worker generation: ' + str(error)) from error


def poll_input_policy(contract=None, reviewed_sha256=None):
    """Only the seventh fixed profile composes Poll with the actual Task API."""
    if reviewed_sha256 != POLL_CONTRACT_SHA256:
        rows = contract.get('repository_inputs', {}) if isinstance(contract, dict) else {}
        if (isinstance(contract, dict) and contract.get('units') == ['linux_poll_owner.c'] or
                isinstance(rows, dict) and any(isinstance(row, dict) and row.get('role')
                    in ('poll_implementation_owner', 'poll_header') for row in rows.values())):
            raise ValueError('Poll inputs require the exact reviewed Poll contract')
        return []
    if not isinstance(contract, dict):
        raise ValueError('reviewed Poll provider identity/shape differs')
    rows = contract.get('repository_inputs')
    shape = dict(schema=1, provider_root='compat/native-file',
                 units=['linux_poll_owner.c'],
                 repository_include_roots=['compat/native-file/include',
                     'compat/native-mm/include', 'compat/native-uio/include',
                     'compat/native-runtime/wait-f43/include',
                     'compat/native-runtime/include'],
                 native_include_roots=['sys/external/bsd/common/include',
                                       'sys/external/bsd/drm2/include'],
                 required_patched_headers=['sys/sys/file.h'],
                 linux_pin=WAIT_LINUX_PIN, wait_contract_sha256=WAIT_CONTRACT_SHA256,
                 generation_provenance_sha256=_WAIT_PROVENANCE_SHA256)
    if (type(contract.get('schema')) is not int or
            any(contract.get(key) != value for key, value in shape.items()) or
            not isinstance(rows, dict) or
            any(not isinstance(row, dict) for row in rows.values()) or
            {name: row.get('role') for name, row in rows.items()} != _POLL_INPUT_ROLES):
        raise ValueError('reviewed Poll provider identity/shape differs')
    return sorted(_POLL_REQUIRED_INPUTS)


def require_poll_inputs(bindings, repository, contract=None, reviewed_sha256=None):
    for name in poll_input_policy(contract, reviewed_sha256):
        expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
        if bindings.get(str(Path(repository) / name)) != expected:
            raise ValueError('provider did not consume the required Poll input: ' + name)


def verify_poll_generation(repository, contract, repository_bindings, reviewed_sha256=None):
    """Check Poll against the separate unchanged Wait authority without executing a recipe."""
    if not poll_input_policy(contract, reviewed_sha256):
        return {}
    repository = Path(repository).resolve(strict=True)
    try:
        expected_paths = {str(repository / name) for name in _POLL_INPUT_ROLES}
        if set(repository_bindings) != expected_paths:
            raise ValueError('exactly twenty-six Git-bound Poll rows required')
        for name, row in contract['repository_inputs'].items():
            expected = dict(kind='repository', relative=name, **row)
            if repository_bindings.get(str(repository / name)) != expected:
                raise ValueError('Git-bound Poll row differs: ' + name)
        wait_contract = load_contract(repository / WAIT_CONTRACT_PATH, repository)
        wait_bindings = repository_inputs(repository, wait_contract)
        shared = {}
        for name, row in wait_contract['repository_inputs'].items():
            poll_row = contract['repository_inputs'].get(name, {})
            identity = {key: row[key] for key in ('blob', 'sha256')}
            if {key: poll_row.get(key) for key in identity} != identity:
                raise ValueError('referenced Wait input identity differs: ' + name)
            shared[name] = identity
        generation = verify_wait_generation(repository, wait_contract, wait_bindings,
                                            WAIT_CONTRACT_SHA256)
        return dict(state='VERIFIED_REFERENCED_WAIT_GENERATION_ONLY',
            wait_contract=WAIT_CONTRACT_PATH, wait_contract_sha256=WAIT_CONTRACT_SHA256,
            wait_repository_commit=wait_contract['repository_commit'],
            shared_repository_inputs=shared, wait_generation=generation,
            native_preprocessing='NOT_RUN', native_compilation='NOT_RUN',
            linked=False, runtime='NOT_RUN')
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise ValueError('Poll generation: ' + str(error)) from error


def wait_input_policy(contract=None, reviewed_sha256=None):
    """Only the sixth fixed profile admits the exact recovered Wait input set."""
    if contract is not None and not isinstance(contract, dict):
        raise ValueError('reviewed Wait provider identity/shape differs')
    rows = (contract or {}).get('repository_inputs', {})
    if not isinstance(rows, dict):
        raise ValueError('reviewed Wait provider identity/shape differs')
    if reviewed_sha256 != WAIT_CONTRACT_SHA256:
        if any(isinstance(row, dict) and row.get('role') == 'generation_proof_owner'
               for row in rows.values()):
            raise ValueError('generation proofs require the exact reviewed Wait contract')
        return []
    shape = dict(provider_root='compat/native-runtime/wait-f43', units=['linux_wait.c'],
                 repository_include_roots=['compat/native-runtime/wait-f43/include',
                                           'compat/native-runtime/include'],
                 native_include_roots=['sys/external/bsd/common/include',
                                       'sys/external/bsd/drm2/include'],
                 required_patched_headers=[], linux_pin=WAIT_LINUX_PIN,
                 generation_provenance_sha256=_WAIT_PROVENANCE_SHA256)
    if (not isinstance(contract, dict) or not isinstance(rows, dict) or
            any(contract.get(key) != value for key, value in shape.items()) or
            any(not isinstance(row, dict) for row in rows.values()) or
            {name: row.get('role') for name, row in rows.items()} != _WAIT_INPUT_ROLES):
        raise ValueError('reviewed Wait provider identity/shape differs')
    return sorted(_WAIT_REQUIRED_INPUTS)


def require_wait_inputs(bindings, repository, contract=None, reviewed_sha256=None):
    for name in wait_input_policy(contract, reviewed_sha256):
        expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
        if bindings.get(str(Path(repository) / name)) != expected:
            raise ValueError('provider did not consume the required Wait input: ' + name)


def verify_wait_generation(repository, contract, repository_bindings, reviewed_sha256=None):
    """Cross-link same-read committed generation evidence; never run either recipe."""
    if not wait_input_policy(contract, reviewed_sha256):
        return {}
    repository = Path(repository).resolve(strict=True)
    try:
        expected_paths = {str(repository / name) for name in _WAIT_INPUT_ROLES}
        if set(repository_bindings) != expected_paths:
            raise ValueError('exactly fifteen Git-bound rows required')

        def read_bound(name):
            expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
            if repository_bindings.get(str(repository / name)) != expected:
                raise ValueError('Git-bound generation row differs: ' + name)
            path = repository / name
            if path.is_symlink() or path.resolve(strict=True) != path:
                raise ValueError('generation input is aliased: ' + name)
            raw = regular_bytes(path)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if (sha_bytes(raw) != expected['sha256'] or blob != expected['blob'] or
                    path.is_symlink() or path.resolve(strict=True) != path):
                raise ValueError('same-read generation SHA256/blob differs: ' + name)
            return raw

        def read_json(name):
            return json.loads(read_bound(name), object_pairs_hook=unique_object)

        provenance_raw = read_bound(_WAIT_PROVENANCE_PATH)
        if sha_bytes(provenance_raw) != contract['generation_provenance_sha256']:
            raise ValueError('generation provenance pin differs')
        document = json.loads(provenance_raw, object_pairs_hook=unique_object)
        if (not isinstance(document, dict) or set(document) != _WAIT_PROVENANCE_KEYS or
                type(document.get('schema')) is not int or document['schema'] != 1 or
                document.get('state') != 'RECOVERED_SOURCE_ONLY_NOT_INSTALLED' or
                document.get('linux_pin') != WAIT_LINUX_PIN or document.get('netbsd_pin') != PIN or
                document.get('source_mode') != 'PINNED_UPSTREAM_BLOB_SNAPSHOTS; NO CHECKOUT/CLEAN-TREE CLAIM' or
                document.get('native_preprocessing') != 'NOT_RUN' or
                document.get('native_compilation') != 'NOT_RUN' or
                document.get('runtime') != 'NOT_RUN' or document.get('linked') is not False or
                document.get('installed') is not False or document.get('open_gates') != _WAIT_OPEN_GATES):
            raise ValueError('generation scope/pins/flags differ')
        if (document.get('files') != _WAIT_OUTPUT_IDENTITIES or
                document.get('inputs') != _WAIT_SOURCE_IDENTITIES or
                document.get('witnesses') != _WAIT_WITNESSES or
                document.get('recovery_tool_sha256') != _WAIT_RECOVERY_TOOL_SHA256):
            raise ValueError('generation declared identities differ')
        operations = document.get('operations')
        if (not isinstance(operations, list) or len(operations) != 49 or
                any(not isinstance(row, dict) for row in operations) or
                len({row.get('operation') for row in operations}) != 49 or
                sha_bytes(json.dumps(operations, sort_keys=True, separators=(',', ':')).encode())
                != _WAIT_AUDIT_SHA256):
            raise ValueError('generation operation audit differs')
        for name, expected in _WAIT_OUTPUT_IDENTITIES.items():
            raw = read_bound('compat/native-runtime/wait-f43/' + name)
            if len(raw) != expected['size'] or sha_bytes(raw) != expected['sha256']:
                raise ValueError('historical recovered output differs: ' + name)
        for name, expected in _WAIT_SOURCE_IDENTITIES.items():
            raw = read_bound('compat/native-runtime/wait-inputs-f43/' + name)
            observed = dict(size=len(raw), sha256=sha_bytes(raw),
                git_blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                source_url='https://github.com/torvalds/linux/blob/' + WAIT_LINUX_PIN + '/' + name)
            if observed != expected:
                raise ValueError('pinned upstream raw authority differs: ' + name)
        inputs = read_json('compat/native-runtime/wait-inputs-f43/provenance.json')
        expected_inputs = dict(schema=1, state='PINNED_SOURCE_INPUTS', linux_pin=WAIT_LINUX_PIN,
            acquisition='exact two pinned upstream blobs; no checkout or clean-tree claim',
            files=_WAIT_SOURCE_IDENTITIES)
        if (not isinstance(inputs, dict) or type(inputs.get('schema')) is not int or
                inputs != expected_inputs):
            raise ValueError('input provenance cross-link differs')
        for label, expected in _WAIT_WITNESSES.items():
            raw = read_bound(expected['path'])
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if sha_bytes(raw) != expected['sha256'] or blob != expected['git_blob']:
                raise ValueError('recipe/ledger witness differs: ' + label)
        ledger = read_json(_WAIT_WITNESSES['historical_ledger']['path'])
        if not isinstance(ledger, dict) or any(ledger.get(name) != row['sha256']
                for name, row in _WAIT_OUTPUT_IDENTITIES.items()):
            raise ValueError('historical ledger cross-link differs')
        producer = read_bound('tools/recover_native_wait.py')
        if sha_bytes(producer) != document['recovery_tool_sha256']:
            raise ValueError('producer cross-link differs')
        return dict(state='VERIFIED_SOURCE_GENERATION_ONLY',
            provenance=_WAIT_PROVENANCE_PATH, provenance_sha256=contract['generation_provenance_sha256'],
            linux_pin=WAIT_LINUX_PIN, netbsd_pin=PIN, operation_count=49,
            inputs={name: dict(row) for name, row in _WAIT_SOURCE_IDENTITIES.items()},
            outputs={name: dict(row) for name, row in _WAIT_OUTPUT_IDENTITIES.items()},
            witnesses={name: dict(row) for name, row in _WAIT_WITNESSES.items()},
            recovery_tool_sha256=document['recovery_tool_sha256'],
            native_preprocessing='NOT_RUN', native_compilation='NOT_RUN', linked=False, runtime='NOT_RUN')
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise ValueError('Wait generation: ' + str(error)) from error


def task_worker_input_policy(contract=None, reviewed_sha256=None):
    """The fifth fixed selection alone may compose the original Task C and worker API."""
    if reviewed_sha256 != TASK_WORKER_CONTRACT_SHA256:
        return []
    if not isinstance(contract, dict):
        raise ValueError('reviewed Task worker provider identity/shape differs')
    rows = contract.get('repository_inputs', {})
    shape = dict(provider_root='compat/native-runtime/task',
                 units=['linux_task_worker_owner.c'],
                 repository_include_roots=['compat/native-runtime/include'],
                 native_include_roots=['sys/external/bsd/common/include',
                                       'sys/external/bsd/drm2/include'],
                 required_patched_headers=[])
    if (any(contract.get(key) != value for key, value in shape.items()) or
            not isinstance(rows, dict) or
            any(not isinstance(row, dict) for row in rows.values()) or
            {name: row.get('role') for name, row in rows.items()} != _TASK_WORKER_INPUT_ROLES):
        raise ValueError('reviewed Task worker provider identity/shape differs')
    return sorted(_TASK_WORKER_REQUIRED_INPUTS)


def require_task_worker_inputs(bindings, repository, contract=None, reviewed_sha256=None):
    for name in task_worker_input_policy(contract, reviewed_sha256):
        expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
        if bindings.get(str(Path(repository) / name)) != expected:
            raise ValueError('provider did not consume the exact Task worker input: ' + name)


def task_fragment_policy(contract=None, reviewed_sha256=None):
    """Only the exact reviewed Task selection may consume its three owner fragments."""
    if reviewed_sha256 == TASK_WORKER_CONTRACT_SHA256:
        task_worker_input_policy(contract, reviewed_sha256)
        return sorted(_TASK_FRAGMENTS)
    rows = (contract or {}).get('repository_inputs', {})
    fragments = {name for name, row in rows.items() if row.get('role') == 'task_fragment'}
    if reviewed_sha256 != TASK_CONTRACT_SHA256:
        if fragments:
            raise ValueError('Task fragments require the exact reviewed Task contract')
        return []
    shape = dict(provider_root='compat/native-runtime/task', units=['linux_task.c'],
                 repository_include_roots=['compat/native-runtime/include'],
                 native_include_roots=['sys/external/bsd/common/include',
                                       'sys/external/bsd/drm2/include'],
                 required_patched_headers=[])
    if (any(contract.get(key) != value for key, value in shape.items()) or
            {name: row.get('role') for name, row in rows.items()} != _TASK_INPUT_ROLES or
            fragments != _TASK_FRAGMENTS):
        raise ValueError('reviewed Task provider identity/shape differs')
    return sorted(_TASK_FRAGMENTS)


def require_task_fragments(bindings, repository, contract=None, reviewed_sha256=None):
    for name in task_fragment_policy(contract, reviewed_sha256):
        expected = dict(kind='repository', relative=name, **contract['repository_inputs'][name])
        if bindings.get(str(Path(repository) / name)) != expected:
            raise ValueError('provider did not consume the exact reviewed Task fragment: ' + name)


def provider_header_policy(core, contract=None, reviewed_sha256=None):
    """Keep the original all-header default; narrow only via reviewed contract metadata."""
    if reviewed_sha256 == WORKER_CONTRACT_SHA256:
        worker_input_policy(contract, reviewed_sha256)
        return []
    if reviewed_sha256 == POLL_CONTRACT_SHA256:
        poll_input_policy(contract, reviewed_sha256)
    elif wait_input_policy(contract, reviewed_sha256):
        return []
    if task_fragment_policy(contract, reviewed_sha256):
        return []
    available = {name for name in core['patched_inputs'] if name.endswith('.h')}
    if contract is None or 'required_patched_headers' not in contract:
        return sorted(available)
    names = contract['required_patched_headers']
    if not isinstance(names, list) or not names:
        raise ValueError('required_patched_headers must be a nonempty list')
    if any(not isinstance(name, str) for name in names):
        raise ValueError('required patched headers must be canonical header paths')
    for name in names:
        source_relative(name)
        if not name.endswith('.h'):
            raise ValueError('required patched header is not a header path')
    required = set(names)
    if len(required) != len(names):
        raise ValueError('duplicate required patched header')
    if 'sys/sys/file.h' not in required:
        raise ValueError('native FILE header must remain required')
    if not required.issubset(available):
        raise ValueError('required patched header is outside the selected core')
    return sorted(required)


def require_provider_headers(bindings, repository, core, contract=None, reviewed_sha256=None):
    consumed = {row['relative'] for row in bindings.values() if row['kind'] == 'patched'}
    required = set(provider_header_policy(core, contract, reviewed_sha256))
    if not required.issubset(consumed):
        raise ValueError('provider did not consume the patched native FILE headers')
