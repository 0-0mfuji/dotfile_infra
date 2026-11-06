import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('study_resume', Path(__file__).resolve().parents[1] / 'files/study-resume.py')
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)


class MigrationTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'data/study/sources/book.pdf'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'%PDF-verified-source')
        old = root / 'data/study/text-reflow-library'
        folder = old / 'books/mac-id/3e66ab34f484'
        cache = folder / 'cache'
        cache.mkdir(parents=True)
        mac_repo = Path('/Users/example/Karakeep-tool')
        mac_folder = mac_repo / 'data/study/text-reflow-library/books/mac-id/3e66ab34f484'
        profile = {**resume.PROFILE, 'tesseract': True}
        (cache / 'input.json').write_text(json.dumps({'source': str(mac_repo / 'data/study/sources/book.pdf'),
                                                     'tesseract': True, 'batch_profile': profile}))
        (cache / 'p00001.gemini.json').write_text('{"transcription":"cached"}')
        (folder / 'horizontal.epub').write_bytes(b'original-epub')
        job = {'id': 'linux-id', 'path': str(source), 'source_type': 'single_source', 'sd_epubs': ['医学教科書/book.epub']}
        record = {'job': {**job, 'id': 'mac-id', 'path': str(mac_repo / 'data/study/sources/book.pdf')},
                  'profile': profile, 'status': 'converted_draft', 'dependencies': {},
                  'source_sha256': resume.digest(source), 'outputs': [str((mac_folder / 'horizontal.epub').relative_to(mac_repo))]}
        (folder / 'job.json').write_text(json.dumps(record))
        plan = {'jobs': [job], 'missing': [{'source': 'unavailable.pdf'}]}
        return old, folder, source, plan

    def test_migration_preserves_originals_and_remaps_verified_cache_and_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            old, folder, source, plan = self.fixture(root)
            dest = root / 'data/study/text-reflow-linux'
            original_record = (folder / 'job.json').read_bytes()
            with patch.object(resume, 'REPO', root), patch.object(resume, 'OLD', old), \
                    patch.object(resume, 'DEST', dest), patch.object(resume, 'current_plan', return_value=plan), \
                    patch.object(resume.shutil, 'disk_usage', return_value=SimpleNamespace(free=20 * 1024**3)):
                manifest = resume.prepare()
                self.assertEqual(manifest['retained_completed'], 1)
                self.assertEqual(resume.prepare(), manifest)
            new = dest / 'books/linux-id' / resume.PROFILE_ID
            record = json.loads((new / 'job.json').read_text())
            self.assertEqual(record['job']['path'], str(source))
            self.assertEqual(record['outputs'], [str(new / 'horizontal.epub')])
            self.assertFalse(record['profile']['tesseract'])
            identity = json.loads((new / 'cache/input.json').read_text())
            self.assertEqual(identity['source'], str(source))
            self.assertFalse(identity['tesseract'])
            self.assertFalse(identity['batch_profile']['tesseract'])
            self.assertEqual((folder / 'job.json').read_bytes(), original_record)
            self.assertEqual((new / 'cache/p00001.gemini.json').read_bytes(), (folder / 'cache/p00001.gemini.json').read_bytes())
            (new / 'horizontal.epub').write_bytes(b'updated-copy')
            self.assertEqual((folder / 'horizontal.epub').read_bytes(), b'original-epub')

    def test_changed_source_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            old, _, source, plan = self.fixture(root)
            source.write_bytes(b'%PDF-different-source')
            with patch.object(resume, 'REPO', root), patch.object(resume, 'OLD', old):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    resume.migration_plan(plan)

    def test_primary_profile_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            old, folder, _, plan = self.fixture(root)
            record = json.loads((folder / 'job.json').read_text())
            record['profile']['dpi'] = 200
            (folder / 'job.json').write_text(json.dumps(record))
            with patch.object(resume, 'REPO', root), patch.object(resume, 'OLD', old):
                with self.assertRaisesRegex(ValueError, 'primary OCR settings differ'):
                    resume.migration_plan(plan)


if __name__ == '__main__':
    unittest.main()
