import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

FILES = Path(__file__).resolve().parents[1] / 'files'


def imported(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), FILES / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class PipelineTests(unittest.TestCase):
    def test_book_translation_records_and_reuses_failed_sentence(self):
        p = imported('secretary-pipeline')
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); repo = base / 'repo'; state = base / 'state'; install = base / 'install'
            install.mkdir(); (install / 'plamo.revision').write_text('v1')
            root = repo / 'data/study/device-library-all'; root.mkdir(parents=True)
            source = root / 'カンデル（英語）.epub'
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('mimetype', 'application/epub+zip')
                z.writestr('book.xhtml', '<html><body><p>This is a reference with five words.</p></body></html>')
            class FakeTranslator:
                use_modal = False
                def __init__(self): self.calls = 0
                def __call__(self, text):
                    self.calls += 1
                    raise p.TranslationNeedsReview('no Japanese')
            translate = FakeTranslator()
            with patch.object(p, 'REPO', repo), patch.object(p, 'STATE', state), patch.object(p, 'INSTALL', install), patch.object(p.subprocess, 'run'):
                p.ebooks(translate)
                receipt = next((state / 'epubs').glob('*.json'))
                self.assertEqual(p.load(receipt)['review_count'], 1)
                with zipfile.ZipFile(next((state / 'epubs').glob('*.epub'))) as z:
                    self.assertIn('翻訳要確認', z.read('book.xhtml').decode())
                p.ebooks(translate)
                self.assertEqual(translate.calls, 1)

    def test_completed_receipt_needs_same_bytes_and_real_outputs(self):
        p = imported('secretary-pipeline')
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            source = repo / 'data/study/japan-medical-licensing/sources/メイン/test.pdf'
            source.parent.mkdir(parents=True); source.write_bytes(b'pdf1')
            output = repo / 'good.epub'; output.write_bytes(b'epub')
            receipt = repo / 'data/study/text-reflow-linux/books/id/profile/job.json'
            p.save(receipt, dict(job={'path': str(source)}, source_sha256=p.digest(source), status='converted_draft', outputs=[str(output)]))
            with patch.object(p, 'REPO', repo):
                self.assertEqual(p.medical_pending()[1], [])
                source.write_bytes(b'pdf2')
                self.assertEqual(p.medical_pending()[1], [source])
                source.write_bytes(b'pdf1'); output.unlink()
                self.assertEqual(p.medical_pending()[1], [source])

    def test_abbreviations_and_decimal_stay_in_source_sentence(self):
        p = imported('secretary-pipeline')
        text = 'Dr. Smith uses Fig. 2 at 3.14 Hz. Next observation.'
        self.assertEqual(p.sentences(text), ['Dr. Smith uses Fig. 2 at 3.14 Hz.', 'Next observation.'])

    def test_untranslatable_article_is_queued_for_review_without_blocking_other_articles(self):
        p = imported('secretary-pipeline')
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state'; install = Path(folder) / 'install'
            install.mkdir(); (install / 'plamo.revision').write_text('model-v1')
            p.save(state / 'articles.json', [dict(id='bad', hash='h1', text='Untranslatable text.'),
                                              dict(id='good', hash='h2', text='English sentence.')])
            calls = []
            def translate(text):
                calls.append(text)
                if text.startswith('Untranslatable'): raise p.TranslationNeedsReview('not Japanese')
                return '日本語の文です。'
            with patch.object(p, 'STATE', state), patch.object(p, 'INSTALL', install), patch.object(p, 'module', return_value=None):
                self.assertEqual(p.articles(translate), 1)
                self.assertEqual(p.articles(translate, worker='modal'), 0)
                self.assertFalse((state / 'outbox/bad-h1.json').exists())
                self.assertEqual(p.load(state / 'review/articles/bad-h1.json')['sentence_index'], 1)
                self.assertEqual(p.load(state / 'outbox/good-h2.json')['pairs'], [['English sentence.', '日本語の文です。']])
                calls.clear(); self.assertEqual(p.articles(translate), 1)
                self.assertEqual(p.articles(translate, worker='modal'), 0); self.assertEqual(calls, [])

    def test_operational_translation_failure_still_propagates(self):
        p = imported('secretary-pipeline')
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state'; install = Path(folder) / 'install'
            install.mkdir(); (install / 'plamo.revision').write_text('model-v1')
            p.save(state / 'articles.json', [dict(id='a', hash='h', text='English sentence.')])
            def failed(_): raise RuntimeError('GPU unavailable')
            with patch.object(p, 'STATE', state), patch.object(p, 'INSTALL', install), patch.object(p, 'module', return_value=None):
                with self.assertRaisesRegex(RuntimeError, 'GPU unavailable'): p.articles(failed)
                self.assertFalse((state / 'review/articles/a-h.json').exists())

    def test_publish_inherits_time_tags_lists_and_does_not_mutate_source(self):
        p = imported('secretary-pipeline-upload')
        text = 'This is the original article.'
        source = {'id': 'original', 'title': 'Title', 'createdAt': '2020-01-01T00:00:00Z',
                  'tags': [{'name': 'Medicine'}], 'content': {'type': 'link', 'url': 'https://example.org', 'htmlContent': text}}
        calls = []; created = {}
        def api(config, method, path, data=None):
            calls.append((method, path, data))
            if path.endswith('/original?includeContent=true'): return source
            if path.endswith('/lists'): return {'lists': [{'id': 'list1', 'type': 'manual'}]}
            if method == 'POST' and path == '/api/v1/bookmarks':
                created.update(data); return {'id': 'copy'}
            if path.endswith('/copy?includeContent=true'):
                return dict(title=created['title'], createdAt=created['createdAt'], content={'text': created['text']}, tags=[{'name': x} for x in ['Medicine', '英日対訳', 'Plamo翻訳']])
        document = dict(source_id='original', source_hash=p.hashlib.sha256(text.encode()).hexdigest(), pairs=[[text, 'これは元の記事です。']], model='revision', translated_at=1)
        with tempfile.TemporaryDirectory() as folder, patch.object(p, 'LEDGER', Path(folder)), patch.object(p, 'api', api), patch.object(p, 'all_bookmarks', return_value=[]):
            p.publish({}, document)
            p.publish({}, document)
        self.assertEqual(created['createdAt'], '2020-01-01T00:00:05+00:00')
        self.assertEqual(created['title'], 'Title【英日対訳】')
        self.assertEqual(sum(m == 'POST' and path == '/api/v1/bookmarks' for m, path, d in calls), 1)
        self.assertFalse(any(m in ('PATCH', 'DELETE') for m, _, _ in calls))
        self.assertTrue(any(m == 'PUT' and path == '/api/v1/lists/list1/bookmarks/copy' for m, path, _ in calls))

    def test_ambiguous_create_is_never_blindly_retried(self):
        p = imported('secretary-pipeline-upload')
        text = 'This is an article.'
        h = p.hashlib.sha256(text.encode()).hexdigest()
        doc = dict(source_id='original', source_hash=h, pairs=[[text, '記事です。']], model='r', translated_at=1)
        source = dict(id='original', title='A', createdAt='2020-01-01T00:00:00Z', tags=[], content=dict(type='link', url='https://example.org', htmlContent=text))
        def api(config, method, path, data=None):
            self.assertEqual(method, 'GET')
            return {'lists': []} if path.endswith('/lists') else source
        with tempfile.TemporaryDirectory() as folder, patch.object(p, 'LEDGER', Path(folder)), patch.object(p, 'api', api), patch.object(p, 'all_bookmarks', return_value=[]):
            p.pipeline.save(Path(folder) / ('original-' + h + '.json'), {'state': 'creating'})
            with self.assertRaisesRegex(RuntimeError, 'interrupted'): p.publish({}, doc)


if __name__ == '__main__':
    unittest.main()
