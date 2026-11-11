"""F49 exact two-owner Worker recovery tests; private fixtures, never native tools."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / 'tools'))
import recover_native_worker as recovery


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def encoded(document):
    return (json.dumps(document, indent=2, sort_keys=True) + '\n').encode()


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='f49-worker-test-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.repo = self.base / 'repository'
        for name in recovery.INPUTS:
            write(self.repo / name, (REPOSITORY / name).read_bytes())
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
            GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
            GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
            GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init', '-q')
        self.git('add', '--', *recovery.INPUTS)
        self.git('commit', '-q', '-m', 'private source identity fixture')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        pin = mock.patch.object(recovery, 'INPUT_COMMIT', self.commit)
        pin.start()
        self.addCleanup(pin.stop)
        self.patch = (self.repo / recovery.PATCH).read_bytes()
        self.sections = recovery.extract_sections(self.patch)

    def git(self, *arguments):
        return subprocess.check_output(['git', '-C', str(self.repo), *arguments],
                                       env=self.environment, stderr=subprocess.PIPE)

    def recover(self):
        return recovery.recover(self.repo)

    @contextlib.contextmanager
    def rebound_patch(self, raw):
        inputs = copy.deepcopy(recovery.INPUTS)
        inputs[recovery.PATCH].update(recovery.identity(raw))
        with mock.patch.object(recovery, 'INPUTS', inputs):
            yield

    def changed_first_header(self, section, transform):
        lines = section.splitlines(keepends=True)
        position = next(i for i, line in enumerate(lines) if line.startswith(b'@@ '))
        lines[position] = transform(lines[position])
        return b''.join(lines)

    def test_exact_positive_replay_and_source_only_provenance(self):
        result = self.recover()
        self.assertEqual(set(result['files']),
            {'linux_kthread.c', 'include/linux/kthread.h', 'provenance.json'})
        self.assertEqual(recovery.identity(result['files']['linux_kthread.c']),
            dict(size=19566, sha256='31d75082ff20da8d6cb5664c60dda8733555a572aafd40e8a82ed4f1774d2274',
                 blob='c8f72ebd33119c9a4e47cc58b3397074c0523887'))
        self.assertEqual(recovery.identity(result['files']['include/linux/kthread.h']),
            dict(size=4700, sha256='97c094ab5fbc3688334875500c23d5053186d35e6342d2668ce63659335b8814',
                 blob='87bfe919c26654f034351f97acffc88d138cd861'))
        proof = result['provenance']
        self.assertEqual(proof['state'], 'RECOVERED_SOURCE_ONLY_NOT_INSTALLED')
        self.assertEqual(proof['netbsd_pin'], '03d918f6d0e81fa05b8f1160eca0628ad39988a6')
        self.assertEqual(proof['repository_input_commit'], self.commit)
        self.assertEqual(len(result['inputs']), 7)
        self.assertEqual((proof['patch_owner_sections'], proof['applied_owner_sections'],
                          proof['unexecuted_owner_sections']), (14, 2, 12))
        self.assertEqual(len(result['audit']), 27)
        self.assertEqual(sum(row['owner'] == recovery.NATIVE_C for row in result['audit']), 25)
        self.assertEqual(sum(row['owner'] == recovery.NATIVE_H for row in result['audit']), 2)
        self.assertFalse(proof['historical_recipe_executed'])
        self.assertFalse(proof['whole_patch_applied'])
        for key in ('native_preprocessing', 'native_compilation', 'runtime'):
            self.assertEqual(proof[key], 'NOT_RUN')
        for key in ('linked', 'installed', 'booted'):
            self.assertIs(proof[key], False)
        self.assertEqual(json.loads(result['files']['provenance.json']), proof)
        self.assertEqual(recovery.validate_publication(result['files']), proof)

    def test_replay_is_reproducible_and_never_mutates_source_inputs(self):
        before = {name: (self.repo / name).read_bytes() for name in recovery.INPUTS}
        first, second = self.recover(), self.recover()
        self.assertEqual(first, second)
        self.assertEqual({name: (self.repo / name).read_bytes() for name in recovery.INPUTS}, before)
        self.assertEqual(self.git('status', '--porcelain'), b'')
        self.assertFalse((self.repo / recovery.OUTPUT_ROOT).exists())

    def test_original_fragments_and_checked_fini_result_are_preserved(self):
        result = self.recover()
        source, header = result['files']['linux_kthread.c'], result['files']['include/linux/kthread.h']
        self.assertTrue(source.endswith((self.repo / recovery.FRAGMENT_C).read_bytes()))
        self.assertEqual(header.count((self.repo / recovery.FRAGMENT_H).read_bytes()), 1)
        checked = (b'void\nlinux_kthread_fini(void)\n{\n\tint error;\n\n'
                   b'\terror = linux_task_system_fini();\n\tKASSERT(error == 0);\n}\n')
        self.assertEqual(source.count(checked), 1)
        self.assertIn(b'linux_kthread_wake_locked', source)
        self.assertIn(b'linux_kthread_wake_locked', header)
        self.assertEqual(result['provenance']['definition_ownership']['task_system_fini_checked'],
                         dict(file='linux_kthread.c', call_line=86, assertion_line=87))
        self.assertFalse(result['provenance']['historical_recipe']['executed'])

    def test_every_raw_patch_fragment_recipe_and_integration_input_is_authenticated(self):
        for name in recovery.INPUTS:
            path = self.repo / name
            original = path.read_bytes()
            path.write_bytes(original + b' altered fixture input\n')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'working bytes differ'):
                self.recover()
            path.write_bytes(original)

    def test_selected_and_unselected_patch_tampering_both_fail_whole_authority(self):
        selected = self.patch.replace(b'linux_kthread', b'linux_Kthread', 1)
        unselected = b'# changed unselected patch envelope\n' + self.patch
        for raw in (selected, unselected):
            with self.subTest(size=len(raw)), self.assertRaisesRegex(ValueError, 'whole patch identity'):
                recovery.extract_sections(raw)

    def test_real_git_commit_must_bind_each_correct_working_path(self):
        self.git('rm', '--cached', '--', recovery.BASE_C)
        self.git('commit', '-q', '-m', 'private missing source path')
        different = self.git('rev-parse', 'HEAD').decode().strip()
        with mock.patch.object(recovery, 'INPUT_COMMIT', different):
            with self.assertRaisesRegex(ValueError, 'committed mode/path/blob differs'):
                self.recover()

    def test_git_identity_reads_ignore_inherited_directory_and_replacement_selectors(self):
        with mock.patch.dict(os.environ, GIT_DIR='/missing', GIT_COMMON_DIR='/missing',
                             GIT_WORK_TREE='/missing', GIT_INDEX_FILE='/missing',
                             GIT_REPLACE_REF_BASE='refs/forbidden'):
            self.assertEqual(len(self.recover()['audit']), 27)

    def test_direct_and_parent_input_aliases_are_rejected(self):
        path = self.repo / recovery.BASE_C
        original = path.read_bytes()
        external = write(self.base / 'external.c', original)
        path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'aliased input'):
            self.recover()
        path.unlink()
        path.write_bytes(original)
        parent = path.parent
        moved = parent.with_name('actual-base')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliased input'):
            self.recover()

    def test_only_two_selected_sections_are_returned(self):
        self.assertEqual(set(self.sections), {recovery.NATIVE_C, recovery.NATIVE_H})
        for owner, section in self.sections.items():
            self.assertEqual(len(section), recovery.SECTIONS[owner]['size'])
            self.assertEqual(hashlib.sha256(section).hexdigest(), recovery.SECTIONS[owner]['sha256'])

    def test_rebound_duplicate_or_missing_owner_is_rejected(self):
        starts = list(re.finditer(rb'^--- a/', self.patch, re.M))
        last = self.patch[starts[-1].start():]
        for raw in (self.patch + last, self.patch[:starts[-1].start()]):
            with self.subTest(size=len(raw)), self.rebound_patch(raw):
                with self.assertRaisesRegex(ValueError, 'fourteen|duplicate'):
                    recovery.extract_sections(raw)

    def test_rebound_cross_owner_headers_are_rejected(self):
        raw = self.patch.replace(b'+++ b/' + recovery.NATIVE_C.encode() + b'\n',
                                 b'+++ b/' + recovery.NATIVE_H.encode() + b'\n', 1)
        with self.rebound_patch(raw), self.assertRaisesRegex(ValueError, 'cross-owner'):
            recovery.extract_sections(raw)

    def test_rebound_unselected_owner_aliases_are_rejected(self):
        owners = re.findall(rb'^--- a/([^\n]+)\n', self.patch, re.M)
        owner = next(name for name in owners if name.decode() not in recovery.SECTIONS)
        for alias in (b'/' + owner, owner.replace(b'/', b'//', 1),
                      b'../' + owner, owner.replace(b'/', b'\\', 1)):
            raw = self.patch.replace(b'--- a/' + owner + b'\n', b'--- a/' + alias + b'\n', 1)
            raw = raw.replace(b'+++ b/' + owner + b'\n', b'+++ b/' + alias + b'\n', 1)
            with self.subTest(alias=alias), self.rebound_patch(raw):
                with self.assertRaisesRegex(ValueError, 'noncanonical'):
                    recovery.extract_sections(raw)

    def test_rebound_selected_section_identity_still_requires_exact_original_bytes(self):
        section = self.sections[recovery.NATIVE_C]
        raw = self.patch.replace(section, section.replace(b'linux_task_system_fini',
                                                         b'linux_task_system_finX', 1))
        with self.rebound_patch(raw), self.assertRaisesRegex(ValueError, 'selected patch section identity'):
            recovery.extract_sections(raw)

    def test_strict_replay_rejects_wrong_old_context_in_each_owner(self):
        for base, owner in ((recovery.BASE_C, recovery.NATIVE_C),
                            (recovery.BASE_H, recovery.NATIVE_H)):
            raw = (self.repo / base).read_bytes()
            changed = b'changed original first line\n' + raw.split(b'\n', 1)[1]
            # Alter the exact first consumed context, rather than an unrelated prefix.
            section = self.sections[owner]
            first_context = next(line[1:] for line in section.splitlines(keepends=True)[2:]
                                 if line[:1] in (b' ', b'-'))
            self.assertIn(first_context, raw)
            changed = raw.replace(first_context, first_context.replace(first_context[:1], b'X', 1), 1)
            with self.subTest(owner=owner), self.assertRaisesRegex(ValueError, 'old context'):
                recovery.apply_selected(changed, section)

    def test_strict_replay_rejects_old_and_new_hunk_positions(self):
        section = self.sections[recovery.NATIVE_C]
        changes = (
            lambda line: re.sub(rb'@@ -(\d+)', lambda m: b'@@ -' + str(int(m[1]) + 1).encode(), line, count=1),
            lambda line: re.sub(rb'\+(\d+)', lambda m: b'+' + str(int(m[1]) + 1).encode(), line, count=1))
        for index, change in enumerate(changes):
            changed = self.changed_first_header(section, change)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'context|position'):
                recovery.apply_selected((self.repo / recovery.BASE_C).read_bytes(), changed)

    def test_strict_replay_rejects_old_and_new_hunk_line_counts(self):
        section = self.sections[recovery.NATIVE_C]
        changes = (
            lambda line: re.sub(rb'-(\d+),(\d+)', lambda m: b'-' + m[1] + b',' + str(int(m[2])+1).encode(), line, count=1),
            lambda line: re.sub(rb'\+(\d+),(\d+)', lambda m: b'+' + m[1] + b',' + str(int(m[2])+1).encode(), line, count=1))
        for index, change in enumerate(changes):
            changed = self.changed_first_header(section, change)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'line counts'):
                recovery.apply_selected((self.repo / recovery.BASE_C).read_bytes(), changed)

    def test_strict_replay_rejects_reordered_and_removed_hunks(self):
        section = self.sections[recovery.NATIVE_C]
        markers = [match.start() for match in re.finditer(rb'^@@ ', section, re.M)]
        prefix = section[:markers[0]]
        hunks = [section[start:stop] for start, stop in zip(markers, markers[1:] + [len(section)])]
        variants = (prefix + hunks[1] + hunks[0] + b''.join(hunks[2:]),
                    prefix + b''.join(hunks[:-1]))
        for raw in variants:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                recovery.apply_selected((self.repo / recovery.BASE_C).read_bytes(), raw)

    def test_strict_replay_rejects_unsupported_no_newline_marker_and_truncated_payload(self):
        section = self.sections[recovery.NATIVE_C]
        variants = (section[:-1], section + b'\\ No newline at end of file\n')
        for raw in variants:
            with self.subTest(size=len(raw)), self.assertRaisesRegex(ValueError, 'payload|newline'):
                recovery.apply_selected((self.repo / recovery.BASE_C).read_bytes(), raw)

    def test_strict_replay_rejects_cross_owner_selected_headers(self):
        section = self.sections[recovery.NATIVE_C].replace(
            b'+++ b/' + recovery.NATIVE_C.encode() + b'\n',
            b'+++ b/' + recovery.NATIVE_H.encode() + b'\n', 1)
        with self.assertRaisesRegex(ValueError, 'selected owner'):
            recovery.apply_selected((self.repo / recovery.BASE_C).read_bytes(), section)

    def test_generation_executes_only_readonly_git_and_never_historical_or_native_tools(self):
        real_run = recovery.subprocess.run
        commands = []
        def checked_run(argv, *args, **kwargs):
            commands.append(argv)
            self.assertEqual(Path(argv[0]).name, 'git')
            self.assertIn('ls-tree', argv)
            return real_run(argv, *args, **kwargs)
        with mock.patch.object(recovery.subprocess, 'run', side_effect=checked_run):
            self.assertEqual(len(self.recover()['audit']), 27)
        self.assertEqual(len(commands), len(recovery.INPUTS))

    def test_publication_validates_every_payload_before_creating_an_output(self):
        result = self.recover()
        for name in result['files']:
            changed = dict(result['files'])
            changed[name] += b' altered'
            output = self.base / ('rejected-' + str(len(name)))
            with self.subTest(name=name), self.assertRaises(ValueError):
                recovery.publish_fresh(output, changed)
            self.assertFalse(output.exists())

    def test_publication_rejects_foreign_file_set_before_creating_any_path(self):
        files = self.recover()['files']
        for name in ('../escaped.c', '/absolute.c', 'include\\linux\\kthread.h'):
            changed = dict(files)
            changed[name] = b'foreign'
            output = self.base / 'rejected-files'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'three output files'):
                recovery.publish_fresh(output, changed)
            self.assertFalse(output.exists())

    def test_publication_rejects_rebound_provenance_identity_scope_and_unknown_fields(self):
        result = self.recover()
        mutations = (
            lambda d: d.update(schema=True),
            lambda d: d.update(netbsd_pin='0' * 40),
            lambda d: d.update(repository_input_commit='0' * 40),
            lambda d: d.update(recovery_tool_sha256='0' * 64),
            lambda d: d.update(native_compilation='PASS'),
            lambda d: d.update(linked=0),
            lambda d: d.update(installed=1),
            lambda d: d.update(extra_unreviewed='field'),
            lambda d: d.update(open_gates=[]),
            lambda d: d['historical_recipe'].update(executed=True),
            lambda d: d['definition_ownership']['linux_kthread_wake_locked'].update(line=1),
            lambda d: d['historical_integration'].update(interpretation='new native result'))
        for index, change in enumerate(mutations):
            proof = copy.deepcopy(result['provenance'])
            change(proof)
            files = dict(result['files'], **{'provenance.json': encoded(proof)})
            output = self.base / 'rejected-proof'
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'provenance'):
                recovery.publish_fresh(output, files)
            self.assertFalse(output.exists())

    def test_publication_rejects_twenty_seven_fake_reordered_or_crosslinked_audit_rows(self):
        result = self.recover()
        changes = (lambda d: d.update(operations=[{}] * 27),
                   lambda d: d['operations'].reverse(),
                   lambda d: d['operations'][0].update(old_start=1),
                   lambda d: d['operations'][0].update(hunk_sha256='0' * 64))
        for index, change in enumerate(changes):
            proof = copy.deepcopy(result['provenance'])
            change(proof)
            files = dict(result['files'], **{'provenance.json': encoded(proof)})
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'operation audit'):
                recovery.validate_publication(files)

    def test_publication_rejects_duplicate_provenance_keys_after_outer_json_rebinding(self):
        result = self.recover()
        proof = result['provenance']
        raw = b'{"schema":1,' + encoded(proof).lstrip()[1:]
        files = dict(result['files'], **{'provenance.json': raw})
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            recovery.publish_fresh(self.base / 'rejected-duplicate', files)
        self.assertFalse((self.base / 'rejected-duplicate').exists())

    def test_existing_file_directory_symlink_and_parent_alias_are_preserved(self):
        files = self.recover()['files']
        file = write(self.base / 'existing-file', b'keep original')
        directory = self.base / 'existing-directory'
        directory.mkdir()
        sentinel = write(directory / 'sentinel', b'keep directory')
        link = self.base / 'existing-link'
        link.symlink_to(directory, target_is_directory=True)
        dangling = self.base / 'dangling'
        dangling.symlink_to(self.base / 'missing')
        for output in (file, directory, link, dangling):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'preserve existing'):
                recovery.publish_fresh(output, files)
        self.assertEqual(file.read_bytes(), b'keep original')
        self.assertEqual(sentinel.read_bytes(), b'keep directory')
        alias = self.base / 'aliased-parent'
        alias.symlink_to(directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'aliased output'):
            recovery.publish_fresh(alias / 'new-worker', files)
        self.assertFalse((directory / 'new-worker').exists())

    def test_complete_fresh_publication_reads_back_three_files_and_provenance_is_last(self):
        files = self.recover()['files']
        output = self.base / 'published'
        real_open = Path.open
        observed = []
        def checked_open(path, mode='r', *args, **kwargs):
            if path.is_relative_to(output) and 'x' in mode:
                relative = path.relative_to(output).as_posix()
                if relative == 'provenance.json':
                    self.assertEqual((output / 'linux_kthread.c').read_bytes(), files['linux_kthread.c'])
                    self.assertEqual((output / 'include/linux/kthread.h').read_bytes(), files['include/linux/kthread.h'])
                observed.append(relative)
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(Path, 'open', checked_open):
            result = recovery.publish_fresh(output, dict(reversed(list(files.items()))))
        self.assertEqual(result['state'], 'RECOVERED_SOURCE_ONLY_NOT_INSTALLED')
        self.assertEqual(observed[-1], 'provenance.json')
        for name, raw in files.items():
            self.assertEqual((output / name).read_bytes(), raw)
        self.assertEqual(self.git('status', '--porcelain'), b'')

    def test_failed_second_owner_write_retains_partial_directory_without_provenance(self):
        files = self.recover()['files']
        output = self.base / 'partial'
        real_open = Path.open
        writes = []
        def failing_open(path, mode='r', *args, **kwargs):
            if path.is_relative_to(output) and 'x' in mode:
                writes.append(path.relative_to(output).as_posix())
                if len(writes) == 2:
                    raise OSError('injected second owner write failure')
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(Path, 'open', failing_open):
            with self.assertRaisesRegex(OSError, 'second owner write failure'):
                recovery.publish_fresh(output, files)
        self.assertTrue(output.is_dir())
        self.assertEqual((output / 'linux_kthread.c').read_bytes(), files['linux_kthread.c'])
        self.assertFalse((output / 'provenance.json').exists())
        with self.assertRaisesRegex(ValueError, 'preserve existing'):
            recovery.publish_fresh(output, files)
        self.assertEqual((output / 'linux_kthread.c').read_bytes(), files['linux_kthread.c'])

    def test_failed_provenance_write_retains_both_owners_without_a_success_proof(self):
        files = self.recover()['files']
        output = self.base / 'partial-proof'
        real_open = Path.open
        def failing_open(path, mode='r', *args, **kwargs):
            if path == output / 'provenance.json' and 'x' in mode:
                raise OSError('injected provenance write failure')
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(Path, 'open', failing_open):
            with self.assertRaisesRegex(OSError, 'provenance write failure'):
                recovery.publish_fresh(output, files)
        self.assertEqual((output / 'linux_kthread.c').read_bytes(), files['linux_kthread.c'])
        self.assertEqual((output / 'include/linux/kthread.h').read_bytes(), files['include/linux/kthread.h'])
        self.assertFalse((output / 'provenance.json').exists())

    def test_default_cli_reports_derivation_without_materializing_fixed_output(self):
        result = io.StringIO()
        with mock.patch.object(recovery, 'REPOSITORY', self.repo), \
             mock.patch.object(sys, 'argv', ['recover_native_worker.py']), \
             contextlib.redirect_stdout(result):
            recovery.main()
        report = json.loads(result.getvalue())
        self.assertEqual(report['state'], 'VERIFIED_DERIVATION_ONLY_NO_WRITE')
        self.assertEqual(report['operations'], 27)
        self.assertFalse((self.repo / recovery.OUTPUT_ROOT).exists())
        self.assertEqual(self.git('status', '--porcelain'), b'')

    def test_cli_accepts_write_only_at_the_fixed_private_fixture_repository_location(self):
        with mock.patch.object(recovery, 'REPOSITORY', self.repo), \
             mock.patch.object(sys, 'argv', ['recover_native_worker.py', '--write']), \
             contextlib.redirect_stdout(io.StringIO()):
            recovery.main()
        output = self.repo / recovery.OUTPUT_ROOT
        self.assertTrue(output.is_relative_to(self.base))
        self.assertEqual((output / 'linux_kthread.c').read_bytes(),
                         self.recover()['files']['linux_kthread.c'])
        self.assertFalse((REPOSITORY / recovery.OUTPUT_ROOT).is_relative_to(self.base))

    def test_cli_rejects_output_override_before_any_recovery_or_publication(self):
        with mock.patch.object(recovery, 'recover') as called, \
             mock.patch.object(sys, 'argv', ['recover_native_worker.py', '--output', str(self.base/'foreign')]), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                recovery.main()
        self.assertEqual(raised.exception.code, 2)
        called.assert_not_called()


if __name__ == '__main__':
    unittest.main()
