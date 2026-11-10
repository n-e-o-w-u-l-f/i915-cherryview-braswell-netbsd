"""Archive-bound provenance for a scoped native NetBSD ABI compile.

No extraction, source edits, compiler execution, or invented clean-Git identity.
The production archive pin is fixed; generated opt headers are a separate input.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import tarfile

PIN = '03d918f6d0e81fa05b8f1160eca0628ad39988a6'
ARCHIVE_SHA256 = '3645aca2c1ac9716558075b7747a98583a8e87435f00ff30c786b4b438dbe15b'
PREFIX = 'src-' + PIN + '/'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def source_relative(value):
    rel = PurePosixPath(value)
    if (not value or rel.is_absolute() or '..' in rel.parts
            or '\\' in value or str(rel) != value):
        raise ValueError('unsafe archive source path: ' + str(value))
    return value


class ArchiveSource:
    """Keep one regular archive FD bound through hashing and selected reads."""
    def __init__(self, path):
        self.path = Path(path).absolute()
        self.stream = None
        self.initial_identity = None
        self.verified_members = {}

    def __enter__(self):
        if self.path.is_symlink():
            raise ValueError('archive symlink is not an immutable input')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(self.path, flags)
        self.stream = os.fdopen(descriptor, 'rb')
        try:
            info = os.fstat(self.stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('regular pinned source archive required')
            self.initial_identity = identity(info)
            if hashlib.file_digest(self.stream, 'sha256').hexdigest() != ARCHIVE_SHA256:
                raise ValueError('pinned NetBSD source archive SHA256 mismatch')
            self.check_identity()
            return self
        except BaseException:
            self.stream.close()
            self.stream = None
            raise

    def check_identity(self):
        if self.stream is None:
            raise ValueError('source archive is not open')
        if (identity(os.fstat(self.stream.fileno())) != self.initial_identity
                or self.path.is_symlink()
                or identity(self.path.stat()) != self.initial_identity):
            raise ValueError('source archive identity/content metadata changed')

    def verify_source_members(self, expected):
        """Compare requested regular members only; never trust TAR link targets."""
        wanted = {PREFIX + source_relative(rel): (rel, value)
                  for rel, value in expected.items()}
        if not wanted:
            raise ValueError('empty archive dependency proof')
        self.check_identity()
        self.stream.seek(0)
        observed = {}
        with tarfile.open(fileobj=self.stream, mode='r|gz') as archive:
            for member in archive:
                if member.name not in wanted:
                    continue
                rel, expected_hash = wanted[member.name]
                if rel in observed:
                    raise ValueError('duplicate selected archive member: ' + rel)
                if not member.isfile():
                    raise ValueError('selected archive member is not regular: ' + rel)
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError('unreadable selected archive member: ' + rel)
                with handle:
                    actual = hashlib.file_digest(handle, 'sha256').hexdigest()
                if actual != expected_hash:
                    raise ValueError('archive/source dependency bytes differ: ' + rel)
                observed[rel] = actual
        self.check_identity()
        missing = set(expected) - set(observed)
        if missing:
            raise ValueError('missing archive dependencies: ' + str(sorted(missing)))
        self.verified_members = observed
        return observed.copy()

    def receipt(self):
        self.check_identity()
        return dict(mode='ARCHIVE_USED_SUBSET', netbsd_pin=PIN,
                    archive=str(self.path), archive_sha256=ARCHIVE_SHA256,
                    archive_identity=list(self.initial_identity),
                    verified_source_members=self.verified_members.copy(),
                    full_tree_clean_git='NOT_CLAIMED')

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def dependency_paths(depfile, cwd):
    text = Path(depfile).read_text(encoding='utf8').replace(chr(92) + chr(10), ' ')
    if ':' not in text:
        raise ValueError('native dependency output has no target')
    target, body = text.split(':', 1)
    if not target.strip() or ':' in body:
        raise ValueError('ambiguous native dependency output')
    tokens = shlex.split(body)
    if not tokens:
        raise ValueError('empty native dependency output')
    base = Path(cwd).resolve(strict=True)
    return {((Path(value) if Path(value).is_absolute() else base / value)
             .resolve(strict=True)) for value in tokens}


def bind_dependencies(paths, source, overlay, obj, patched, generated_configuration=None):
    """Bind real paths; config is direct opt_*.h or exact selected-contract headers."""
    source, overlay, obj = [Path(value).resolve(strict=True)
                            for value in (source, overlay, obj)]
    declared = ({} if generated_configuration is None else
                validate_generated_configuration(generated_configuration, allow_empty=True))
    declared_configuration_inputs(obj, declared)
    rows = {}
    for original in paths:
        path = Path(original).resolve(strict=True)
        if not path.is_file():
            raise ValueError('native dependency is not a file: ' + str(path))
        current = digest(path)
        if path.is_relative_to(overlay):
            rel = path.relative_to(overlay).as_posix()
            if rel not in patched or current != patched[rel]:
                raise ValueError('unbound patched dependency: ' + rel)
            row = dict(kind='patched', relative=rel, sha256=current)
        elif path.is_relative_to(source):
            rel = path.relative_to(source).as_posix()
            if rel in patched:
                raise ValueError('original version of patched input consumed: ' + rel)
            row = dict(kind='archive', relative=source_relative(rel), sha256=current)
        elif path.parent == obj and path.name in declared:
            if current != declared[path.name]:
                raise ValueError('declared configuration bytes differ: ' + path.name)
            row = dict(kind='declared_generated_configuration', relative=path.name, sha256=current)
        elif path.parent == obj and re.fullmatch(r'opt_[A-Za-z0-9_]+\.h', path.name):
            row = dict(kind='generated_configuration', relative=path.name, sha256=current)
        else:
            raise ValueError('foreign/unbound native dependency: ' + str(path))
        rows[str(path)] = row
    if not rows:
        raise ValueError('empty bound native dependency set')
    return rows


def archive_expectations(initial, bindings):
    expected = dict(initial)
    for row in bindings.values():
        if row['kind'] != 'archive':
            continue
        prior = expected.setdefault(row['relative'], row['sha256'])
        if prior != row['sha256']:
            raise ValueError('source dependency changed across owners: ' + row['relative'])
    return expected


def recheck_dependencies(paths, before, source, overlay, obj, patched, generated_configuration=None):
    current = bind_dependencies(paths, source, overlay, obj, patched, generated_configuration)
    if current != before:
        raise ValueError('native dependency set or bytes changed after preflight')
    return current


def private_git_environment(output):
    """Isolate non-repository apply checks from the controller's Git selectors."""
    environment = dict(os.environ)
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        environment.pop(key, None)
    environment['GIT_CEILING_DIRECTORIES'] = str(Path(output).parent)
    return environment


