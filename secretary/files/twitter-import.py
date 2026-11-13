#!/usr/bin/env python3
"""Resumable wrapper around TwitterBookmark_to_karakeep, with durable create intents."""
import fcntl
import json
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path('/var/lib/secretary-karakeep/twitter-import')
UPSTREAM = Path('/opt/secretary/twitter-bookmark-tool')
sys.path.insert(0, str(UPSTREAM))
import common
import register_tweets
import upload_media
# The upstream scripts disable certificate verification globally. Restore it.
ssl._create_default_https_context = ssl.create_default_context

class Ambiguous(Exception):
    pass

class Client:
    def __init__(self, config):
        self.base = config['url'].rstrip('/')
        self.key = config['key']
    def request(self, method, path, value=None, content_type='application/json'):
        if isinstance(value, dict): value = json.dumps(value, ensure_ascii=False).encode()
        headers = {'Authorization': 'Bearer ' + self.key, 'Content-Type': content_type}
        req = urllib.request.Request(self.base + path, data=value, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    def snapshot(self):
        cursor, cursors, bookmarks = None, set(), []
        while True:
            query = {'limit': 100}
            if cursor: query['cursor'] = cursor
            page = self.request('GET', '/api/v1/bookmarks?' + urllib.parse.urlencode(query))
            if not isinstance(page.get('bookmarks'), list) or 'nextCursor' not in page:
                raise RuntimeError('Invalid bookmark page')
            bookmarks.extend(page['bookmarks'])
            cursor = page['nextCursor']
            if not cursor: return bookmarks
            if cursor in cursors: raise RuntimeError('Repeated bookmark cursor')
            cursors.add(cursor)
            if len(cursors) % 50 == 0: print('Snapshot pages:', len(cursors), flush=True)
    def upload(self, path, filename):
        boundary = uuid.uuid4().hex
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\nContent-Type: {content_type}\r\n\r\n').encode()
        body = head + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST', '/api/v1/assets', body, 'multipart/form-data; boundary=' + boundary)['assetId']

class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipt (key TEXT PRIMARY KEY, state TEXT NOT NULL, value TEXT NOT NULL)')
        self.db.commit()
    def get(self, key):
        row = self.db.execute('SELECT state,value FROM receipt WHERE key=?', (key,)).fetchone()
        return (row[0], json.loads(row[1])) if row else (None, {})
    def put(self, key, state, value):
        with self.db: self.db.execute('INSERT OR REPLACE INTO receipt VALUES (?,?,?)', (key, state, json.dumps(value)))


def snapshot_index(bookmarks):
    ids = common.extract_karakeep_tweet_ids(bookmarks)
    urls = common.extract_karakeep_urls(bookmarks)
    files = common.extract_uploaded_filenames_from_export(bookmarks)
    markers = {}
    for b in bookmarks:
        note = b.get('note') or ''
        if note.startswith('filename:'):
            filename = note.split()[0][len('filename:'):]
            markers.setdefault(filename, []).append(b['id'])
        content = b.get('content') or {}
        if content.get('type') == 'asset' and content.get('fileName'):
            files.add(content['fileName'])
    return ids, urls, files, markers


def create_link(client, ledger, item, ids, urls):
    match = re.search(r'/status/(\d+)', item['url'])
    ident = match.group(1) if match else None
    if item['url'] in urls or (ident and ident in ids): return False
    key = 'link:' + (ident or item['url'])
    state, receipt = ledger.get(key)
    if state == 'done': return False
    if state == 'creating': raise Ambiguous('Unresolved link creation; reconcile before retry')
    ledger.put(key, 'creating', {})
    # The requested upstream registration routine performs the create request.
    bookmark_id = register_tweets.register_item_via_api(item, client.key, client.base)
    if not bookmark_id: raise Ambiguous('Link create returned no bookmark ID')
    ledger.put(key, 'done', {'id': bookmark_id})
    urls.add(item['url'])
    if ident: ids.add(ident)
    return True


def create_media(client, ledger, entry, files, markers, old_done, tmpdir):
    name = entry['filename']; key = 'media:' + name
    state, receipt = ledger.get(key)
    marker_matches = markers.get(name, [])
    if len(marker_matches) > 1: raise Ambiguous('Duplicate media marker; reconcile before retry')
    if state == 'done' or name in old_done: return False
    if marker_matches:
        receipt['bookmark_id'] = marker_matches[0]
        if entry['ext'] != 'mp4':
            ledger.put(key, 'done', receipt); return False
        state = 'created'
    elif name in files:
        ledger.put(key, 'done', {}); return False
    elif state == 'creating':
        raise Ambiguous('Unresolved media creation; reconcile before retry')
    if state == 'unavailable': return False
    if state not in ('asset', 'created'):
        u = urllib.parse.urlsplit(entry['url'])
        if u.scheme != 'https' or u.hostname not in ('pbs.twimg.com', 'video.twimg.com') or Path(name).name != name:
            raise ValueError('Invalid media source')
        path = tmpdir / name
        try:
            try: upload_media.download_media(entry['url'], str(path))
            except urllib.error.HTTPError as e:
                if e.code in (403, 404, 410):
                    ledger.put(key, 'unavailable', {'http': e.code}); return False
                raise
            receipt['asset_id'] = client.upload(path, name)
            ledger.put(key, 'asset', receipt)
        finally:
            path.unlink(missing_ok=True)
    if state != 'created':
        ledger.put(key, 'creating', receipt)
        note = f'filename:{name} tweet_id:{entry["tweet_id"]}'
        if entry['ext'] == 'mp4':
            value = {'type': 'text', 'text': 'Twitter video: ' + entry['tweet_id'], 'note': note, 'source': 'api'}
        else:
            value = {'type': 'asset', 'assetType': 'image', 'assetId': receipt['asset_id'], 'fileName': name, 'note': note, 'source': 'api'}
        result = client.request('POST', '/api/v1/bookmarks', value)
        receipt['bookmark_id'] = result['id']; ledger.put(key, 'created', receipt)
    if entry['ext'] == 'mp4':
        if not receipt.get('asset_id'): raise Ambiguous('Video asset ID missing; reconcile before retry')
        bid = urllib.parse.quote(receipt['bookmark_id'], safe='')
        existing = client.request('GET', '/api/v1/bookmarks/' + bid)
        if not any(a.get('id') == receipt['asset_id'] for a in existing.get('assets', [])):
            client.request('POST', '/api/v1/bookmarks/' + bid + '/assets', {'id': receipt['asset_id'], 'assetType': 'userUploaded'})
    ledger.put(key, 'done', receipt); files.add(name)
    return True


def main():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (ROOT / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        client = Client(json.loads(Path('/etc/secretary-karakeep.json').read_text()))
        ledger = Ledger(ROOT / 'receipts.sqlite3')
        tweets = json.loads((ROOT / 'input/twitter.json').read_text())
        media = common.parse_media_urls_txt(str(ROOT / 'input/media-urls.txt'))
        old_file = ROOT / 'prior-upload-progress.json'
        old = json.loads(old_file.read_text()) if old_file.exists() else {}
        old_done = {k for k, v in old.items() if v.get('status') == 'done'}
        bookmarks = client.snapshot()
        ids, urls, files, markers = snapshot_index(bookmarks)
        print('Snapshot:', len(bookmarks), 'bookmarks;', len(ids), 'tweet IDs;', len(files), 'media filenames', flush=True)
        items = register_tweets.collect_items_to_register(tweets, ids, urls, False, False)
        print('Input:', len(tweets), 'tweets;', len(media), 'media; candidate links:', len(items), flush=True)
        if '--dry-run' in sys.argv: return
        for i, item in enumerate(items, 1):
            create_link(client, ledger, item, ids, urls)
            if i % 100 == 0: print('Links processed:', i, '/', len(items), flush=True)
            time.sleep(.2)
        with tempfile.TemporaryDirectory(prefix='twitter-', dir=ROOT) as temp:
            for i, entry in enumerate(media, 1):
                create_media(client, ledger, entry, files, markers, old_done, Path(temp))
                if i % 50 == 0: print('Media processed:', i, '/', len(media), flush=True)
                time.sleep(.5)
        counts = dict(ledger.db.execute('SELECT state, count(*) FROM receipt GROUP BY state'))
        print('Import finished; receipts:', counts, flush=True)

if __name__ == '__main__':
    try: main()
    except Ambiguous as e:
        print('REVIEW REQUIRED:', e, file=sys.stderr, flush=True); sys.exit(78)
    except Exception as e:
        print('Temporary import failure:', type(e).__name__, str(e)[:160], file=sys.stderr, flush=True); sys.exit(1)
