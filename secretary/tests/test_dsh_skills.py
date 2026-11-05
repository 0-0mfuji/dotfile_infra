import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('dsh_skills', Path(__file__).parents[1] / 'tooling/dsh-skills.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DshSkillsTests(unittest.TestCase):
    def test_converts_names_and_updates_managed_content_idempotently(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'source'; dest = root / 'dest'
            (source / 'one').mkdir(parents=True)
            skill = source / 'one/SKILL.md'; skill.write_text('secretary_tools__translate')
            self.assertEqual(m.sync(source, dest), 1)
            self.assertEqual((dest / 'one/SKILL.md').read_text(), 'mcp__secretary_tools__translate')
            self.assertEqual(m.sync(source, dest), 1)
            skill.write_text('secretary_tools__dictionary')
            m.sync(source, dest)
            self.assertEqual((dest / 'one/SKILL.md').read_text(), 'mcp__secretary_tools__dictionary')

    def test_preserves_custom_skills_before_any_partial_update(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'source'; dest = root / 'dest'
            for name in ('a', 'z'):
                (source / name).mkdir(parents=True)
                (source / name / 'SKILL.md').write_text('original')
            m.sync(source, dest)
            (dest / 'z/SKILL.md').write_text('custom')
            (source / 'a/SKILL.md').write_text('update')
            with self.assertRaises(ValueError):
                m.sync(source, dest)
            self.assertEqual((dest / 'a/SKILL.md').read_text(), 'original')
            self.assertEqual((dest / 'z/SKILL.md').read_text(), 'custom')

class CodexConfigTests(unittest.TestCase):
    def test_keeps_native_model_auth_and_permission_settings(self):
        spec = importlib.util.spec_from_file_location('codex_config', Path(__file__).parents[1] / 'tooling/codex-config.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.toml'
            config.write_text('model = "chosen-model"\napproval_policy = "untrusted"\ncli_auth_credentials_store = "file"\n')
            self.assertTrue(module.configure(config))
            import tomlkit
            values = tomlkit.parse(config.read_text())
            self.assertEqual(values['model'], 'chosen-model')
            self.assertEqual(values['approval_policy'], 'untrusted')
            self.assertEqual(values['cli_auth_credentials_store'], 'file')
            self.assertEqual(values['mcp_servers']['secretary_tools']['command'], '/usr/bin/python3')
            self.assertFalse(module.configure(config))

    def test_conflicting_server_is_not_overwritten(self):
        spec = importlib.util.spec_from_file_location('codex_config_conflict', Path(__file__).parents[1] / 'tooling/codex-config.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.toml'
            before = '[mcp_servers.secretary]\ncommand="custom-server"\n'
            config.write_text(before)
            with self.assertRaises(ValueError):
                module.configure(config)
            self.assertEqual(config.read_text(), before)
