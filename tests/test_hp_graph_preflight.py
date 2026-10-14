#!/usr/bin/env python3
"""Portable negative controls for native input and symbol-owner gates.

Uses synthetic files/nm text, invokes no compiler, make, nm, or HP operation.
"""
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from hp_graph_preflight import (LINUX_PIN, NETBSD_PIN, configured_rules, digest,
                                preflight, relative_path, require_hp, selected_units)
from audit_hp_native_drm_symbol_owners import parse_nm, symbol_graph, verified_rows, verify_elf


class Inputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        work = Path(self.temp.name)
        self.tree, self.obj, self.tools = [work / n for n in ('src', 'obj', 'tools')]
        for path in (self.tree, self.obj, self.tools / 'bin', self.obj / 'machine'):
            path.mkdir(parents=True, exist_ok=True)
        self.groups = json.loads((ROOT / 'docs/evidence/HP_FULL_GRAPH_API_20261005.json').read_text())['graph']['units']
        self.rows = selected_units(self.groups)
        hashes = {}
        for row in self.rows:
            path = self.tree / 'sys' / row['source']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// synthetic input, not pinned reference content\n')
            hashes[row['source']] = digest(path)
        self.makefile = 'S= ' + str(self.tree / 'sys') + '\n'
        self.makefile += 'ALLFILES= ' + ' '.join(r['source'] for r in self.rows) + '\n'
        self.makefile += 'OBJS= drmkms.ko\nOBJS.drmkms= ' + ' '.join(r['object'] for r in self.rows) + '\n'
        (self.obj / 'Makefile').write_text(self.makefile)
        manifests = {}
        for path in ('i915drm/files.i915drmkms', 'drm/files.drmkms', 'ttm/files.ttm'):
            rel = 'sys/external/bsd/drm2/' + path
            file = self.tree / rel
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('// synthetic manifest\n')
            manifests[rel] = digest(file)
        for name in ('nbmake-amd64', 'x86_64--netbsd-gcc', 'x86_64--netbsd-nm'):
            (self.tools / 'bin' / name).write_text('fixture only, never executed')
        (self.obj / 'machine/cdefs.h').write_text('// generated ABI fixture')
        self.status = work / 'stage.json'
        self.state = dict(state='CONFIGURED', linux_pin=LINUX_PIN, netbsd_pin=NETBSD_PIN,
                          units=self.groups, source_sha256=hashes,
                          manifest_sha256=manifests, makefile_sha256=digest(self.obj / 'Makefile'))
        self.save()

    def save(self):
        self.status.write_text(json.dumps(self.state))

    def check(self):
        return preflight(self.tree, self.obj, self.tools, self.status)

    def test_full_frozen_selection(self):
        result = self.check()
        self.assertEqual(len(result['units']), 410)
        self.assertEqual(sum(r['group'] == 'i915' for r in result['units']), 323)
        self.assertEqual(result['state'], 'INPUTS_VERIFIED')

    def test_same_count_wrong_i915_source_rejected(self):
        self.groups['i915'][0] = 'invented.c'
        self.save()
        with self.assertRaisesRegex(ValueError, 'source set differs'):
            self.check()

    def test_missing_ttm_group_rejected(self):
        del self.groups['ttm']
        self.save()
        with self.assertRaises(ValueError):
            self.check()

    def test_old_unhashed_stage_rejected(self):
        del self.state['source_sha256']
        self.save()
        with self.assertRaisesRegex(ValueError, 'hash ledger required'):
            self.check()

    def test_modified_source_rejected(self):
        (self.tree / 'sys' / self.rows[0]['source']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'modified staged source'):
            self.check()

    def test_makefile_comment_cannot_select_missing_unit(self):
        row = self.rows[0]
        text = self.makefile.replace(row['source'] + ' ', '') + '# ' + row['source'] + '\n'
        (self.obj / 'Makefile').write_text(text)
        self.state['makefile_sha256'] = digest(self.obj / 'Makefile')
        self.save()
        with self.assertRaisesRegex(ValueError, 'ownership mismatch'):
            self.check()

    def test_same_basename_old_override_rejected(self):
        row = self.rows[0]
        text = self.makefile.replace(row['source'], 'old/' + row['object'].replace('.o', '.c'))
        (self.obj / 'Makefile').write_text(text)
        self.state['makefile_sha256'] = digest(self.obj / 'Makefile')
        self.save()
        with self.assertRaisesRegex(ValueError, 'another/missing source'):
            self.check()

    def test_modified_makefile_rejected(self):
        (self.obj / 'Makefile').write_text(self.makefile + '# drift\n')
        with self.assertRaisesRegex(ValueError, 'Makefile hash differs'):
            self.check()

    def test_allfiles_without_selected_object_rejected(self):
        self.makefile = self.makefile.replace('OBJS.drmkms= ', 'OBJS.unselected= ')
        (self.obj / 'Makefile').write_text(self.makefile)
        self.state['makefile_sha256'] = digest(self.obj / 'Makefile')
        self.save()
        with self.assertRaisesRegex(ValueError, 'missing configured attribute'):
            self.check()

    def test_generated_header_identity_drift_is_observable(self):
        original = self.check()
        (self.obj / 'machine/cdefs.h').write_text('// changed ABI')
        self.assertNotEqual(self.check()['generated_header_sha256'], original['generated_header_sha256'])

    def test_wrong_pin_rejected(self):
        self.state['netbsd_pin'] = 'other'
        self.save()
        with self.assertRaises(ValueError):
            self.check()

    def test_modified_manifest_rejected(self):
        (self.tree / next(iter(self.state['manifest_sha256']))).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'configuration manifest'):
            self.check()

    def test_missing_native_tool_rejected(self):
        (self.tools / 'bin/x86_64--netbsd-nm').unlink()
        with self.assertRaisesRegex(ValueError, 'missing native tool'):
            self.check()

    def test_provider_ledger_requires_actual_matching_artifact(self):
        inputs = self.check()
        row = self.rows[0]
        artifact = self.obj / row['object']
        header = bytearray(64)
        header[:7] = b'\x7fELF\x02\x01\x01'
        header[16:24] = b'\x01\x00\x3e\x00\x01\x00\x00\x00'
        header[52:54] = b'\x40\x00'
        artifact.write_bytes(header)
        report = self.status.parent / 'compile.json'
        record = dict(state='PASSED', source=row['source'], o_exit=0, d_exit=0,
                      source_unchanged=True, source_sha256=self.state['source_sha256'][row['source']],
                      artifact=dict(path=str(artifact), sha256=digest(artifact)))
        data = dict(preflight=inputs, units=[record])
        report.write_text(json.dumps(data))
        self.assertEqual(len(verified_rows([report], inputs)), 1)
        artifact.write_bytes(artifact.read_bytes() + b'drift')
        with self.assertRaisesRegex(ValueError, 'stale'):
            verified_rows([report], inputs)

    def test_failed_compile_cannot_be_marked_passed(self):
        inputs = self.check()
        report = self.status.parent / 'false-pass.json'
        report.write_text(json.dumps(dict(preflight=inputs, units=[dict(state='PASSED', o_exit=1)])))
        with self.assertRaisesRegex(ValueError, 'fresh dependency/compile evidence'):
            verified_rows([report], inputs)


