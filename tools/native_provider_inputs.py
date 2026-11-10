"""Reviewed native FILE provider identities and independent dependency admission."""
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
                                   (ANON_CONTRACT_PATH, ANON_CONTRACT_SHA256)):
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


def provider_header_policy(core, contract=None):
    """Keep the original all-header default; narrow only via reviewed contract metadata."""
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


def require_provider_headers(bindings, repository, core, contract=None):
    consumed = {row['relative'] for row in bindings.values() if row['kind'] == 'patched'}
    required = set(provider_header_policy(core, contract))
    if not required.issubset(consumed):
        raise ValueError('provider did not consume the patched native FILE headers')
