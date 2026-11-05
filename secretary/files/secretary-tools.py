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
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.request
import urllib.error

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


def specs():
    string = {'type': 'string'}
    args = {'type': 'array', 'items': string, 'maxItems': 100}
    definitions = [
        ('catalog', '利用可能なKarakeepツールと制約を一覧表示する。実行しない。', {}, []),
        ('inspect', '固定版のツールソースと引数・制約を読む。--helpを実行しない。', {'path': string}, ['path']),
        ('run', '固定版Karakeep-toolをジョブとして実行。外部変更や上書きの対象を確認して使う。', {'path': string, 'args': args}, ['path']),
        ('job_status', '実行ジョブの完了状態とログ末尾を確認。失敗を成功と報告しない。', {'job_id': string}, ['job_id']),
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
        folder = job_folder(args['job_id'])
        value = json.loads((folder / 'status.json').read_text())
        if value['state'] == 'running':
            try:
                os.kill(value['pid'], 0)
            except ProcessLookupError:
                value.update(state='interrupted', error='worker stopped; inspect output before retrying')
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
