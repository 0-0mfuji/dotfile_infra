#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixed Karakeep tools + local PLaMo jobs over stdio MCP; no arbitrary shell strings."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.request
import urllib.error
import zipfile
import xml.etree.ElementTree as ET

INSTALL = Path('/opt/secretary')
REPO = Path('/srv/secretary/karakeep-tool')
DOCS = Path('/srv/secretary/documents')
STATE = Path('/home/secretary/.config/secretary/tool-jobs')
CONFIG = Path('/home/secretary/.config/secretary/connections.json')
PYTHON = '/opt/secretary-tools/bin/python'
PLAMO_PYTHON = '/opt/secretary-plamo/bin/python'


def catalog():
    return json.loads((INSTALL / 'catalog.json').read_text())


def within(root, name, existing=False):
    root = root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('path must be inside ' + str(root))
    if existing and not path.is_file():
        raise ValueError('input file not found')
    return path


def read_credentials():
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    item = cfg.get('karakeep', {})
    if not item.get('url') or not item.get('key') or not item.get('managed_proxy') or item['url'] != 'http://127.0.0.1:8766':
        raise ValueError('Karakeep scoped gateway not configured: run provision and dev secretary setup karakeep')
    return item


def gateway_request(method, path, data=None):
    cfg = read_credentials()
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(cfg['url'] + path, data=body, method=method,
                                    headers={'Authorization': 'Bearer ' + cfg['key'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read(16000)).get('error', 'request rejected')
        except Exception:
            message = 'request rejected'
        raise ValueError('Karakeep gateway: ' + redact(str(message))[:1000]) from None
    except Exception as error:
        raise ValueError('Karakeep gateway request failed: ' + type(error).__name__) from None


def child_env():
    env = {'HOME': '/home/secretary', 'PATH': '/opt/secretary-tools/bin:/usr/local/bin:/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'TZ': 'Asia/Tokyo', 'PYTHONUNBUFFERED': '1',
           'XDG_CACHE_HOME': '/srv/secretary/karakeep-tool/data/cache',
           'NODE_PATH': '/opt/secretary-node/node_modules', 'CHROME_PATH': '/usr/bin/chromium'}
    if CONFIG.exists():
        item = json.loads(CONFIG.read_text()).get('karakeep', {})
        if item and not item.get('managed_proxy'):
            raise ValueError('Raw Karakeep keys cannot be passed to tools; run provision first')
        env.update(KARAKEEP_SERVER_ADDR=item.get('url', ''), KARAKEEP_API_KEY=item.get('key', ''))
    secrets = CONFIG.parent / 'tool-secrets.json'
    if secrets.exists():
        values = json.loads(secrets.read_text())
        for key in ('OPENAI_API_KEY', 'GEMINI_API_KEY'):
            if isinstance(values.get(key), str):
                env[key] = values[key]
    return env


def redact(text):
    if CONFIG.exists():
        item = json.loads(CONFIG.read_text()).get('karakeep', {})
        if item.get('key'):
            text = text.replace(item['key'], '[REDACTED]')
    secrets = CONFIG.parent / 'tool-secrets.json'
    if secrets.exists():
        for key, value in json.loads(secrets.read_text()).items():
            if isinstance(value, str) and value:
                text = text.replace(value, '[REDACTED]')
    return re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._-]+', r'\1[REDACTED]', text)


def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_args(args):
    if not isinstance(args, list) or len(args) > 100 or any(
        not isinstance(a, str) or '\x00' in a or len(a) > 16000 for a in args
    ):
        raise ValueError('args must be an array of at most 100 strings')
    return args


def tool_entry(path):
    entry = next((x for x in catalog()['tools'] if x['path'] == path), None)
    if not entry or entry['helper']:
        raise ValueError('not a catalog entry point')
    target = within(REPO, path, existing=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('tool source differs from the reviewed fixed revision')
    return entry, target


def check_legacy_access(path, args):
    """Fail explicitly rather than letting a CLI swallow a rejected raw mutation."""
    validate_args(args)
    if args == ['--help']:
        return
    if path in ('tools/karakeep/sync_nas_pdfs_to_karakeep.py', 'tools/karakeep/recrawl/recrawl.sh') and '--dry-run' not in args:
        raise ValueError('This legacy write batch is restricted to --dry-run; use scoped plans for supported changes')
    if path == 'tools/karakeep/recrawl/manage_list.sh' and (not args or args[0] not in ('status', 'show-list')):
        raise ValueError('Legacy list mutations are disabled; an operator-reviewed plan implementation is required')


def start_job(kind, payload):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    job = uuid.uuid4().hex
    folder = STATE / job
    folder.mkdir(mode=0o700)
    atomic_json(folder / 'request.json', {'kind': kind, **payload})
    atomic_json(folder / 'status.json', {'state': 'queued', 'created': time.time()})
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', job],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    return {'job_id': job, 'pid': process.pid, 'status_tool': 'secretary_tools__job_status'}


def job_folder(job):
    if not isinstance(job, str) or not re.fullmatch('[a-f0-9]{32}', job):
        raise ValueError('invalid job id')
    return within(STATE, job)


def worker(job):
    folder = job_folder(job)
    request = json.loads((folder / 'request.json').read_text())
    atomic_json(folder / 'status.json', {'state': 'running', 'pid': os.getpid(), 'started': time.time()})
    lock = None
    try:
        env = child_env()
        if request['kind'] == 'translate':
            lock = open(STATE / 'translation.lock', 'a')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('another translation is running; retry after it finishes')
            command = [PLAMO_PYTHON, str(INSTALL / 'plamo-translate.py')]
            stdin = json.dumps(request).encode()
            timeout = 1800
            env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                       HF_HOME='/var/lib/secretary-models/cache', NUMBA_CACHE_DIR='/var/lib/secretary-models/numba')
        elif request['kind'] == 'dictionary':
            _, target = tool_entry(request['path'])
            command = [PYTHON, str(target), request['input'], request['output']]
            if request.get('swap'):
                command.append('--swap')
            stdin = None
            timeout = 1800
        else:
            entry, target = tool_entry(request['path'])
            check_legacy_access(request['path'], request.get('args', []))
            if target.name in ('run_extra.sh', 'run_mirror2.sh') or (target.name == 'finalize.py' and 'place' in request.get('args', [])):
                raise ValueError('Mac-specific paths require a reviewed portability change first; see inspect')
            if target.suffix == '.swift':
                raise ValueError('This tool requires macOS Vision; run it on the Mac')
            interpreter = {'.py': PYTHON, '.sh': '/bin/bash', '.cjs': '/usr/bin/node', '.java': '/usr/bin/java'}[target.suffix]
            command = ([PYTHON, '-m', 'streamlit', 'run', str(target), '--server.address=127.0.0.1'] if target.name == 'app.py'
                       else [interpreter, str(target)])
            command += validate_args(request.get('args', []))
            stdin = None
            timeout = 3600
        # Logs stay private, unbounded stdout never travels through MCP. Return only a tail.
        with (folder / 'output.log').open('wb') as log:
            proc = subprocess.Popen(command, cwd=REPO, env=env, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                    stdout=log, stderr=log, start_new_session=True)
            try:
                proc.communicate(stdin, timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise TimeoutError('job timed out and its process group was terminated')
        atomic_json(folder / 'status.json', {'state': 'completed' if proc.returncode == 0 else 'failed',
                    'exit_code': proc.returncode, 'finished': time.time(), 'output': request.get('output')})
    except Exception as exc:
        atomic_json(folder / 'status.json', {'state': 'failed', 'error': redact(str(exc)), 'finished': time.time()})
    finally:
        if lock:
            lock.close()


def python_script(argv):
    args = [os.fsdecode(x) for x in argv if x]
    if not args or not Path(args[0]).name.lower().startswith('python'):
        return None, []
    args = args[1:]
    while args and args[0] in ('-u', '-B', '-s', '-S', '-E', '-I'):
        args = args[1:]
    if not args or args[0].startswith('-'):
        return None, []
    return Path(args[0]).name, args[1:]


def study_status(scope='medical'):
    if scope not in ('medical', 'nonmedical', 'all'):
        raise ValueError('scope must be medical, nonmedical or all')
    root = within(REPO, 'data/study/text-reflow-library')
    def read(path, default):
        if not path.exists():
            return default
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('invalid study status file')
        return json.loads(path.read_text())
    plan = read(root / 'plan.json', {'jobs': []})
    live = read(root / 'progress.json', {})
    saved = read(root / 'run-status.json', {})
    profile = live.get('profile_id', '')
    if profile and not re.fullmatch('[a-f0-9]{12,64}', profile):
        raise ValueError('invalid recorded OCR profile')
    totals = {'medical': {}, 'nonmedical': {}}; selected = []; absent = []
    output_count = 0
    for job in plan['jobs']:
        jid = job.get('id', '')
        if not re.fullmatch('[a-f0-9]{16,64}', jid):
            raise ValueError('invalid study job id')
        kind = 'medical' if any(p.startswith(('医学教科書/', '医師国家試験/')) for p in job.get('sd_epubs', [])) else 'nonmedical'
        folder = root / 'books' / jid / profile
        record = read(folder / 'job.json', {}) if profile else {}
        state = record.get('status', 'pending' if profile else 'unknown_profile')
        totals[kind][state] = totals[kind].get(state, 0) + 1
        if scope != 'all' and kind != scope:
            continue
        selected.append(jid)
        if state == 'converted_draft':
            missing = 0
            for original in record.get('outputs', []):
                marker = '/books/' + jid + '/' + profile + '/'
                relative = original.split(marker, 1)[-1] if marker in original else original
                target = (folder / relative).resolve()
                if target.is_relative_to(folder.resolve()) and target.suffix.lower() == '.epub' and target.is_file():
                    output_count += 1
                else:
                    missing += 1
            if missing:
                absent.append({'job_id': jid, 'title': job.get('title'), 'missing_outputs': missing})
    counts = {}
    for kind, values in totals.items():
        if scope in ('all', kind):
            for key, value in values.items():counts[key] = counts.get(key, 0) + value
    converters = []; workers = []
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if path.stat().st_uid != os.getuid():continue
            script, args = python_script(path.read_bytes().split(b'\0'))
            if script == 'yomitoku_worker.py':workers.append(int(path.parent.name))
            if script == 'convert_study_materials.py' and args and args[0] == 'run':
                converters.append(int(path.parent.name))
        except (OSError, ValueError):continue
    free = shutil.disk_usage(REPO).free
    return {'data_present': (root / 'plan.json').is_file(), 'scope': scope, 'planned_jobs': len(selected), 'counts': counts, 'all_plan_jobs': len(plan['jobs']),
            'all_scope_counts': totals, 'profile_id': profile or None,
            'saved_progress': live, 'progress_in_scope': live.get('job_id') in selected,
            'saved_run_status': {k: saved.get(k) for k in ('status', 'updated_at', 'completed_jobs', 'publication_status')},
            'present_completed_epub_files': output_count, 'completed_records_with_missing_files': absent[:20],
            'free_gib_now': round(free / 1024**3, 2),
            'conversion_process_ids': converters, 'ocr_worker_process_ids': workers,
            'related_conversion_process_ids': converters + workers,
            'gpu_program_support': {'devices': ['cpu', 'mps', 'cuda', 'auto'], 'default': 'cpu',
                'cuda_arguments': ['--device', 'cuda', '--yomitoku-python', '/opt/secretary-ocr/bin/python']},
            'notes': 'Counts are planned conversion jobs, not distinct books or original catalog groups. '
                     'Saved progress is historical and does not prove a run is active. Converted drafts are unreviewed. '
                     'Mac paths and path-derived job IDs need reconciliation before resuming on Linux. '
                     'An OCR worker alone may be idle and does not prove conversion is running. '
                     'GPU availability must be checked with gpu_diagnostics, not the isolated shell. No conversion was started.'}


def gpu_diagnostics():
    code = '''import json,importlib.metadata
d={}
try:
 import torch
 d.update(torch_version=torch.__version__,compiled_cuda=torch.version.cuda,cuda_available=torch.cuda.is_available(),device_count=torch.cuda.device_count())
 d['yomitoku_version']=importlib.metadata.version('yomitoku')
 if d['cuda_available']:
  d['gpu_name']=torch.cuda.get_device_name(0)
  d['cuda_calculation_ok']=(torch.ones(1,device='cuda')+1).item()==2
except Exception as e:d['error']=type(e).__name__+': '+str(e)[:500]
print(json.dumps(d))'''
    try:
        result = subprocess.run(['/opt/secretary-ocr/bin/python', '-c', code],
                                capture_output=True, text=True, timeout=45)
        data = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        return {'ocr_runtime': data, 'exit_code': result.returncode,
                'notes': 'Measured in the MCP/OCR environment, not the shell sandbox. Only a tiny CUDA calculation was run; no OCR, model download or conversion restart. Process exit releases its GPU memory.'}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {'ocr_runtime': {}, 'error': type(error).__name__, 'notes': 'Probe failed; do not infer that the host has no GPU.'}


def data_files(query='', directory='data', source='repository', limit=20):
    """Bounded metadata lookup, never a shell or content search."""
    roots = {'repository': REPO, 'documents': DOCS}
    if source not in roots or not isinstance(query, str) or len(query) > 200:
        raise ValueError('invalid source or query')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    root = roots[source].resolve()
    folder = within(root, directory) if directory else root
    # Hidden credential/cache directories are not a discovery surface.
    if any(p.startswith('.') for p in folder.relative_to(root).parts):
        raise ValueError('hidden directories are excluded')
    found, scanned, truncated = [], 0, False
    if folder.is_dir():
        for base, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and
                             d not in ('node_modules', 'venv', '__pycache__', 'cache') and not d.endswith('-venv'))
            for name in sorted(files):
                scanned += 1
                if scanned > 20000:
                    truncated = True
                    break
                path = Path(base) / name
                relative = path.relative_to(root).as_posix()
                if (name.startswith('.') or path.is_symlink() or not path.resolve().is_relative_to(root)
                        or query.casefold() not in relative.casefold()):
                    continue
                try:
                    info = path.stat()
                    if not path.is_file():
                        continue
                except OSError:
                    continue
                if len(found) == limit:
                    truncated = True
                    break
                found.append({'path': relative, 'bytes': info.st_size,
                              'modified_unix': info.st_mtime, 'source': source})
            if truncated:
                break
    return {'items': found, 'truncated': truncated, 'scanned_entries': min(scanned, 20000),
            'notes': 'File metadata only; no contents, subprocesses, network or writes. '
                     'Results are not a total count. Narrow directory/query if truncated.'}


def list_epubs(query='', directory='', source='repository', limit=20):
    roots = {'repository': REPO, 'documents': DOCS}
    if source not in roots or not isinstance(query, str) or len(query) > 200:
        raise ValueError('invalid source or query')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    root = roots[source].resolve()
    folder = within(root, directory) if directory else root
    if not folder.is_dir():
        return {'items': [], 'total_matches': 0, 'truncated': False}
    titles = {}
    study_titles = {}
    manifest = REPO / 'data/novels/candidates.json'
    if source == 'repository' and manifest.is_file() and not manifest.is_symlink() and manifest.resolve().is_relative_to(root) and manifest.stat().st_size <= 16 * 1024 * 1024:
        try:
            titles = {w['ncode'].lower(): str(w.get('title', ''))[:200]
                      for w in json.loads(manifest.read_text()).get('works', [])}
        except (OSError, ValueError, KeyError, TypeError):
            titles = {}
    study_plan = REPO / 'data/study/text-reflow-library/plan.json'
    if source == 'repository' and study_plan.is_file() and not study_plan.is_symlink() and study_plan.resolve().is_relative_to(root) and study_plan.stat().st_size <= 16 * 1024 * 1024:
        try:
            study_titles = {j['id']: str(j.get('title', ''))[:200] for j in json.loads(study_plan.read_text()).get('jobs', [])}
        except (OSError, ValueError, KeyError, TypeError):
            study_titles = {}
    found = []
    for base, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'venv', '__pycache__') and not d.endswith('-venv')]
        for name in files:
            if name.startswith('.') or not name.lower().endswith('.epub'):
                continue
            path = Path(base) / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            try:
                info = path.stat()
            except FileNotFoundError:
                continue
            relative = path.relative_to(root).as_posix()
            title = titles.get(path.stem.lower(), '') if relative.startswith('data/novels/') else ''
            if relative.startswith('data/study/text-reflow-library/books/'):
                title = study_titles.get(Path(relative).parts[4], '')
            if query.casefold() not in (relative + ' ' + title).casefold():
                continue
            found.append({'path': relative, 'filename': name, 'title': title, 'bytes': info.st_size,
                          'modified_unix': info.st_mtime, 'source': source})
    found.sort(key=lambda x: (-x['modified_unix'], x['path']))
    return {'items': found[:limit], 'total_matches': len(found), 'truncated': len(found) > limit,
            'notes': 'Metadata only. Use export_epub to validate and prepare a selected file; no book contents were read.'}


