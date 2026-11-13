import importlib.util
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

common = types.ModuleType('common')
common.extract_karakeep_tweet_ids = lambda bs: {m.group(1) for b in bs if (m := re.search(r'/status/(\d+)', (b.get('content') or {}).get('url', '')))}
common.extract_karakeep_urls = lambda bs: {b['content']['url'] for b in bs if (b.get('content') or {}).get('url')}
common.extract_uploaded_filenames_from_export = lambda bs: {b['note'].split()[0][9:] for b in bs if (b.get('note') or '').startswith('filename:')}
spec = importlib.util.spec_from_file_location('twitter_import', Path(__file__).parents[1] / 'files/twitter-import.py')
m = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'common': common, 'register_tweets': types.ModuleType('register_tweets'),
                              'upload_media': types.ModuleType('upload_media')}):
    spec.loader.exec_module(m)

class TwitterImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = m.Ledger(Path(self.temp.name) / 'receipts.db')
    def test_tweet_id_prevents_duplicate_across_url_forms(self):
        item = {'url': 'https://x.com/a/status/123', 'key': '123'}
        self.assertFalse(m.create_link(None, self.ledger, item, {'123'}, set()))
    def test_ambiguous_create_never_retries(self):
        item = {'url': 'https://x.com/a/status/123', 'key': '123'}
        self.ledger.put('link:123', 'creating', {})
        with self.assertRaises(m.Ambiguous): m.create_link(None, self.ledger, item, set(), set())
    def test_media_intent_and_existing_markers(self):
        entry = {'filename':'u_123456789012345_photo_1_20250101.jpg', 'ext':'jpg', 'media_type':'photo'}
        self.ledger.put('media:' + entry['filename'], 'creating', {})
        with self.assertRaises(m.Ambiguous):
            m.create_media(None, self.ledger, entry, set(), {}, set(), Path(self.temp.name))
        self.assertFalse(m.create_media(None, self.ledger, entry, set(), {entry['filename']: ['id']}, set(), Path(self.temp.name)))
        self.assertEqual(self.ledger.get('media:' + entry['filename'])[0], 'done')
    def test_snapshot_indexes_notes_and_media(self):
        data = [{'id':'a','note':'filename:foo.jpg tweet_id:123', 'content':{'type':'asset','fileName':'foo.jpg'}},
                {'id':'b','content':{'type':'link','url':'https://x.com/a/status/123'}, 'assets':[{'fileName':'video.mp4'}]}]
        ids, urls, files, markers = m.snapshot_index(data)
        self.assertEqual(ids, {'123'}); self.assertIn('foo.jpg', files)
        self.assertEqual(markers['foo.jpg'], ['a'])
        self.assertIn('video.mp4', files)
    def test_existing_duplicate_markers_are_skipped(self):
        entry = {'filename': 'same.jpg', 'ext': 'jpg', 'media_type': 'photo'}
        self.assertFalse(m.create_media(None, self.ledger, entry, set(), {'same.jpg': ['a', 'b']}, set(), Path(self.temp.name)))
        self.assertEqual(self.ledger.get('media:same.jpg')[0], 'done')
    def test_retry_reuses_recorded_asset(self):
        entry = {'filename': 'same.jpg', 'ext': 'jpg', 'tweet_id': '123', 'media_type': 'photo'}
        self.ledger.put('media:same.jpg', 'retry', {'asset_id': 'asset', '_retry_state': 'asset', '_attempts': 1})
        client = types.SimpleNamespace(request=lambda *args: {'id': 'bookmark'})
        self.assertTrue(m.create_media(client, self.ledger, entry, set(), {}, set(), Path(self.temp.name)))
        self.assertEqual(self.ledger.get('media:same.jpg')[1]['asset_id'], 'asset')
    def test_video_is_never_uploaded(self):
        for entry in ({'filename':'v.mp4', 'ext':'mp4', 'media_type':'video'},
                      {'filename':'v.jpg', 'ext':'jpg', 'media_type':'video'},
                      {'filename':'v.mp4', 'ext':'mp4', 'media_type':'photo'},
                      {'filename':'v.gif', 'ext':'gif', 'media_type':'animated_gif'}):
            self.assertFalse(m.create_media(None, self.ledger, entry, set(), {}, set(), Path(self.temp.name)))
            self.assertEqual(self.ledger.get('media:' + entry['filename'])[0], None)
        disguised = {'filename':'x.jpg', 'ext':'jpg', 'media_type':'photo', 'url':'https://video.twimg.com/x'}
        with self.assertRaises(ValueError):
            m.create_media(None, self.ledger, disguised, set(), {}, set(), Path(self.temp.name))

if __name__ == '__main__': unittest.main()
