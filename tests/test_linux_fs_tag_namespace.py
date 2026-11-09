import importlib.util
from pathlib import Path
import tempfile
import unittest
import hashlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fs_tag_namespace', ROOT/'tools/namespace_linux_fs_tags.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TagLexer(unittest.TestCase):
    def test_linux_page_offset_typedef_does_not_redeclare_native_signed_offset(self):
        src='pgoff_t index; pgoff_t x; char *s="pgoff_t"; /* pgoff_t */\n#include <linux/pgoff_t.h>\n'
        out, counts=module.translate(src)
        self.assertEqual(out,'linux_pgoff_t index; linux_pgoff_t x; char *s="pgoff_t"; /* pgoff_t */\n#include <linux/pgoff_t.h>\n')
        self.assertEqual(counts['identifier:pgoff_t'],2)

    def test_directive_comments_and_zero_header_whitespace_are_preserved(self):
        for src in ('#include/* owner */<linux/fs.h>\n',
                    '# /* owner */ include <linux/fs.h>\n',
                    '#include<linux/fs.h>\n',
                    '/* prefix */ #include <linux/fs.h>\n'):
            with self.subTest(src=src):
                out, counts = module.translate(src, {'linux/fs.h':'linux/fs_netbsd.h'})
                self.assertEqual(out, src.replace('linux/fs.h','linux/fs_netbsd.h'))
                self.assertEqual(counts['include:linux/fs.h'],1)

    def test_multiline_directive_comments_keep_all_physical_newlines(self):
        for src in ('/* prefix\n*/#include <linux/fs.h>\n',
                    '#include /* owner\n comment */ <linux/fs.h>\n'):
            out, _ = module.translate(src, {'linux/fs.h':'linux/fs_netbsd.h'})
            self.assertEqual(out, src.replace('linux/fs.h','linux/fs_netbsd.h'))
            self.assertEqual(out.count('\n'),src.count('\n'))

    def test_comment_newline_cannot_make_midline_hash_a_directive(self):
        src = 'ordinary /* comment\n*/ #include <linux/fs.h>\n'
        self.assertEqual(module.translate(src, {'linux/fs.h':'linux/fs_netbsd.h'})[0],src)

    def test_comment_contents_never_become_provider_directives(self):
        src = '/*\n#include <linux/fs.h>\n*/\n// #include <linux/fs.h>\nchar *s="#include <linux/fs.h>";'
        self.assertEqual(module.translate(src, {'linux/fs.h':'linux/fs_netbsd.h'})[0],src)

    def test_spliced_directive_and_comment_tokens_use_logical_spelling(self):
        src = '#inc\\\nlude /\\\n*owner*\\\n/ <linux/fi\\\nle.h>\n'
        out, counts = module.translate(src, {'linux/file.h':'linux/file_api_netbsd.h'})
        self.assertEqual(out, '#inc\\\nlude /\\\n*owner*\\\n/ <linux/file_api_netbsd.h\\\n>\n')
        self.assertEqual(counts['include:linux/file.h'],1)

    def test_digraph_directive_and_commented_include_next(self):
        src = '%:include/*owner*/"linux/fs.h"\n'
        self.assertEqual(module.translate(src, {'linux/fs.h':'linux/fs_netbsd.h'})[0],
                         src.replace('linux/fs.h','linux/fs_netbsd.h'))
        with self.assertRaisesRegex(ValueError,'include_next'):
            module.translate('#/**/include_next/**/<linux/fs.h>',{'linux/fs.h':'linux/fs_netbsd.h'})

    def test_explicit_unique_provider_includes_preserve_other_tokens(self):
        src = '#include <linux/fs.h>\n#include "linux/file.h"\n#include <sys/file.h>\nchar *s="linux/fs.h"; struct file *p;'
        out, counts = module.translate(src, {'linux/fs.h':'linux/fs_netbsd.h',
                                            'linux/file.h':'linux/file_api_netbsd.h'})
        self.assertEqual(out, '#include <linux/fs_netbsd.h>\n#include "linux/file_api_netbsd.h"\n#include <sys/file.h>\nchar *s="linux/fs.h"; struct linux_file *p;')
        self.assertEqual(counts['include:linux/fs.h'],1)

    def test_include_splices_keep_physical_line_count(self):
        src = '#include \\\n <linux/fi\\\nle.h>\n'
        out, _ = module.translate(src, {'linux/file.h':'linux/file_api_netbsd.h'})
        self.assertEqual(out, '#include \\\n <linux/file_api_netbsd.h\\\n>\n')
        self.assertEqual(src.count('\n'),out.count('\n'))

    def test_arbitrary_include_mapping_and_include_next_refused(self):
        with self.assertRaisesRegex(ValueError,'unqualified'):
            module.translate('#include <sys/file.h>', {'sys/file.h':'linux/fs_netbsd.h'})
        with self.assertRaisesRegex(ValueError,'include_next'):
            module.translate('#include_next <linux/fs.h>', {'linux/fs.h':'linux/fs_netbsd.h'})

    def test_tags_and_separate_ordinary_identifier_names(self):
        src = 'struct file *file; struct inode *inode; struct address_space *mapping;'
        out, counts = module.translate(src)
        self.assertEqual(out, 'struct linux_file *file; struct linux_inode *inode; struct linux_address_space *mapping;')
        self.assertEqual(counts, dict(file=1, inode=1, address_space=1, folio=0))

    def test_folio_tag_is_unique_and_ordinary_name_is_retained(self):
        out, counts = module.translate('struct folio *folio; struct page *page; folio_put(folio);')
        self.assertEqual(out,'struct linux_folio *folio; struct page *page; folio_put(folio);')
        self.assertEqual(counts['folio'],1)

    def test_comments_strings_includes_and_non_tags_are_untouched(self):
        src = '#include <linux/file.h>\nchar *s="struct file"; /* struct inode */\nfile(inode); // struct file\n'
        self.assertEqual(module.translate(src)[0], src)

    def test_tag_comments_and_lines_preserve_qualifiers(self):
        self.assertEqual(module.translate('const struct /* x */\nfile *p;')[0],
                         'const struct /* x */\nlinux_file *p;')

    def test_anonymous_struct_member_is_not_a_tag(self):
        src = 'struct { file member; int inode; } x;'
        self.assertEqual(module.translate(src)[0], src)

    def test_macro_tag_and_unrelated_struct_are_distinguished(self):
        self.assertEqual(module.translate('#define P struct file\nstruct file_ops *p;')[0],
                         '#define P struct linux_file\nstruct file_ops *p;')

    def test_rewrite_is_idempotent(self):
        once = module.translate('struct file *p;')[0]
        self.assertEqual(module.translate(once)[0], once)

    def test_c_phase_two_splices_preserve_physical_lines_and_rename_real_tags(self):
        src = 'str\\\nuct fi\\\nle *file; struct \\\n inode *inode;'
        expected = 'str\\\nuct linux_fi\\\nle *file; struct \\\n linux_inode *inode;'
        self.assertEqual(module.translate(src)[0], expected)

    def test_spliced_comment_delimiters_never_authorize_tag_rewrites(self):
        src = '/\\\n* struct file *\\\n/\nstruct inode *i;'
        self.assertEqual(module.translate(src)[0], '/\\\n* struct file *\\\n/\nstruct linux_inode *i;')

    def test_continued_include_and_crlf_splices_are_preserved(self):
        src = '#include \\\n <linux/file.h>\nstruct \\\r\nfile *p;'
        self.assertEqual(module.translate(src)[0], '#include \\\n <linux/file.h>\nstruct \\\r\nlinux_file *p;')