def export_epub(path, source='repository'):
    """Prepare one validated local EPUB for the existing authenticated workspace UI."""
    roots = {'repository': REPO, 'documents': DOCS}
    if source not in roots:
        raise ValueError('source must be repository or documents')
    original = within(roots[source], path, existing=True)
    if original.suffix.lower() != '.epub':
        raise ValueError('only EPUB files can be prepared for download')
    downloads = within(DOCS, 'downloads')
    downloads.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='epub-', dir=downloads))
    name = original.name if not original.name.startswith('.') else 'book-' + original.name.lstrip('.')
    target = folder / name
    temporary = folder / '.epub-partial'
    try:
        with original.open('rb') as incoming:
            before = os.fstat(incoming.fileno())
            if before.st_size > 1024**3:
                raise ValueError('EPUB exceeds the 1 GiB download preparation limit')
            if shutil.disk_usage(downloads).free < before.st_size + 1024**3:
                raise ValueError('insufficient space; keep at least 1 GiB free')
            with zipfile.ZipFile(incoming) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(i.file_size for i in entries) > 4 * 1024**3:
                    raise ValueError('EPUB expanded size or entry count exceeds the validation limit')
                with archive.open('mimetype') as stream:
                    if stream.read(64) != b'application/epub+zip':
                        raise ValueError('not a valid EPUB container')
                if archive.testzip() is not None:
                    raise ValueError('EPUB checksum validation failed')
            incoming.seek(0)
            digest = hashlib.sha256()
            copied = 0
            with temporary.open('xb') as output:
                os.chmod(temporary, 0o600)
                for block in iter(lambda: incoming.read(4 * 1024 * 1024), b''):
                    copied += len(block)
                    if copied > before.st_size:
                        raise ValueError('EPUB is still growing; wait until creation finishes')
                    output.write(block); digest.update(block)
            after = os.fstat(incoming.fileno())
            current = original.stat()
            if copied != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or (
                current.st_ino, current.st_size, current.st_mtime_ns) != (before.st_ino, before.st_size, before.st_mtime_ns):
                raise ValueError('EPUB changed while being prepared; wait until creation finishes')
        os.link(temporary, target)
        temporary.unlink()
        relative = target.relative_to(DOCS.resolve()).as_posix()
        return {'workspace_path': relative, 'filename': target.name, 'bytes': before.st_size,
                'sha256': digest.hexdigest(),
                'delivery': 'Show this workspace file as the EPUB artifact. In NanoMuse, open its artifact card and use Download. Do not invent URLs or read the book into chat.'}
    except Exception:
        shutil.rmtree(folder)
        raise


