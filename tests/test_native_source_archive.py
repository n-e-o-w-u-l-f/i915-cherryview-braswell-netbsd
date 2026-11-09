"""Real-file archive provenance and dependency-boundary admission regressions."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_source_archive as provenance
import build_hp_native_fileops as fileops


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ArchiveProvenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'source.tar.gz'

    def archive(self, members):
        with tarfile.open(self.path, 'w:gz') as tar:
            for name, content, kind in members:
                row = tarfile.TarInfo(name)
                if kind == 'file':
                    row.size = len(content)
                    tar.addfile(row, io.BytesIO(content))
                else:
                    row.type = tarfile.SYMTYPE
                    row.linkname = content.decode()
                    tar.addfile(row)
        return sha(self.path.read_bytes())

    def open_archive(self, members):
        expected = self.archive(members)
        patch = mock.patch.object(provenance, 'ARCHIVE_SHA256', expected)
        patch.start()
        self.addCleanup(patch.stop)
        archive = provenance.ArchiveSource(self.path)
        archive.__enter__()
        self.addCleanup(archive.__exit__, None, None, None)
        return archive

    def test_matching_regular_selected_member_and_narrow_receipt(self):
        body = b'actual source\n'
        archive = self.open_archive([(provenance.PREFIX + 'sys/a.c', body, 'file')])
        self.assertEqual(archive.verify_source_members({'sys/a.c': sha(body)}),
                         {'sys/a.c': sha(body)})
        self.assertEqual(archive.receipt()['mode'], 'ARCHIVE_USED_SUBSET')
        self.assertEqual(archive.receipt()['full_tree_clean_git'], 'NOT_CLAIMED')

    def test_wrong_archive_hash_rejected(self):
        self.archive([(provenance.PREFIX + 'sys/a.c', b'body', 'file')])
        with self.assertRaisesRegex(ValueError, 'archive SHA256'):
            with provenance.ArchiveSource(self.path):
                self.fail('untrusted archive admitted')

    def test_changed_source_bytes_rejected(self):
        archive = self.open_archive([(provenance.PREFIX + 'sys/a.c', b'original', 'file')])
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            archive.verify_source_members({'sys/a.c': sha(b'changed')})

    def test_missing_and_wrong_prefix_members_rejected(self):
        archive = self.open_archive([('foreign/sys/a.c', b'body', 'file')])
        with self.assertRaisesRegex(ValueError, 'missing archive'):
            archive.verify_source_members({'sys/a.c': sha(b'body')})

    def test_selected_symlink_rejected(self):
        archive = self.open_archive([(provenance.PREFIX + 'sys/a.h', b'../outside', 'link')])
        with self.assertRaisesRegex(ValueError, 'not regular'):
            archive.verify_source_members({'sys/a.h': sha(b'anything')})

    def test_duplicate_selected_member_rejected(self):
        archive = self.open_archive([(provenance.PREFIX + 'sys/a.h', b'body', 'file')] * 2)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            archive.verify_source_members({'sys/a.h': sha(b'body')})

    def test_path_traversal_and_absolute_paths_rejected(self):
        for name in ('../outside', '/absolute', 'sys/../bad', 'sys\\bad', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                provenance.source_relative(name)

    def test_archive_symlink_and_replacement_rejected(self):
        archive = self.open_archive([(provenance.PREFIX + 'sys/a.c', b'body', 'file')])
        link = self.root / 'link.tar.gz'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            with provenance.ArchiveSource(link):
                self.fail('symlink admitted')
        other = self.root / 'replacement'
        other.write_bytes(self.path.read_bytes())
        other.replace(self.path)
        with self.assertRaisesRegex(ValueError, 'identity'):
            archive.check_identity()

    def test_archive_in_place_drift_rejected(self):
        archive = self.open_archive([(provenance.PREFIX + 'sys/a.c', b'body', 'file')])
        with self.path.open('ab') as stream:
            stream.write(b'x')
        with self.assertRaisesRegex(ValueError, 'identity'):
            archive.check_identity()


class DependencyProvenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.overlay, self.obj = [self.root / v for v in ('source', 'overlay', 'obj')]
        for directory in (self.source, self.overlay, self.obj):
            directory.mkdir()
        self.baseline = self.file(self.source / 'sys/native.h', b'baseline')
        self.modified = self.file(self.overlay / 'sys/file.h', b'patched')
        self.generated = self.file(self.obj / 'opt_param.h', b'configuration')
        self.patched = {'sys/file.h': sha(b'patched')}

    def file(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def bind(self, paths):
        return provenance.bind_dependencies(paths, self.source, self.overlay,
                                            self.obj, self.patched)

    def test_actual_paths_are_classified_and_generated_remains_separate(self):
        rows = self.bind([self.baseline, self.modified, self.generated])
        self.assertEqual({v['kind'] for v in rows.values()},
                         {'archive', 'patched', 'generated_configuration'})
        self.assertEqual(provenance.archive_expectations({}, rows),
                         {'sys/native.h': sha(b'baseline')})

    def test_original_patched_header_is_rejected(self):
        original = self.file(self.source / 'sys/file.h', b'original')
        with self.assertRaisesRegex(ValueError, 'original version'):
            self.bind([original])

    def test_changed_overlay_and_unbound_overlay_are_rejected(self):
        for path in (self.modified, self.file(self.overlay / 'sys/other.h', b'other')):
            if path == self.modified:
                path.write_bytes(b'drift')
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'unbound patched'):
                self.bind([path])

    def test_unexpected_and_nested_object_headers_rejected(self):
        for path in (self.file(self.obj / 'foreign.h', b'bad'),
                     self.file(self.obj / 'nested/opt_param.h', b'bad'),
                     self.file(self.root / 'outside.h', b'bad')):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'foreign'):
                self.bind([path])

    def test_source_alias_resolves_but_escape_is_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.source, target_is_directory=True)
        self.assertEqual(self.bind([alias / 'sys/native.h']), self.bind([self.baseline]))
        outside = self.file(self.root / 'outside.h', b'bad')
        escape = self.source / 'escape.h'
        escape.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'foreign'):
            self.bind([escape])

    def test_generated_or_source_dependency_drift_is_rejected(self):
        for path in (self.generated, self.baseline):
            before = self.bind([path])
            path.write_bytes(b'changed')
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'set or bytes'):
                provenance.recheck_dependencies([path], before, self.source,
                    self.overlay, self.obj, self.patched)

    def test_added_or_removed_dependency_rejected(self):
        before = self.bind([self.baseline])
        for paths in ([], [self.baseline, self.generated]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                provenance.recheck_dependencies(paths, before, self.source,
                    self.overlay, self.obj, self.patched)

    def test_preprocessor_dependency_escaping_and_duplicates(self):
        spaced = self.file(self.source / 'name with space.h', b'spaced')
        dep = self.root / 'unit.d'
        escaped = str(spaced).replace(' ', chr(92) + ' ')
        dep.write_text('unit.o: ' + escaped + ' ' + chr(92) + '\n ' + str(self.generated) + '\n')
        self.assertEqual(provenance.dependency_paths(dep, self.obj), {spaced, self.generated})
        dep.write_text('no target')
        with self.assertRaises(ValueError):
            provenance.dependency_paths(dep, self.obj)

    def test_contradictory_archive_expectations_rejected(self):
        rows = self.bind([self.baseline])
        with self.assertRaisesRegex(ValueError, 'changed across owners'):
            provenance.archive_expectations({'sys/native.h': '0' * 64}, rows)


class ExplicitArchiveCLI(unittest.TestCase):
    def test_wrapper_forwards_archive_only_when_requested(self):
        common = ['--source', '/source', '--kernel-obj', '/obj',
                  '--output', '/new', '--toolchain', '/tools']
        for suffix in ([], ['--source-archive', '/verified.tar.gz']):
            with self.subTest(suffix=suffix), mock.patch.object(fileops.subprocess, 'run') as run:
                run.return_value.returncode = 0
                self.assertEqual(fileops.main(common + suffix), 0)
                command = run.call_args.args[0]
                if suffix:
                    self.assertIn('--source-archive', command)
                    self.assertEqual(command[command.index('--source-archive') + 1], suffix[1])
                else:
                    self.assertNotIn('--source-archive', command)

    def test_core_default_clean_git_checks_remain_guarded(self):
        import ast
        tree = ast.parse((ROOT / 'tools/build_hp_native_core_patch.py').read_text())
        guards = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == 'a.source_archive is None']
        self.assertEqual(len(guards), 1)
        body = ast.unparse(ast.Module(body=guards[0].body, type_ignores=[]))
        self.assertIn("'rev-parse', 'HEAD'", body)
        self.assertIn("'status', '--porcelain'", body)
        self.assertIn('wrong native source pin', body)
        self.assertIn('native reference dirty', body)




class PrivateExecutionInputs(unittest.TestCase):
    def test_private_git_environment_clears_all_repository_selectors(self):
        selectors = {name: 'foreign' for name in
                     ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR')}
        selectors.update(GIT_CEILING_DIRECTORIES='/foreign', F31_TEST_VALUE='retained')
        with mock.patch.dict(provenance.os.environ, selectors):
            environment = provenance.private_git_environment(Path('/private/new-output'))
            for key in selectors.keys() - {'GIT_CEILING_DIRECTORIES', 'F31_TEST_VALUE'}:
                self.assertNotIn(key, environment)
                self.assertEqual(provenance.os.environ[key], 'foreign')
            self.assertEqual(environment['GIT_CEILING_DIRECTORIES'], '/private')
            self.assertEqual(environment['F31_TEST_VALUE'], 'retained')

    def test_old_artifacts_record_absence_and_reject_every_changed_extension(self):
        for extension in ('o', 'd', 'su'):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / ('unit.' + extension)).write_bytes(b'original')
                before = provenance.snapshot_prior_artifacts(root, ['unit'])
                self.assertEqual(len(before), 3)
                self.assertEqual(sum(value is None for value in before.values()), 2)
                provenance.recheck_prior_artifacts(root, before)
                (root / ('unit.' + extension)).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    provenance.recheck_prior_artifacts(root, before)

    def test_old_artifact_creation_and_removal_are_rejected(self):
        for mode in ('creation', 'removal'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path = root / 'unit.d'
                if mode == 'removal':
                    path.write_bytes(b'old dependencies')
                before = provenance.snapshot_prior_artifacts(root, ['unit'])
                if mode == 'creation':
                    path.write_bytes(b'new dependencies')
                else:
                    path.unlink()
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    provenance.recheck_prior_artifacts(root, before)

    def test_old_artifact_symlinks_and_unsafe_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'outside').write_bytes(b'outside')
            (root / 'unit.su').symlink_to(root / 'outside')
            with self.assertRaisesRegex(ValueError, 'not a regular file'):
                provenance.snapshot_prior_artifacts(root, ['unit'])
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                provenance.snapshot_prior_artifacts(root, ['../outside'])

if __name__ == '__main__':
    unittest.main()
