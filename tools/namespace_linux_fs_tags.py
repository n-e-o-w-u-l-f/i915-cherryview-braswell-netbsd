#!/usr/bin/env python3
"""Namespace only owned Linux struct tags before native FILE integration.

Native headers/adapter units are never token-rewritten. Every admitted input
must have a digest from the completed Linux source transformation receipt.
This changes names, not object layout or runtime semantics.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import socket

TAGS = {'file': 'linux_file', 'inode': 'linux_inode',
        'address_space': 'linux_address_space', 'folio': 'linux_folio'}
IDENTIFIERS = {'pgoff_t':'linux_pgoff_t'}
PROVIDER_INCLUDES = {
    'linux/fs.h': 'linux/fs_netbsd.h',
    'linux/file.h': 'linux/file_api_netbsd.h',
    'linux/file_ref.h': 'linux/file_ref_netbsd.h',
    'linux/anon_inodes.h': 'linux/anon_inodes_netbsd.h',
    'linux/poll.h': 'linux/poll_netbsd.h',
    'linux/shmem_fs.h': 'linux/shmem_fs_netbsd.h',
    'linux/pagemap.h': 'linux/pagemap_netbsd.h',
    'linux/mm_types.h': 'linux/modern_mm_types_netbsd.h',
    'linux/mm.h': 'linux/mm_netbsd.h',
    'linux/mmap_lock.h': 'linux/mmap_lock_netbsd.h',
    'linux/io-mapping.h': 'linux/io_mapping_netbsd.h',
    'linux/uio.h': 'linux/uio_netbsd.h',
    'linux/folio_batch.h': 'linux/folio_batch_netbsd.h',
}
LEX = re.compile(
    r'(?P<include>^[ \t]*#[ \t]*(?:include|include_next|import)[ \t]+(?:<[^>\n]+>|"[^"\n]+"))'
    r'|(?P<comment>/\*[\s\S]*?\*/|//(?:\\\r?\n|[^\n])*)'
    r'|(?P<literal>"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\')'
    r'|(?P<identifier>[A-Za-z_][A-Za-z_0-9]*)'
    r'|(?P<space>\s+)|(?P<other>.)', re.M)
DIRECTIVE = re.compile(
    r'^[ \t]*(?:#|%:)[ \t]*(?P<kind>include_next|include|import)(?![A-Za-z_0-9])'
    r'[ \t]*(?:<(?P<angled>[^>\n]+)>|"(?P<quoted>[^"\n]+)")', re.M)


def translate(text, include_mapping=None):
    """Rename a tag immediately following struct; keep ordinary names intact."""
    # C removes escaped newlines before token recognition. Lex that logical
    # view, but map every token back to its untouched physical source span.
    # Otherwise a splice can hide a tag or even form a comment delimiter.
    logical, positions = [], []
    index = 0
    while index < len(text):
        if text.startswith('\\\r\n', index):
            index += 3
        elif text.startswith('\\\n', index):
            index += 2
        else:
            logical.append(text[index]); positions.append(index); index += 1
    logical = ''.join(logical)
    edits, need_tag, counts = [], False, {tag: 0 for tag in TAGS}
    if include_mapping is not None:
        if any(PROVIDER_INCLUDES.get(old) != new for old, new in include_mapping.items()):
            raise ValueError('unqualified provider include mapping')
        counts.update({'include:'+old: 0 for old in include_mapping})
    # Preprocessing replaces a whole block comment with whitespace, including
    # its internal physical newlines. Recognize directives in that view, but
    # retain original physical comments/splices in the emitted source. This
    # handles #include/*comment*/<...> and a leading multiline comment without
    # treating an apparent directive inside a comment or literal as active.
    directive_view = list(logical)
    for match in LEX.finditer(logical):
        if match.lastgroup == 'comment':
            directive_view[match.start():match.end()] = ' ' * len(match.group())
    directives = list(DIRECTIVE.finditer(''.join(directive_view)))
    for directive in directives:
        group = 'angled' if directive.group('angled') is not None else 'quoted'
        old = directive.group(group)
        if include_mapping and old in include_mapping:
            if directive.group('kind') != 'include':
                raise ValueError('provider include_next/import requires explicit owner review')
            begin = positions[directive.start(group)]
            end = positions[directive.end(group) - 1] + 1
            splices = ''.join(re.findall(r'\\\r?\n', text[begin:end]))
            edits.append((begin, end, include_mapping[old] + splices))
            counts['include:' + old] += 1
    for match in LEX.finditer(logical):
        kind, token = match.lastgroup, match.group()
        begin, end = positions[match.start()], positions[match.end() - 1] + 1
        physical = text[begin:end]
        if any(match.start() < directive.end() and match.end() > directive.start()
               for directive in directives):
            need_tag = False
            continue
        if kind in ('space', 'comment'):
            continue
        if kind == 'identifier':
            if need_tag and token in TAGS:
                edits.append((begin, end, TAGS[token][:-len(token)] + physical))
                counts[token] += 1
            elif token in IDENTIFIERS:
                edits.append((begin,end,IDENTIFIERS[token][:-len(token)]+physical))
                key='identifier:'+token
                counts[key]=counts.get(key,0)+1
            need_tag = token == 'struct'
        else:
            need_tag = False
    output, cursor = [], 0
    for begin, end, replacement in sorted(edits):
        if begin < cursor:
            raise ValueError('overlapping source namespace replacements')
        output.append(text[cursor:begin]); output.append(replacement); cursor = end
    output.append(text[cursor:])
    return ''.join(output), counts


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owned_inputs(receipt):
    """Require an explicit frozen post-math identity for every Linux input."""
    if receipt.get('linux_pin') != 'fd179f8a05be3ccae366b9b96e176b51fbe54aab':
        raise ValueError('wrong Linux source pin')
    namespace = receipt.get('compiler_math_namespace')
    if not namespace or namespace.get('tokenizer_version') != 2:
        raise ValueError('completed owned compiler namespace receipt required')
    rows = list(namespace.get('seeds', ()))
    rows += [row for row in receipt.get('rows', ())
             if row.get('state') in ('IMPORTED_API_UNREVIEWED',
                                     'IMPORTED_API_TRANSLATED_UNREVIEWED')]
    found = {}
    for row in rows:
        rel = row.get('path', '')
        path = PurePosixPath(rel)
        if (not rel or path.is_absolute() or path.as_posix() != rel or ':' in rel or '\x00' in rel
                or any(part in ('', '.', '..') for part in rel.split('/')) or '\\' in rel
                or not rel.startswith('sys/external/bsd/drm2/dist/')
                or path.suffix not in ('.c', '.h')):
            raise ValueError('unqualified Linux-owned tag input: ' + rel)
        sha = row.get('sha256', '')
        if not re.fullmatch(r'[a-f0-9]{64}', sha):
            raise ValueError('missing exact transformed input hash: ' + rel)
        if rel in found and found[rel] != sha:
            raise ValueError('contradictory Linux input identity: ' + rel)
        found[rel] = sha
    if not found:
        raise ValueError('empty Linux input set')
    return found


def provider_includes(tree, receipt):
    """Admit only existing, digest-bound unique native provider headers."""
    if (receipt.get('version') != 1 or receipt.get('scope') != 'LINUX_OWNED_INCLUDES'
            or receipt.get('linux_pin') != 'fd179f8a05be3ccae366b9b96e176b51fbe54aab'):
        raise ValueError('explicit provider include contract required')
    mapping, owners = {}, {}
    for old, row in receipt.get('includes', {}).items():
        new = PROVIDER_INCLUDES.get(old)
        if new is None or row.get('target') != new:
            raise ValueError('unqualified provider include owner: '+old)
        relative = 'sys/external/bsd/drm2/include/'+new
        if row.get('path') != relative or not re.fullmatch(r'[a-f0-9]{64}',row.get('sha256','')):
            raise ValueError('provider header path/digest required: '+old)
        header = tree/relative
        if (header.resolve(strict=True) != header or not header.is_file()
                or digest(header) != row['sha256']):
            raise ValueError('provider header missing, redirected or changed: '+old)
        mapping[old] = new
        owners[relative] = row['sha256']
    if not mapping:
        raise ValueError('empty provider include contract')
    return mapping, owners


def integrate(tree, receipt, output, providers=None):
    tree = Path(tree).resolve(strict=True)
    output = Path(output)
    if (output.exists() or output.is_symlink() or not output.parent.is_dir()
            or output.resolve().is_relative_to(tree)):
        raise ValueError('new separate output receipt required')
    candidates = owned_inputs(receipt)
    include_mapping, header_owners = provider_includes(tree, providers) if providers is not None else ({}, {})
    def qualified(path, relative):
        # Reject any redirected ancestor too: an in-tree dist symlink must
        # never authorize rewriting a native header elsewhere in this tree.
        if path.resolve(strict=True) != tree / relative or not path.is_file():
            raise ValueError('Linux source escapes canonical dist owner: ' + relative)
        return path
    plan, rows = [], []
    for relative, expected in sorted(candidates.items()):
        path = tree / relative
        qualified(path, relative)
        if digest(path) != expected:
            raise ValueError('Linux source changed since transformation: ' + relative)
        before = path.read_bytes()
        text, counts = translate(before.decode('utf8'), include_mapping or None)
        after = text.encode('utf8')
        temp = path.with_name(path.name + '.fs-tags.tmp')
        if temp.exists() or temp.is_symlink():
            raise ValueError('preserve interrupted tag transform: ' + str(temp))
        rows.append(dict(path=relative, before_sha256=expected,
                         after_sha256=hashlib.sha256(after).hexdigest(), counts=counts))
        if before != after:
            plan.append((path, temp, before, after))
    # Every source and temporary is checked before the first write. Recheck
    # immediately before replacement; record any failure for explicit recovery.
    result = dict(state='APPLYING', tags=TAGS, identifiers=IDENTIFIERS, linux_pin=receipt['linux_pin'],
                  files=rows, replaced=[], acceptance='SOURCE_NAMES_ONLY',
                  include_mapping=include_mapping, provider_headers_sha256=header_owners)
    receipt_temp = output.with_name(output.name + '.fs-tags-receipt.tmp')
    if receipt_temp.exists() or receipt_temp.is_symlink():
        raise ValueError('preserve interrupted tag receipt: ' + str(receipt_temp))
    first_save = True
    def save():
        nonlocal first_save
        data = json.dumps(result, indent=2) + '\n'
        if first_save:
            with output.open('x', encoding='utf8', newline='\n') as stream:
                stream.write(data)
            first_save = False
        else:
            with receipt_temp.open('x', encoding='utf8', newline='\n') as stream:
                stream.write(data)
            receipt_temp.replace(output)
    save()
    try:
        for path, temp, before, after in plan:
            qualified(path, path.relative_to(tree).as_posix())
            if path.read_bytes() != before:
                raise ValueError('concurrent source drift: ' + str(path))
            with temp.open('xb') as stream:
                stream.write(after)
            qualified(path, path.relative_to(tree).as_posix())
            if path.read_bytes() != before:
                raise ValueError('concurrent source drift during temporary write: ' + str(path))
            temp.replace(path)
            result['replaced'].append(path.relative_to(tree).as_posix())
            save()
        for row in rows:
            path = qualified(tree / row['path'], row['path'])
            if digest(path) != row['after_sha256']:
                raise ValueError('concurrent source drift after tag transform: ' + row['path'])
        for relative, expected in header_owners.items():
            header = tree/relative
            if header.resolve(strict=True) != header or digest(header) != expected:
                raise ValueError('provider header changed during namespace transform: '+relative)
        result['state'] = 'APPLIED'
        save()
    except BaseException as error:
        result.update(state='FAILED', error=str(error))
        try:
            save()
        except OSError:
            # Keep both the last valid receipt and any incomplete temporary;
            # their complete before/after table enables explicit recovery.
            pass
        raise
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tree', type=Path, required=True)
    p.add_argument('--namespace-receipt', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--provider-receipt', type=Path,
                   help='optional exact unique-header owners; never rewrites native inputs')
    a = p.parse_args()
    if (platform.system() != 'NetBSD' or platform.release().split('.')[0] != '11'
            or socket.gethostname().split('.')[0] != 'hp-tpnw121'):
        p.error('source integration restricted to HP NetBSD11')
    providers = json.loads(a.provider_receipt.read_text(encoding='utf8')) if a.provider_receipt else None
    result = integrate(a.tree, json.loads(a.namespace_receipt.read_text(encoding='utf8')), a.output, providers)
    print('LINUX_FS_TAG_NAMESPACE', len(result['replaced']), 'changed Linux-owned files; no ABI/runtime acceptance')


if __name__ == '__main__':
    main()