def narou_status():
    """Read the fixed local library; never run a downloader or access the network."""
    root = within(REPO, 'data/novels')
    if not root.is_dir():
        return {'data_present': False, 'scope': 'secretary container only'}
    def local(path):
        return not path.is_symlink() and path.resolve().is_relative_to(root)
    manifest = root / 'candidates.json'
    if not local(manifest) or manifest.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('candidate manifest unavailable or too large')
    data = json.loads(manifest.read_text())
    works = {w['ncode'].lower(): w for w in data['works']
             if re.fullmatch(r'n[0-9]{4}[a-z]+', w.get('ncode', '').lower())}
    library = root / 'library'
    if not local(library):
        raise ValueError('library path escapes novels data')
    complete, invalid = set(), []
    epubs = list(root.glob('*.epub')) + list(library.glob('*/*.epub'))
    valid_count = 0
    for path in epubs:
        if not local(path):
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                with archive.open('mimetype') as stream:
                    if stream.read(64) != b'application/epub+zip':
                        raise ValueError('not EPUB')
                code = path.stem.lower()
                if code not in works:
                    for name in archive.namelist():
                        if name.endswith('.opf') and archive.getinfo(name).file_size <= 2 * 1024 * 1024:
                            with archive.open(name) as stream:
                                metadata = ET.fromstring(stream.read(2 * 1024 * 1024))
                            for source in metadata.iter('{http://purl.org/dc/elements/1.1/}source'):
                                match = re.fullmatch(r'https?://ncode\.syosetu\.com/(n[0-9]{4}[a-z]+)/?', source.text or '')
                                if match:
                                    code = match[1]
                valid_count += 1
                if code in works:
                    complete.add(code)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
            invalid.append(str(path.relative_to(root)))
    partial = []
    for path in library.glob('*/*.txt'):
        code = path.parent.name
        if code not in works or code in complete or not local(path):
            continue
        # Count the downloader's saved episode markers, not arbitrary text lines.
        saved = 0; checkpoint_total = None
        with path.open(errors='replace') as stream:
            for index, line in enumerate(stream):
                if index < 40:
                    match = re.fullmatch(r'話数[：:]\s*(\d+)\s*', line)
                    if match:
                        checkpoint_total = int(match[1])
                if re.fullmatch(r'［＃「.*」は(?:大|中|小)見出し］\s*', line):
                    saved += 1
        partial.append({'ncode': code, 'title': str(works[code].get('title', ''))[:200],
                        'saved_episodes': saved, 'checkpoint_total_episodes': checkpoint_total,
                        'candidate_episodes': works[code].get('general_all_no'),
                        'text_bytes': path.stat().st_size})
    records = []; truncated = False
    log = library / 'batch.jsonl'
    if log.is_file() and local(log):
        with log.open('rb') as stream:
            if log.stat().st_size > 8 * 1024 * 1024:
                stream.seek(-8 * 1024 * 1024, 2); stream.readline(); truncated = True
            for line in stream:
                try:
                    item = json.loads(line)
                    if item.get('ncode') in works:
                        records.append({k: item.get(k) for k in ('ncode', 'success', 'at', 'returncode')})
                except (ValueError, AttributeError):
                    continue
    processes = []
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if path.stat().st_uid != os.getuid():
                continue
            script, args = python_script(path.read_bytes().split(b'\0'))
            if (script == 'narou_library.py' and args and args[0] == 'download' and '--execute' in args) or (
                script == 'novel_downloader.py' and any(a.startswith(('https://ncode.syosetu.com/', 'http://ncode.syosetu.com/')) for a in args)
                and not any(a in args for a in ('--dry-run', '--check-update', '--help'))):
                processes.append(int(path.parent.name))
        except (OSError, ValueError):
            continue
    latest = {x['ncode']: x for x in records}
    return {'data_present': True, 'scope': 'secretary container only; Mac processes are not inspected',
            'candidate_count': len(works), 'collected_at': data.get('collected_at'),
            'completed_candidates': len(complete), 'epub_files': len(epubs),
            'epub_format_valid': valid_count, 'invalid_epubs': invalid[:20],
            'partial': partial, 'not_completed': len(works) - len(complete),
            'last_batch_record': records[-1] if records else None,
            'batch_records_read': len(records), 'batch_log_truncated': truncated,
            'unresolved_logged_failures': [k for k, v in latest.items() if v['success'] is False and k not in complete],
            'running_process_ids': processes,
            'notes': 'EPUB count confirms local ZIP/mimetype, not complete text or current website episode coverage. '
                     'Saved TXT episode markers are checkpoints; candidate episode totals may be older. '
                     'No network access, acquisition restart, or file modification was performed.'}