def snapshot_prior_artifacts(obj, units):
    """Freeze existing object, dependency and stack-usage outputs, including absence."""
    obj = Path(obj)
    result = {}
    for unit in units:
        if Path(unit).name != unit or unit in ('', '.', '..'):
            raise ValueError('unsafe original artifact name')
        for extension in ('o', 'd', 'su'):
            name = unit + '.' + extension
            path = obj / name
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError('original artifact is not a regular file: ' + name)
            result[name] = digest(path) if path.exists() else None
    return result


def recheck_prior_artifacts(obj, expected):
    units = sorted({name.rsplit('.', 1)[0] for name in expected})
    if snapshot_prior_artifacts(obj, units) != expected:
        raise ValueError('original object/dependency/stack artifact changed')


def validate_generated_configuration(mapping, allow_empty=False):
    """Validate a selected contract's exact direct non-opt header declarations."""
    if not isinstance(mapping, dict) or (not mapping and not allow_empty):
        raise ValueError('generated_configuration must be a nonempty object')
    result = {}
    for name, expected in mapping.items():
        if (not isinstance(name, str)
                or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.h', name) is None
                or name.lower().startswith('opt_')):
            raise ValueError('unsafe or opt generated configuration basename')
        if (not isinstance(expected, str)
                or re.fullmatch(r'[0-9a-f]{64}', expected) is None):
            raise ValueError('invalid generated configuration SHA256: ' + name)
        result[name] = expected
    return result


def _unique_contract_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate contract declaration: ' + name)
        result[name] = value
    return result


def selected_generated_configuration(chain, archive_mode):
    """Read metadata only from the already selected, hash-frozen contracts."""
    declared, origins = {}, []
    for step in chain:
        path = Path(step['contract'])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != step['contract_sha256']:
            raise ValueError('selected contract changed before manifest admission')
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError('selected native contract must be an object')
        if 'generated_configuration' not in document:
            continue
        if not archive_mode:
            raise ValueError('generated_configuration requires explicit source archive mode')
        document = json.loads(raw, object_pairs_hook=_unique_contract_object)
        mapping = validate_generated_configuration(document['generated_configuration'])
        for name, expected in mapping.items():
            if name in declared:
                raise ValueError('duplicate generated configuration declaration: ' + name)
            declared[name] = expected
        origins.append(dict(contract=str(path),
                            contract_sha256=step['contract_sha256'],
                            generated_configuration=mapping))
    return declared, origins


def declared_configuration_inputs(obj, mapping):
    """Bind every declared basename to a real direct object-directory header."""
    declared = validate_generated_configuration(mapping, allow_empty=True)
    obj = Path(obj).resolve(strict=True)
    result = {}
    for name, expected in declared.items():
        path = obj / name
        if (path.is_symlink() or not path.is_file()
                or path.resolve(strict=True).parent != obj):
            raise ValueError('declared configuration is not a direct regular header: ' + name)
        if digest(path) != expected:
            raise ValueError('declared configuration bytes differ: ' + name)
        result[str(path)] = expected
    return result


def require_declared_configuration_consumed(bindings, mapping):
    declared = validate_generated_configuration(mapping, allow_empty=True)
    consumed = {row['relative'] for row in bindings.values()
                if row['kind'] == 'declared_generated_configuration'}
    if consumed != set(declared):
        raise ValueError('declared configuration not consumed: ' +
                         str(sorted(set(declared) - consumed)))
