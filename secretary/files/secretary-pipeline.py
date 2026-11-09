#!/usr/bin/env python3
"""Container-only resumable medical OCR, Narou and bilingual translation workers."""
import argparse
import contextlib
import fcntl
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

REPO = Path('/srv/secretary/karakeep-tool')
INSTALL = Path('/opt/secretary')
STATE = Path('/var/lib/secretary-pipeline')
PYTHON = '/opt/secretary-tools/bin/python'


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
        os.chmod(name, 0o640)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), INSTALL / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(kind, state, **details):
    save(STATE / (kind + '-status.json'), dict(state=state, updated_at=time.time(), **details))


def normalize(path):
    return unicodedata.normalize('NFC', str(path))


def medical_pending():
    """Match current PDF bytes and actual output existence, not legacy aggregate status."""
    root = REPO / 'data/study/japan-medical-licensing/sources'
    files = sorted(p for p in root.rglob('*.pdf') if any(x in ('メイン', 'マイナー') for x in p.parts))
    if not files:
        raise RuntimeError('No medical examination PDFs found')
    completed = set()
    for library in ('text-reflow-linux', 'medical-auto'):
        for p in (REPO / 'data/study' / library).glob('books/*/*/job.json'):
            d = load(p, {})
            outputs = d.get('outputs', [])
            if d.get('status') == 'converted_draft' and outputs and all(Path(x).is_file() for x in outputs):
                completed.add((normalize(d['job']['path']), d['source_sha256']))
    pending = [p for p in files if (normalize(p), digest(p)) not in completed]
    return files, pending


def medical():
    tools = module('secretary-tools')
    _, converter = tools.tool_entry('study/convert_study_materials.py')
    files, pending = medical_pending()
    record('medical', 'running' if pending else 'completed', total=len(files), remaining=len(pending))
    if not pending:
        return
    # One converter invocation reuses its persistent OCR worker and page caches.
    command = [PYTHON, str(converter), 'run',
               *[argument for path in pending for argument in ('--input', str(path))],
               '--output', str(REPO / 'data/study/medical-auto'), '--device', 'cuda',
               '--engine', 'yomitoku', '--offline', '--dpi', '300',
               '--yomitoku-python', '/opt/secretary-ocr/bin/python', '--java', '/usr/bin/java',
               '--epubcheck-jar', str(REPO / 'data/study/japan-medical-licensing/work/qa-tools/epubcheck-5.4.0/epubcheck.jar'),
               '--min-free-gib', '5', '--json']
    env = tools.child_env(credentials=False)
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    with (STATE / 'medical.log').open('a') as out:
        subprocess.run(command, cwd=REPO, env=env, stdout=out, stderr=out, check=True)
    files, pending = medical_pending()
    if pending:
        raise RuntimeError(f'{len(pending)} medical inputs still incomplete')
    record('medical', 'completed', total=len(files), remaining=0)


def narou():
    tools = module('secretary-tools')
    status = tools.narou_status()
    if status['running_process_ids']:
        raise RuntimeError('Another Narou process is active; retry later')
    if status['not_completed'] == 0 and status['candidate_count']:
        record('narou', 'completed', completed=status['completed_candidates'])
        return
    versions = dict(line.split('=', 1) for line in (INSTALL / 'pipeline-versions.env').read_text().splitlines()
                    if line and not line.startswith('#') and '=' in line)
    downloader = REPO / 'novel_downloader/novel_downloader.py'
    if digest(downloader) != versions['NOVEL_DOWNLOADER_PATCHED_SHA256'].strip('"\''):
        raise RuntimeError('Downloader checksum differs from pinned version')
    _, entry = tools.tool_entry('books/narou_library.py')
    record('narou', 'running', completed=status['completed_candidates'], remaining=status['not_completed'])
    with (STATE / 'narou.log').open('a') as out:
        subprocess.run([PYTHON, '-u', str(entry), 'download', '--execute', '--limit', '2000',
                        '--delay', '3', '--reserve-gib', '5'], cwd=REPO,
                       env=tools.child_env(credentials=False), stdout=out, stderr=out, check=True)
    status = tools.narou_status()
    if status['not_completed']:
        raise RuntimeError(f"{status['not_completed']} Narou candidates remain")
    record('narou', 'completed', completed=status['completed_candidates'])