def specs():
    string = {'type': 'string'}
    args = {'type': 'array', 'items': string, 'maxItems': 100}
    definitions = [
        ('catalog', '利用可能なKarakeepツールと制約を一覧表示する。実行しない。', {}, []),
        ('data_files', 'データ・文書のファイル名、相対パス、サイズを検索する。本文・隠しファイルは読まず、最大2万項目で停止。shellのfind/ls/grepで保存先を探す代わりに使う。truncatedならdirectoryを絞る。',
         {'query': string, 'directory': string, 'source': {'type': 'string', 'enum': ['repository', 'documents']},
          'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}, []),
        ('study_status', '医学書・学習教材EPUBの変換進捗、医学/非医学別件数、保存済み停止位置、出力ファイルと現在の空き容量を読む。statusの汎用runやshell探索は不要。変換は起動しない。',
         {'scope': {'type': 'string', 'enum': ['medical', 'nonmedical', 'all']}}, []),
        ('gpu_diagnostics', 'OCR用Pythonの実環境でTorch/CUDA/YomiTokuと小さなGPU計算を確認。隔離shellでGPUなしと誤判定しない。任意コマンドやOCRは実行しない。', {}, []),
        ('list_epubs', 'ローカルEPUBの一覧・検索。ファイル名、保存先、サイズと既知のなろう作品名だけを返す。本文は読まない。ダウンロード対象の保存先探しに使い、shell検索をしない。',
         {'query': string, 'directory': string, 'source': {'type': 'string', 'enum': ['repository', 'documents']},
          'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}, []),
        ('export_epub', '完成済みEPUBをNanoMuseのダウンロード用成果物にする。原本を保持し、新しいworkspaceファイルを作る。返るworkspace_pathを案内。本文は会話に返さない。',
         {'path': string, 'source': {'type': 'string', 'enum': ['repository', 'documents']}}, ['path']),
        ('narou_status', '小説家になろうの取得進捗を読み取り専用で確認。候補・取得済EPUB・途中TXT・保存話数・バッチ記録・実行中PID。ワークスペース外の固定データをMCP側で読む。検索shellやcollect/downloadの再実行は不要。', {}, []),
        ('inspect', '固定版のツールソースと引数・制約を読む。--helpを実行しない。', {'path': string}, ['path']),
        ('run', '固定版Karakeep-toolをジョブとして実行。外部変更や上書きの対象を確認して使う。', {'path': string, 'args': args}, ['path']),
        ('job_status', 'ジョブ状態とログを確認。完了待ちはwait_seconds=45で行い、shellのsleepは使わない。最長45秒で状態を返す。',
         {'job_id': string, 'wait_seconds': {'type': 'integer', 'minimum': 0, 'maximum': 45}}, ['job_id']),
        ('karakeep_read', 'Karakeep CLIの固定された読み取り操作。認証情報はサービスが渡す。', {'args': args}, ['args']),
        ('karakeep_create', 'KarakeepへURLまたはノートを1件登録。既存記事は変更・削除しない。',
         {'url': string, 'note': string}, []),
        ('karakeep_tags', '指定した1件の記事のタグだけを追加・除去。記事本体の削除はできない。',
         {'bookmark_id': string, 'add': args, 'remove': args}, ['bookmark_id']),
        ('karakeep_delete_plan', '削除する記事IDを固定した計画を作る。削除は実行しない。返るコマンドで管理者が対象と件数を確認する。',
         {'bookmark_ids': {'type': 'array', 'items': string, 'minItems': 1, 'maxItems': 100}}, ['bookmark_ids']),
        ('karakeep_batch_plan', '登録・タグ整理・更新・削除の一括計画だけを作る。1..100操作を固定し、管理者確認後に一度だけ実行。',
         {'actions': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': {'type': 'object',
           'properties': {'operation': {'type': 'string', 'enum': ['create', 'tags', 'update', 'delete']},
                          'bookmark_id': string, 'url': string, 'note': string, 'title': string,
                          'add': args, 'remove': args, 'archived': {'type': 'boolean'}, 'favourited': {'type': 'boolean'}},
           'required': ['operation'], 'additionalProperties': False}}}, ['actions']),
        ('karakeep_plan_status', '確認計画の固定された対象、件数、完了・部分失敗の状態を読む。実行しない。',
         {'plan_id': string}, ['plan_id']),
        ('dictionary', '英辞郎・dict.cc・WaDoku原本を新しい専用フォルダへ変換。元ファイルと既存辞書を上書きしない。',
         {'kind': {'type': 'string', 'enum': ['eijiro', 'dictcc', 'wadoku']}, 'input_file': string,
          'swap': {'type': 'boolean'}}, ['kind', 'input_file']),
        ('translate', 'PLaMo 3 TranslateをGPUで実行し新しい文書に保存。ローカル推論、終了時VRAM解放。',
         {'text': string, 'input_file': string, 'output_file': string, 'source_lang': string,
          'target_lang': string, 'context': string, 'form': {'type': 'string', 'enum': ['plain', 'polite']},
          'glossary': {'type': 'array', 'items': {'type': 'object', 'properties': {'source': string, 'target': string},
                      'required': ['source', 'target'], 'additionalProperties': False}, 'maxItems': 100}}, ['output_file']),
        ('doctor', 'ツール、スキル、CUDAデバイス、モデル、データ配置を点検。バッチは起動しない。', {}, []),
    ]
    return [{'name': name, 'description': desc, 'inputSchema': {'type': 'object', 'properties': props,
             'required': required, 'additionalProperties': False}} for name, desc, props, required in definitions]


def invoke(name, args):
    if name == 'data_files':
        return data_files(args.get('query', ''), args.get('directory', 'data' if args.get('source', 'repository') == 'repository' else ''), args.get('source', 'repository'), args.get('limit', 20))
    if name == 'study_status':
        return study_status(args.get('scope', 'medical'))
    if name == 'gpu_diagnostics':
        return gpu_diagnostics()
    if name == 'list_epubs':
        return list_epubs(args.get('query', ''), args.get('directory', ''), args.get('source', 'repository'), args.get('limit', 20))
    if name == 'export_epub':
        return export_epub(args['path'], args.get('source', 'repository'))
    if name == 'narou_status':
        return narou_status()
    if name == 'karakeep_write':
        raise ValueError('karakeep_write is retired; use create/tags or an operator-confirmed plan')
    if name == 'karakeep_create':
        return gateway_request('POST', '/actions/create', args)
    if name == 'karakeep_tags':
        return gateway_request('POST', '/actions/tags', args)
    if name == 'karakeep_delete_plan':
        ids = args['bookmark_ids']
        if not isinstance(ids, list) or not ids or len(ids) > 100 or len(ids) != len(set(ids)):
            raise ValueError('provide 1..100 unique bookmark ids')
        return gateway_request('POST', '/plans', {'actions': [{'operation': 'delete', 'bookmark_id': x} for x in ids]})
    if name == 'karakeep_batch_plan':
        return gateway_request('POST', '/plans', args)
    if name == 'karakeep_plan_status':
        plan_id = args['plan_id']
        if not isinstance(plan_id, str) or not re.fullmatch('[a-f0-9]{32}', plan_id):
            raise ValueError('invalid plan id')
        return gateway_request('GET', '/plans/' + plan_id)
    if name == 'catalog':
        return catalog()
    if name == 'inspect':
        entry, target = tool_entry(args['path'])
        return {**entry, 'source': target.read_text()[:45000], 'source_truncated': target.stat().st_size > 45000}
    if name == 'run':
        tool_entry(args['path'])
        check_legacy_access(args['path'], args.get('args', []))
        return start_job('tool', args)
    if name == 'job_status':
        wait = args.get('wait_seconds', 0)
        if type(wait) is not int or not 0 <= wait <= 45:
            raise ValueError('wait_seconds must be an integer from 0 to 45')
        folder = job_folder(args['job_id'])
        deadline = time.monotonic() + wait
        while True:
            value = json.loads((folder / 'status.json').read_text())
            if value['state'] == 'running':
                try:
                    os.kill(value['pid'], 0)
                except ProcessLookupError:
                    value.update(state='interrupted', error='worker stopped; inspect output before retrying')
            remaining = deadline - time.monotonic()
            if value['state'] not in ('queued', 'running') or remaining <= 0:
                break
            time.sleep(min(0.5, remaining))
        log = folder / 'output.log'
        if log.exists():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 6000))
                value['log_tail'] = redact(stream.read().decode('utf-8', errors='replace'))
        return value
    if name == 'karakeep_read':
        argv = validate_args(args['args'])
        if not argv or any(x.startswith(('--api-key', '--server-addr', '--config')) for x in argv):
            raise ValueError('credentials and destination flags are supplied by the service')
        if not (argv == ['whoami'] or len(argv) >= 2 and tuple(argv[:2]) in {
            ('bookmarks', 'list'), ('bookmarks', 'search'), ('bookmarks', 'get'), ('lists', 'list'), ('lists', 'get')
        }):
            raise ValueError('not an approved read command')
        read_credentials()
        result = subprocess.run(['/usr/local/bin/karakeep', *argv], env=child_env(), cwd=REPO,
                                capture_output=True, text=True, timeout=90)
        return {'exit_code': result.returncode, 'stdout': redact(result.stdout[-24000:]),
                'stderr': redact(result.stderr[-2000:])}
    if name == 'dictionary':
        paths = {'eijiro': 'tools/dictionaries/eijiro_to_stardict.py',
                 'dictcc': 'tools/dictionaries/german-dict/convert_dictcc.py',
                 'wadoku': 'tools/dictionaries/german-dict/convert_wadoku.py'}
        path = paths[args['kind']]
        tool_entry(path)
        source = within(REPO / 'data', args['input_file'], existing=True)
        output = REPO / 'data/dictionaries/generated' / uuid.uuid4().hex
        output.mkdir(parents=True, mode=0o700)
        return start_job('dictionary', {'path': path, 'input': str(source), 'output': str(output),
                         'swap': bool(args.get('swap')) and args['kind'] == 'dictcc'})
    if name == 'translate':
        if bool(args.get('text')) == bool(args.get('input_file')):
            raise ValueError('provide exactly one of text and input_file')
        text = args.get('text')
        if not text:
            source = within(DOCS, args['input_file'], existing=True)
            if source.stat().st_size > 1024 * 1024:
                raise ValueError('input file too large; split it first')
            text = source.read_text()
        if not isinstance(text, str) or len(text) > 100000 or not text.strip():
            raise ValueError('source must contain 1..100000 characters')
        output = within(DOCS, args['output_file'])
        if output.exists():
            raise ValueError('output already exists; choose a new file')
        output.parent.mkdir(parents=True, exist_ok=True)
        return start_job('translate', {**args, 'text': text, 'output': str(output)})
    if name == 'doctor':
        return doctor()
    raise ValueError('unknown tool')


