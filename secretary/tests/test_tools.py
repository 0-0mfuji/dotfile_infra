import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tools = load('secretary_tools', ROOT / 'files/secretary-tools.py')
migration = load('tools_migration', ROOT / 'tooling/migrate-config.py')
importer = load('data_import', ROOT / 'files/import-tool-data.py')


class ConfigTests(unittest.TestCase):
    def test_preserves_credentials_rules_and_other_servers_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config.toml'
            config.write_text('''[llm]
api_key = "sample-private-value"
[sentinel]
mode = "strict"
always_ask_tools = ["send_email", "shell", "python_execute", "custom"]
[[sentinel.rules]]
tool = "custom"
action = "deny"
[[mcp.servers]]
name = "existing"
command = "unchanged"
''')
            self.assertTrue(migration.migrate(config, root / 'backups'))
            text = config.read_text()
            self.assertIn('sample-private-value', text)
            import tomlkit
            parsed = tomlkit.parse(text)
            self.assertEqual(parsed['sentinel']['mode'], 'strict')
            self.assertNotIn('python_execute', parsed['sentinel']['always_ask_tools'])
            self.assertIn('custom', parsed['sentinel']['always_ask_tools'])
            self.assertEqual(parsed['mcp']['servers'][0]['command'], 'unchanged')
            self.assertEqual(parsed['sentinel']['rules'][0]['action'], 'deny')
            self.assertFalse(migration.migrate(config, root / 'backups'))
            self.assertEqual(len(list((root / 'backups').iterdir())), 1)

    def test_tool_policies_preserve_local_read_vs_external_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config = root / 'config.toml'
            config.write_text((ROOT / 'files/nanomuse.toml').read_text())
            migration.migrate(config, root / 'backups')
            import tomlkit
            parsed = tomlkit.parse(config.read_text())
            policies = parsed['mcp']['servers'][-1]['tools']
            self.assertEqual(policies['translate']['risk'], 'moderate')
            self.assertFalse(policies['translate']['egress'])
            self.assertEqual(policies['run']['risk'], 'sensitive')
            self.assertEqual(policies['karakeep_write']['risk'], 'sensitive')


class ToolBoundaryTests(unittest.TestCase):
    def test_rejects_traversal_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); docs = root / 'docs'; docs.mkdir()
            (docs / 'outside').symlink_to(root)
            for name in ('../private', 'outside/private', str(root / 'private')):
                with self.assertRaises(ValueError):
                    tools.within(docs, name)

    def test_read_endpoint_cannot_write_or_change_destination(self):
        for args in (['bookmarks', 'delete', 'id'], ['--server-addr=http://elsewhere', 'whoami'],
                     ['bookmarks', 'get', 'id', '--api-key=secret']):
            with self.assertRaises(ValueError):
                tools.invoke('karakeep_read', {'args': args})

    def test_changed_source_cannot_execute(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'tool.py').write_text('changed')
            entry = {'path': 'tool.py', 'helper': False, 'sha256': hashlib.sha256(b'original').hexdigest()}
            with patch.object(tools, 'REPO', root), patch.object(tools, 'catalog', return_value={'tools': [entry]}):
                with self.assertRaises(ValueError):
                    tools.tool_entry('tool.py')

    def test_translation_refuses_overwrite_and_requires_one_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'existing.md').write_text('keep')
            with patch.object(tools, 'DOCS', root):
                for args in ({'output_file': 'new.md'}, {'text': 'source', 'input_file': 'input.md', 'output_file': 'new.md'},
                             {'text': 'source', 'output_file': 'existing.md'}):
                    with self.assertRaises(ValueError):
                        tools.invoke('translate', args)
            self.assertEqual((root / 'existing.md').read_text(), 'keep')

    def test_arguments_are_not_shell_commands(self):
        with self.assertRaises(ValueError):
            tools.validate_args('echo secret')
        self.assertEqual(tools.validate_args(['$(not-a-command)', 'value with spaces']), ['$(not-a-command)', 'value with spaces'])


class ImportTests(unittest.TestCase):
    def archive(self, name='data/source.txt', content=b'original', digest=None):
        stream = io.BytesIO()
        manifest = [{'path': name, 'size': len(content), 'sha256': digest or hashlib.sha256(content).hexdigest()}]
        with tarfile.open(fileobj=stream, mode='w') as archive:
            for path, data in [('manifest.json', json.dumps(manifest).encode()), ('data/' + name, content)]:
                info = tarfile.TarInfo(path); info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        stream.seek(0)
        return stream

    def test_resumable_verified_import_preserves_source_and_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(importer.import_stream(self.archive(), root), 1)
            self.assertEqual(importer.import_stream(self.archive(), root), 1)
            with self.assertRaises(ValueError):
                importer.import_stream(self.archive(content=b'conflict'), root)
            self.assertEqual((root / 'data/source.txt').read_bytes(), b'original')

    def test_bad_checksum_does_not_install_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                importer.import_stream(self.archive(digest='0' * 64), root)
            self.assertFalse((root / 'data/source.txt').exists())

    def test_rejects_traversal_secrets_and_source_code(self):
        for name in ('../outside', '.env', 'data/../../outside', 'tools/tool.py'):
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    importer.import_stream(self.archive(name=name), Path(folder))


if __name__ == '__main__':
    unittest.main()