def sentences(text):
    # Preserve English abbreviation/decimal boundaries; every source character is retained.
    text = re.sub(r'\s+', ' ', text).strip()
    protected = re.sub(r'\b(?:Dr|Mr|Mrs|Ms|Prof|Fig|Figs|Eq|Eqs|Vol|vs|etc|e\.g|i\.e)\.',
                       lambda m: m[0].replace('.', '\u2024'), text, flags=re.I)
    protected = re.sub(r'\b([A-Z])\.(?=\s+[A-Z])', lambda m: m[1] + '\u2024', protected)
    return [p.replace('\u2024', '.') for p in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9“"(])', protected) if p]


class Translator:
    def __init__(self):
        self.process = None

    def close(self):
        if self.process:
            self.process.stdin.close()
            self.process.wait(timeout=60)
            self.process = None

    def __call__(self, text):
        revision = (INSTALL / 'plamo.revision').read_text().strip()
        key = hashlib.sha256((revision + ':sentence-v1:' + text).encode()).hexdigest()
        cache = STATE / 'sentences' / (key + '.json')
        if cache.exists():
            return load(cache)['translation']
        if not self.process:
            self.process = subprocess.Popen(['/opt/secretary-plamo/bin/python', str(INSTALL / 'plamo-translate.py'), '--stream'],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.process.stdin.write(json.dumps(dict(text=text, source_lang='en', target_lang='ja')) + '\n')
        self.process.stdin.flush()
        reply = self.process.stdout.readline()
        if not reply:
            raise RuntimeError('PLaMo worker exited; sentence checkpoint retained')
        result = json.loads(reply)
        if result.get('error') or not result.get('text', '').strip():
            raise RuntimeError('PLaMo did not produce a complete translation')
        translated = result['text'].strip()
        if re.search('[A-Za-z]', text) and not re.search('[\u3040-\u30ff\u3400-\u9fff]', translated):
            raise RuntimeError('Translation contains no Japanese text; manual review needed')
        save(cache, dict(source=text, translation=translated, revision=revision))
        return translated


def article_text(item):
    # Use the saved readable article, never refetch arbitrary external URLs.
    from html.parser import HTMLParser
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(); self.skip = 0; self.parts = []
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style', 'nav', 'noscript'): self.skip += 1
            if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3'): self.parts.append('\n')
        def handle_endtag(self, tag):
            if tag in ('script', 'style', 'nav', 'noscript'): self.skip = max(0, self.skip - 1)
        def handle_data(self, data):
            if not self.skip: self.parts.append(data)
    content = item.get('content', {})
    if content.get('type') != 'link': return ''
    raw = content.get('htmlContent') or ''
    parser = Reader(); parser.feed(raw)
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def articles(translate):
    tools = module('secretary-tools')
    manifest = STATE / 'articles.json'
    if not manifest.exists():
        items, cursor, seen = [], None, set()
        while True:
            from urllib.parse import urlencode
            query = dict(limit=100, includeContent='true')
            if cursor: query['cursor'] = cursor
            page = tools.gateway_request('GET', '/api/v1/bookmarks?' + urlencode(query))
            for item in page['bookmarks']:
                text = article_text(item)
                letters = len(re.findall('[A-Za-z]', text)); jp = len(re.findall('[\u3040-\u30ff\u3400-\u9fff]', text))
                if '【英日対訳】' not in (item.get('title') or '') and letters > 200 and letters > jp * 5:
                    items.append(dict(id=item['id'], text=text, hash=hashlib.sha256(text.encode()).hexdigest()))
            cursor = page.get('nextCursor')
            if not cursor: break
            if cursor in seen: raise RuntimeError('Karakeep pagination cursor repeated')
            seen.add(cursor)
        save(manifest, items)
    items = load(manifest)
    for index, item in enumerate(items):
        outbox = STATE / 'outbox' / (item['id'] + '-' + item['hash'] + '.json')
        if outbox.exists(): continue
        record('translation', 'running', source='karakeep', index=index + 1, total=len(items), source_id=item['id'])
        pairs = [[s, translate(s)] for s in sentences(item['text'])]
        save(outbox, dict(source_id=item['id'], source_hash=item['hash'], pairs=pairs,
                         model=(INSTALL / 'plamo.revision').read_text().strip(), translated_at=time.time()))


def ebooks(translate):
    root = REPO / 'data/study/device-library-all'
    sources = [p for p in root.rglob('*.epub') if 'カンデル' in normalize(p.name)]
    if not sources:
        raise RuntimeError('Final Kandel English EPUBs not found')
    for source in sorted(sources):
        key = digest(source)
        target = STATE / 'epubs' / (normalize(source.stem) + '【英日対訳】.epub')
        receipt = target.with_suffix('.json')
        if target.exists() and load(receipt, {}).get('source_hash') == key: continue
        record('translation', 'running', source='kandel', title=source.stem)
        translated_count = 0
        temporary = target.with_name(target.stem + '.partial.epub')
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(temporary, 'w') as dst:
            dst.writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            for entry in src.infolist():
                if entry.filename == 'mimetype': continue
                data = src.read(entry)
                if entry.filename.lower().endswith(('.xhtml', '.html')):
                    tree = ET.fromstring(data)
                    for parent in list(tree.iter()):
                        for child in list(parent):
                            if child.tag.split('}')[-1] != 'p': continue
                            if any(n.tag.split('}')[-1] in ('img', 'svg', 'math', 'table', 'br') for n in child.iter()): continue
                            text = ''.join(child.itertext()).strip()
                            if len(re.findall('[A-Za-z]+', text)) < 5: continue
                            parts = sentences(text)
                            if not parts: continue
                            position = list(parent).index(child)
                            tail = child.tail
                            parent.remove(child)
                            for sentence_index, s in enumerate(parts):
                                for lang, body in [('en', s), ('ja', translate(s))]:
                                    attributes = {}
                                    if lang == 'en' and sentence_index == 0: attributes.update(child.attrib)
                                    attributes.update(lang=lang, **{'class': 'bilingual-' + lang})
                                    node = ET.Element(child.tag, attributes)
                                    node.text = body
                                    if lang == 'en' and sentence_index == 0:
                                        for anchor in child.iter():
                                            if anchor is not child and anchor.get('id'):
                                                ET.SubElement(node, child.tag.rsplit('}', 1)[0] + '}span', {'id': anchor.get('id')})
                                    parent.insert(position, node); position += 1
                                translated_count += 1
                            node.tail = tail
                    data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
                elif entry.filename.endswith('.opf'):
                    tree = ET.fromstring(data)
                    for node in tree.iter():
                        if node.tag == '{http://purl.org/dc/elements/1.1/}title':
                            node.text = (node.text or source.stem).replace('【英日対訳】', '') + '【英日対訳】'
                        if node.tag.endswith('spine'):
                            node.set('page-progression-direction', 'ltr')
                    data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
                dst.writestr(entry, data)
        if not translated_count:
            raise RuntimeError('No translatable prose found in EPUB')
        jar = REPO / 'data/study/japan-medical-licensing/work/qa-tools/epubcheck-5.4.0/epubcheck.jar'
        # EPUBCheck determines whether a generated file may be published.
        with (STATE / 'epubcheck.log').open('a') as log:
            subprocess.run(['/usr/bin/java', '-jar', str(jar), str(temporary)], stdout=log, stderr=log, check=True)
        os.replace(temporary, target)
        save(receipt, dict(source=str(source), source_hash=key, sentences=translated_count, status='draft_unreviewed'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['gpu', 'narou', 'status'])
    args = parser.parse_args()
    if args.action == 'status':
        for p in sorted(STATE.glob('*-status.json')): print(p.name, p.read_text())
        return
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / (args.action + '.lock')).open('a') as own_lock:
        fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if shutil.disk_usage(REPO / 'data').free < 6 * 1024**3:
                raise RuntimeError('Less than 6 GiB free; waiting for space')
            if args.action == 'narou':
                narou(); return
            tools = module('secretary-tools')
            record('gpu', 'running')
            with (tools.STATE / 'translation.lock').open('a') as gpu_lock:
                fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if tools.active_ocr_processes(): raise RuntimeError('Another OCR worker is active')
                medical()
                translate = Translator()
                try:
                    articles(translate)
                    ebooks(translate)
                    record('translation', 'completed')
                    record('gpu', 'completed')
                finally:
                    translate.close()
        except Exception as error:
            record(args.action, 'waiting_retry', error=tools.redact(str(error)) if 'tools' in locals() else type(error).__name__ + ': ' + str(error))
            raise


if __name__ == '__main__':
    main()