class OwnedIntegration(unittest.TestCase):
    def provider(self, tree):
        rel = 'sys/external/bsd/drm2/include/linux/fs_netbsd.h'
        header = tree/rel
        header.parent.mkdir(parents=True)
        header.write_text('/* explicit real-provider header input */\n',encoding='utf8')
        return dict(version=1,scope='LINUX_OWNED_INCLUDES',
                    linux_pin='fd179f8a05be3ccae366b9b96e176b51fbe54aab',
                    includes={'linux/fs.h':dict(target='linux/fs_netbsd.h',path=rel,sha256=module.digest(header))})

    def test_provider_redirect_is_limited_to_owned_inputs_and_existing_digest(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);tree,path,receipt=self.setup_tree(base)
            path.write_text('#include <linux/fs.h>\nstruct file *f;\n',encoding='utf8')
            receipt['compiler_math_namespace']['seeds'][0]['sha256']=module.digest(path)
            provider=self.provider(tree)
            native=tree/'sys/sys/file.h';native.parent.mkdir(parents=True)
            native.write_text('#include <linux/fs.h>\nstruct file *native;\n',encoding='utf8')
            before=native.read_bytes()
            result=module.integrate(tree,receipt,base/'receipt.json',provider)
            self.assertIn('#include <linux/fs_netbsd.h>',path.read_text())
            self.assertEqual(native.read_bytes(),before)
            self.assertEqual(result['include_mapping'],{'linux/fs.h':'linux/fs_netbsd.h'})

    def test_provider_drift_rejected_before_any_source_write(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);tree,path,receipt=self.setup_tree(base)
            provider=self.provider(tree)
            (tree/provider['includes']['linux/fs.h']['path']).write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):
                module.integrate(tree,receipt,base/'receipt.json',provider)
            self.assertEqual(path.read_text(),'struct file *f;\n')
            self.assertFalse((base/'receipt.json').exists())

    def test_native_alias_cannot_be_admitted_as_unique_provider(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);tree,path,receipt=self.setup_tree(base)
            provider=self.provider(tree)
            provider['includes']['linux/fs.h']['path']='sys/sys/file.h'
            with self.assertRaisesRegex(ValueError,'path/digest'):
                module.integrate(tree,receipt,base/'receipt.json',provider)

    def setup_tree(self, base):
        tree = base/'tree'; tree.mkdir()
        rel = 'sys/external/bsd/drm2/dist/drm/test.c'
        path = tree/rel; path.parent.mkdir(parents=True); path.write_text('struct file *f;\n', encoding='utf8')
        receipt = dict(linux_pin='fd179f8a05be3ccae366b9b96e176b51fbe54aab', rows=[],
                       compiler_math_namespace=dict(tokenizer_version=2, seeds=[
                           dict(path=rel, sha256=module.digest(path))]))
        return tree, path, receipt

    def test_transform_requires_exact_prior_owned_hash(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            path.write_text('struct inode *i;\n',encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'changed since'):
                module.integrate(tree,receipt,base/'receipt.json')
            self.assertFalse((base/'receipt.json').exists())

    def test_only_dist_owned_sources_are_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            tree,path,receipt=self.setup_tree(Path(d))
            receipt['compiler_math_namespace']['seeds'][0]['path']='sys/sys/file.h'
            with self.assertRaisesRegex(ValueError,'unqualified'):
                module.owned_inputs(receipt)

    def test_success_records_complete_digest_chain(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            result=module.integrate(tree,receipt,base/'receipt.json')
            self.assertEqual(result['state'],'APPLIED')
            self.assertEqual(path.read_text(encoding='utf8'),'struct linux_file *f;\n')
            self.assertEqual(result['files'][0]['after_sha256'],module.digest(path))

    def test_empty_or_native_only_receipt_does_not_authorize_writes(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            receipt['compiler_math_namespace']['seeds']=[]
            with self.assertRaisesRegex(ValueError,'empty'):
                module.integrate(tree,receipt,base/'receipt.json')
            self.assertEqual(path.read_text(encoding='utf8'),'struct file *f;\n')

    def test_noncanonical_source_alias_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            receipt['compiler_math_namespace']['seeds'][0]['path']='sys/external/bsd/drm2/dist/drm//test.c'
            with self.assertRaisesRegex(ValueError,'unqualified'):
                module.integrate(tree,receipt,base/'receipt.json')
            self.assertEqual(path.read_text(encoding='utf8'),'struct file *f;\n')

    def test_intermediate_dist_symlink_cannot_rewrite_native_header(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            native=tree/'sys/external/bsd/drm2/include/linux'; native.mkdir(parents=True)
            header=native/'owner.h'; header.write_text('struct file *native;\n',encoding='utf8')
            alias=tree/'sys/external/bsd/drm2/dist/alias'
            try:
                alias.symlink_to(native, target_is_directory=True)
            except OSError as error:
                self.skipTest(str(error))
            receipt['compiler_math_namespace']['seeds']=[dict(
                path='sys/external/bsd/drm2/dist/alias/owner.h',sha256=module.digest(header))]
            with self.assertRaisesRegex(ValueError,'canonical dist owner'):
                module.integrate(tree,receipt,base/'receipt.json')
            self.assertEqual(header.read_text(encoding='utf8'),'struct file *native;\n')

    def test_concurrently_created_source_temp_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            temporary=path.with_name(path.name+'.fs-tags.tmp')
            original_open=Path.open
            def opening(target, mode='r', *args, **kwargs):
                if target == temporary and mode == 'xb':
                    with original_open(target,'wb') as stream:
                        stream.write(b'preserved concurrent work')
                return original_open(target,mode,*args,**kwargs)
            with patch.object(Path,'open',opening):
                with self.assertRaises(FileExistsError):
                    module.integrate(tree,receipt,base/'receipt.json')
            self.assertEqual(temporary.read_bytes(),b'preserved concurrent work')
            self.assertEqual(path.read_text(encoding='utf8'),'struct file *f;\n')

    def test_interrupted_receipt_temp_prevents_any_source_write(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); tree,path,receipt=self.setup_tree(base)
            output=base/'receipt.json'
            temporary=base/'receipt.json.fs-tags-receipt.tmp'
            temporary.write_text('preserved receipt fragment',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'interrupted tag receipt'):
                module.integrate(tree,receipt,output)
            self.assertEqual(path.read_text(encoding='utf8'),'struct file *f;\n')
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
