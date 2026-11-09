import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FILES = Path(__file__).resolve().parents[1] / 'files'


def imported(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), FILES / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class PipelineTests(unittest.TestCase):
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
