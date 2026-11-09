#!/usr/bin/env python3
"""Credential-separated publisher: only create bilingual copies, never mutate originals."""
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode

INSTALL = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pipeline', INSTALL / 'secretary-pipeline.py')
pipeline = importlib.util.module_from_spec(spec); spec.loader.exec_module(pipeline)
spec = importlib.util.spec_from_file_location('gateway', INSTALL / 'karakeep-gateway.py')
gateway = importlib.util.module_from_spec(spec); spec.loader.exec_module(gateway)
LEDGER = Path('/var/lib/secretary-karakeep/translations')


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def api(config, method, path, value=None):
    raw, _ = gateway.upstream(config, method, path, gateway.canonical(value) if value is not None else None)
    return json.loads(raw) if raw else None


def all_bookmarks(config):
    cursor, seen = None, set()
    while True:
        q = dict(limit=100)
        if cursor: q['cursor'] = cursor
        page = api(config, 'GET', '/api/v1/bookmarks?' + urlencode(q))
        yield from page['bookmarks']
        cursor = page.get('nextCursor')
        if not cursor: return
        if cursor in seen: raise RuntimeError('Repeated cursor')
        seen.add(cursor)


def publish(config, document):
    source_id = gateway.identifier(document['source_id'])
    if not re.fullmatch('[a-f0-9]{64}', document['source_hash']): raise ValueError('Invalid source hash')
    marker = 'secretary-translation:' + source_id + ':' + document['source_hash']
    receipt = LEDGER / (source_id + '-' + document['source_hash'] + '.json')
    saved = pipeline.load(receipt, {})
    if saved.get('state') == 'completed': return
    if saved.get('state') == 'ambiguous':
        raise RuntimeError('Prior upload outcome is ambiguous; operator reconciliation required')
    source = api(config, 'GET', '/api/v1/bookmarks/' + source_id + '?includeContent=true')
    text = pipeline.article_text(source)
    if hashlib.sha256(text.encode()).hexdigest() != document['source_hash']:
        raise RuntimeError('Source content changed; translation retained for review')
    pairs = document['pairs']
    originals = pipeline.sentences(text)
    if len(pairs) != len(originals) or any(not isinstance(p, list) or len(p) != 2 or p[0] != s
                                         or not isinstance(p[1], str) or not p[1].strip()
                                         for p, s in zip(pairs, originals)):
        raise ValueError('Incomplete or mismatched sentence pairs')
    title = (source.get('title') or source['content'].get('title') or source['content']['url']).removesuffix('【英日対訳】')
    title = title[:994] + '【英日対訳】'
    created = timestamp(source['createdAt']) + dt.timedelta(seconds=5)
    tags = sorted({x['name'] for x in source.get('tags', [])} | {'英日対訳', 'Plamo翻訳'})
    memberships = api(config, 'GET', '/api/v1/bookmarks/' + source_id + '/lists')
    lists = memberships.get('lists', []) if isinstance(memberships, dict) else memberships
    lists = [x for x in lists if x.get('type', 'manual') == 'manual']
    url = source['content']['url']
    body = '\n\n'.join(['原本: ' + url, '原本ブックマークID: ' + source_id,
                        'モデル: ' + document['model'], '翻訳日時: ' + dt.datetime.fromtimestamp(document['translated_at'], dt.timezone.utc).isoformat(),
                        '自動翻訳・未校閲'] + [line for pair in pairs for line in pair])
    if not saved.get('id'):
        # Full history check is necessary because the new date is intentionally backdated.
        matches = [x for x in all_bookmarks(config) if x.get('note') == marker]
        if len(matches) > 1: raise RuntimeError('Duplicate translation markers require operator review')
        if matches:
            saved.update(id=matches[0]['id'], state='created')
        elif saved.get('state') == 'creating':
            saved['state'] = 'ambiguous'; pipeline.save(receipt, saved)
            raise RuntimeError('Create response was interrupted; no automatic duplicate retry')
        else:
            saved.update(state='creating'); pipeline.save(receipt, saved)
            result = api(config, 'POST', '/api/v1/bookmarks', dict(type='text', text=body,
                         sourceUrl=url, title=title, note=marker, createdAt=created.isoformat(), source='api'))
            saved.update(id=gateway.identifier(result['id']), state='created')
        pipeline.save(receipt, saved)
    bookmark_id = gateway.identifier(saved['id'])
    api(config, 'POST', '/api/v1/bookmarks/' + bookmark_id + '/tags', {'tags': [{'tagName': x} for x in tags]})
    for item in lists:
        api(config, 'PUT', '/api/v1/lists/' + gateway.identifier(item['id']) + '/bookmarks/' + bookmark_id)
    actual = api(config, 'GET', '/api/v1/bookmarks/' + bookmark_id + '?includeContent=true')
    if actual.get('title') != title or timestamp(actual['createdAt']) != created:
        raise RuntimeError('Title/date verification failed; automatic further uploads paused')
    if actual.get('content', {}).get('text') != body or not set(tags).issubset({t['name'] for t in actual['tags']}):
        raise RuntimeError('Body/tag verification failed')
    actual_lists = api(config, 'GET', '/api/v1/bookmarks/' + bookmark_id + '/lists')
    actual_lists = actual_lists.get('lists', []) if isinstance(actual_lists, dict) else actual_lists
    if not {x['id'] for x in lists}.issubset({x['id'] for x in actual_lists}):
        raise RuntimeError('List verification failed')
    saved.update(state='completed', finished=time.time()); pipeline.save(receipt, saved)


def main():
    LEDGER.mkdir(parents=True, exist_ok=True)
    with (LEDGER / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = gateway.read_json(gateway.CONFIG)
        for file in sorted((pipeline.STATE / 'outbox').glob('*.json')):
            if file.is_symlink() or file.stat().st_size > 20 * 1024**2:
                raise RuntimeError('Invalid outbox file')
            publish(config, json.loads(file.read_text()))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never print credentials, source text, or HTTP response bodies.
        pipeline.save(LEDGER / 'status.json', dict(state='waiting_retry', error=str(error)[:300], at=time.time()))
        raise SystemExit(1)