def doctor():
    expected = json.loads((INSTALL / 'skills-manifest.json').read_text())
    skills = Path('/home/secretary/.nanomuse/skills')
    missing = [n for n in expected if not (skills / n / 'SKILL.md').is_file()]
    return {'codex_cli': Path('/usr/local/bin/codex').exists(),
            'codex_config': Path('/home/secretary/.codex/config.toml').exists(),
            'tool_python': Path(PYTHON).exists(), 'plamo_python': Path(PLAMO_PYTHON).exists(),
            'ocr_python': Path('/opt/secretary-ocr/bin/python').exists(),
            'karakeep_cli': Path('/usr/local/bin/karakeep').exists(),
            'karakeep_scoped_connection': CONFIG.exists() and bool(json.loads(CONFIG.read_text()).get('karakeep', {}).get('managed_proxy')),
            'credentials_configured': CONFIG.exists() and
            bool(json.loads(CONFIG.read_text()).get('karakeep', {}).get('key')),
            'catalog_entries': len(catalog()['tools']), 'missing_skills': missing,
            'gpu_devices': [str(p) for p in Path('/dev').glob('nvidia[0-9]*')],
            'model_downloaded': (INSTALL / 'plamo.revision').exists() and
            any(Path('/var/lib/secretary-models/plamo-3-translate-2b').glob('*.safetensors')),
            'data_present': (REPO / 'data').is_dir() and any((REPO / 'data').iterdir()),
            'notes': 'GPU inference, external API and source data completeness require separate functional checks'}


