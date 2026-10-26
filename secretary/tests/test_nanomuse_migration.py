import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('migration', Path(__file__).parents[1] / 'files/migrate-nanomuse.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MigrationTests(unittest.TestCase):
    def test_preserves_conflicts_credentials_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            docs, trial = root / 'documents', root / 'trial'
            docs.mkdir(); trial.mkdir()
            (docs / 'plan.md').write_text('original')
            (docs / '.silverbullet.auth.json').write_text('original-auth')
            (trial / '.silverbullet.auth.json').write_text('old-copy')
            (trial / 'plan.md').write_text('updated in NanoMuse')
            (trial / 'new.md').write_text('new')
            config = root / 'config.toml'
            config.write_text('[llm]\napi_key = "private-placeholder"\n[agent]\nworkspace = "trial"\nlanguage = "ja"\n')
            backup = m.migrate(docs, trial, config, root / 'backups')
            self.assertEqual((docs / 'plan.md').read_text(), 'updated in NanoMuse')
            self.assertEqual((backup / 'documents-before/plan.md').read_text(), 'original')
            self.assertEqual((backup / 'nanomuse-workspace-before/new.md').read_text(), 'new')
            self.assertEqual((docs / '.silverbullet.auth.json').read_text(), 'original-auth')
            self.assertTrue(trial.is_symlink())
            self.assertEqual(trial.resolve(), docs.resolve())
            self.assertIn('private-placeholder', config.read_text())
            self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
            self.assertIsNone(m.migrate(docs, trial, config, root / 'backups'))
            self.assertEqual(len(list((root / 'backups').iterdir())), 1)

    def test_refuses_symlinks_without_merging(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            docs, trial = root / 'documents', root / 'trial'
            docs.mkdir(); trial.mkdir()
            (trial / 'outside').symlink_to(root / 'unrelated')
            config = root / 'config.toml'
            config.write_text('[agent]\nworkspace = "trial"\n')
            with self.assertRaises(ValueError):
                m.migrate(docs, trial, config, root / 'backups')
            self.assertEqual(list(docs.iterdir()), [])
            self.assertTrue(trial.is_dir())