class Symbols(unittest.TestCase):
    def object(self, defs=None, imports=(), weak=()):
        return dict(definitions=defs or {}, imports=imports, weak_imports=weak)

    def test_no_objects_never_pass(self):
        self.assertEqual(symbol_graph({}, [])['state'], 'GRAPH_OPEN')

    def test_unselected_object_cannot_close_an_import(self):
        objects = {'drm.o': self.object(imports=['copyout']), 'foreign.o': self.object({'copyout': 'T'})}
        self.assertEqual(symbol_graph(objects, ['drm.o'])['state'], 'GRAPH_OPEN')

    def test_truncated_elf_is_not_a_native_object(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / 'bad.o'
            obj.write_bytes(b'\x7fELF\x02\x01' + bytes(10) + b'\x01\x00\x3e\x00')
            with self.assertRaisesRegex(ValueError, 'ELF relocatable'):
                verify_elf(obj)

    def test_three_objects_do_not_close_323(self):
        graph = symbol_graph({str(i): self.object() for i in range(3)}, map(str, range(323)))
        self.assertEqual(len(graph['missing_objects']), 320)
        self.assertEqual(graph['state'], 'GRAPH_OPEN')

    def test_kernel_provider_resolves_exact_import(self):
        objects = {'drm.o': self.object(imports=['copyout']), 'kernel.o': self.object({'copyout': 'T'})}
        graph = symbol_graph(objects, objects)
        self.assertEqual(graph['state'], 'OBJECT_SYMBOL_CLOSURE')
        self.assertEqual(graph['edges']['copyout']['providers'][0]['object'], 'kernel.o')

    def test_unresolved_import_stays_open(self):
        objects = {'drm.o': self.object(imports=['drm_ioctl'])}
        self.assertEqual(symbol_graph(objects, objects)['unresolved_symbols'], ['drm_ioctl'])

    def test_old_and_modern_ioctl_conflict(self):
        objects = {'old.o': self.object({'drm_ioctl': 'T'}), 'modern.o': self.object({'drm_ioctl': 'T'})}
        self.assertIn('drm_ioctl', symbol_graph(objects, objects)['conflicting_strong_owners'])

    def test_weak_fallback_not_strong_conflict(self):
        objects = {'weak.o': self.object({'fn': 'W'}), 'strong.o': self.object({'fn': 'T'})}
        self.assertFalse(symbol_graph(objects, objects)['conflicting_strong_owners'])

    def test_common_owner_conflict_requires_review(self):
        objects = {'a.o': self.object({'data': 'C'}), 'b.o': self.object({'data': 'D'})}
        self.assertIn('data', symbol_graph(objects, objects)['conflicting_strong_owners'])

    def test_nm_weak_undefined_is_not_provider(self):
        defs, imports, weak = parse_nm('                 U drm_ioctl\n                 w optional\n00000001 T owner\n')
        self.assertEqual(defs, {'owner': 'T'})
        self.assertEqual(imports, {'drm_ioctl'})
        self.assertEqual(weak, {'optional'})

    def test_nm_garbage_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_nm('unsupported output')


class Safety(unittest.TestCase):
    def test_native_entrypoints_refuse_foreign_host_before_writes(self):
        # Run actual CLI entrypoints with nonexistent paths. They must stop
        # at host admission before any compiler/tool or output creation.
        import platform
        import socket
        if platform.system() == 'NetBSD' and socket.gethostname().split('.')[0] == 'hp-tpnw121':
            self.skipTest('foreign-host control is only for a non-HP test executor')
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'must-not-exist')
            common = ['--native-tree', '/absent/src', '--object-dir', '/absent/obj',
                      '--tool-dir', '/absent/tools', '--graph-status', '/absent/status.json']
            cases = {
                'hp_graph_preflight.py': common,
                'build_hp_native_drm_adapter.py': common + ['--output', output],
                'probe_hp_full_graph.py': common + ['--workspace', directory, '--output', output],
                'audit_hp_native_drm_symbol_owners.py': common + ['--build-status', '/absent/build.json', '--output', output],
                'prepare_hp_full_graph.py': ['--workspace', directory, '--linux-tree', '/absent/linux',
                    '--materialized-tree', '/absent/materialized', '--netbsd-tree', '/absent/netbsd', '--base-tool-dir', '/absent/tools'],
            }
            for script, args in cases.items():
                proc = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / script), *args], text=True, capture_output=True, timeout=15)
                self.assertNotEqual(proc.returncode, 0, script)
                self.assertIn('authorized only on hp-tpnw121', proc.stderr, script)
                self.assertFalse(Path(output).exists(), script)

    def test_foreign_os_and_similar_hostname_rejected(self):
        for system, host in [('Windows', 'hp-tpnw121'), ('NetBSD', 'hp-tpnw121-other')]:
            with patch('hp_graph_preflight.platform.system', return_value=system), patch('hp_graph_preflight.socket.gethostname', return_value=host):
                with self.assertRaises(ValueError):
                    require_hp()

    def test_path_escape_rejected(self):
        for name in ('../escape.c', '/absolute.c', 'foo\\bar.c'):
            with self.assertRaises(ValueError):
                relative_path(name)

    def test_ambiguous_object_rule_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous configured object owner'):
            configured_rules('S=/fixture/sys\nALLFILES=a.c\nOBJS=a.o\na.o: $S/a.c\na.o: $S/b.c\n', Path('/fixture'))


if __name__ == '__main__':
    unittest.main()