def mcp():
    for line in sys.stdin:
        message = {}
        try:
            message = json.loads(line)
            if 'id' not in message:
                continue
            method = message.get('method')
            if method == 'initialize':
                result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'secretary-tools', 'version': '1.0.0'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': specs()}
            elif method == 'tools/call':
                params = message['params']
                found = next((x for x in specs() if x['name'] == params['name']), None)
                if found is None:
                    raise ValueError('Unknown or retired tool; karakeep_write is no longer available')
                spec = found['inputSchema']
                args = params.get('arguments', {})
                if not isinstance(args, dict) or set(args) - set(spec['properties']) or any(k not in args for k in spec['required']):
                    raise ValueError('invalid arguments')
                value = invoke(params['name'], args)
                result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]}
            else:
                print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'unknown method'}}), flush=True)
                continue
        except Exception as exc:
            result = {'isError': True, 'content': [{'type': 'text', 'text': redact(str(exc))[:2000]}]}
        print(json.dumps({'jsonrpc': '2.0', 'id': message.get('id'), 'result': result}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['mcp', 'worker', 'doctor'])
    parser.add_argument('job_id', nargs='?')
    args = parser.parse_args()
    if args.command == 'mcp':
        mcp()
    elif args.command == 'worker':
        worker(args.job_id)
    else:
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
