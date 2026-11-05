#!/usr/bin/env python3
"""Separate raw Karakeep credentials and operator-confirmed mutations from AI users."""
import argparse
import fcntl
import getpass
import contextlib
import pwd
import stat
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

CONFIG = Path('/etc/secretary-karakeep.json')
PLANS = Path('/var/lib/secretary-karakeep/plans')
RUNTIME = Path('/home/secretary/.config/secretary/connections.json')
ENV_FILE = Path('/srv/secretary/karakeep-tool/.env')
ORIGIN = 'http://127.0.0.1:8766'
MAX_ACTIONS = 100
READ_QUERIES = {'users.whoami', 'users.stats', 'bookmarks.getBookmark', 'bookmarks.getBookmarks',
                'lists.list', 'lists.get', 'tags.list'}


def atomic_json(path, value, mode=0o600, owner=None):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            if owner is not None:
                os.fchown(output.fileno(), *owner)
            json.dump(value, output, ensure_ascii=False, indent=2)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else {}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def fingerprint(config):
    return hashlib.sha256(canonical({'url': config.get('url'), 'key': config.get('key')})).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError('invalid bookmark id')
    return value


def bounded_text(value, maximum=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('invalid text length')
    return value


def validate_action(value):
    if not isinstance(value, dict):
        raise ValueError('action must be an object')
    kind = value.get('operation')
    fields = {'create': {'operation', 'url', 'note'}, 'tags': {'operation', 'bookmark_id', 'add', 'remove'},
              'update': {'operation', 'bookmark_id', 'title', 'note', 'archived', 'favourited'},
              'delete': {'operation', 'bookmark_id'}}
    if kind not in fields or set(value) - fields[kind]:
        raise ValueError('unsupported action or fields')
    result = {'operation': kind}
    if kind != 'create':
        result['bookmark_id'] = identifier(value.get('bookmark_id'))
    if kind == 'create':
        if bool(value.get('url')) == bool(value.get('note')):
            raise ValueError('provide exactly one of url and note')
        if value.get('url'):
            url = bounded_text(value['url'], 4096)
            parts = urllib.parse.urlsplit(url)
            if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
                raise ValueError('invalid bookmark URL')
            result['url'] = url
        else:
            result['note'] = bounded_text(value['note'])
    elif kind == 'tags':
        for field in ('add', 'remove'):
            tags = value.get(field, [])
            if not isinstance(tags, list) or len(tags) > 30:
                raise ValueError('invalid tag list')
            result[field] = [bounded_text(x, 100) for x in tags]
            if len(result[field]) != len(set(result[field])):
                raise ValueError('duplicate tags')
        if not result['add'] and not result['remove'] or set(result['add']) & set(result['remove']):
            raise ValueError('empty or conflicting tags')
    elif kind == 'update':
        for field in ('title', 'note'):
            if field in value:
                if not isinstance(value[field], str) or len(value[field]) > 10000:
                    raise ValueError('invalid update text')
                result[field] = value[field]
        for field in ('archived', 'favourited'):
            if field in value:
                if not isinstance(value[field], bool):
                    raise ValueError('expected boolean')
                result[field] = value[field]
        if len(result) == 2:
            raise ValueError('no update fields')
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upstream(config, method, path, body=None):
    if not config.get('url') or not config.get('key'):
        raise ValueError('Karakeep is not configured: dev secretary setup karakeep')
    request = urllib.request.Request(config['url'].rstrip('/') + path, data=body, method=method,
                                    headers={'Authorization': 'Bearer ' + config['key'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
            return response.read(), response.headers.get('Content-Type', 'application/json')
    except urllib.error.HTTPError as error:
        raise ValueError('Karakeep HTTP ' + str(error.code)) from None
    except (OSError, urllib.error.URLError):
        raise ValueError('Karakeep connection failed') from None


def execute_action(config, action):
    kind = action['operation']
    if kind == 'create':
        method = 'bookmarks.createBookmark'
        data = {'source': 'cli', 'type': 'link', 'url': action['url']} if 'url' in action else {
            'source': 'cli', 'type': 'text', 'text': action['note']}
    elif kind == 'tags':
        method = 'bookmarks.updateTags'
        data = {'bookmarkId': action['bookmark_id'], 'attach': [{'tagName': x} for x in action['add']],
                'detach': [{'tagName': x} for x in action['remove']]}
    elif kind == 'update':
        method = 'bookmarks.updateBookmark'
        data = {'bookmarkId': action['bookmark_id'], **{k: v for k, v in action.items() if k not in ('operation', 'bookmark_id')}}
    else:
        method = 'bookmarks.deleteBookmark'; data = {'bookmarkId': action['bookmark_id']}
    raw, _ = upstream(config, 'POST', '/api/trpc/' + method + '?batch=1',
                      canonical({'0': {'json': data}}))
    response = json.loads(raw)
    if not isinstance(response, list) or len(response) != 1 or 'error' in response[0] or 'result' not in response[0]:
        raise ValueError('Karakeep action failed; result is not confirmed')
    return {'ok': True}


def allowed_read(path):
    parts = urllib.parse.urlsplit(path)
    if parts.scheme or parts.netloc or parts.fragment:
        return False
    decoded = urllib.parse.unquote(parts.path)
    if '\\' in decoded or '//' in decoded or '..' in decoded.split('/'):
        return False
    if decoded.startswith('/api/trpc/'):
        names = decoded[len('/api/trpc/'):].split(',')
        return bool(names) and all(name in READ_QUERIES for name in names)
    return bool(re.fullmatch(r'/api/v1/(bookmarks|lists|tags|assets)(/[A-Za-z0-9_/-]+)?', decoded)
                or re.fullmatch(r'/api/assets/[A-Za-z0-9_-]+', decoded) or decoded == '/api/v1/users/me')


def plan_path(plan_id, directory=PLANS):
    if not isinstance(plan_id, str) or not re.fullmatch(r'[a-f0-9]{32}', plan_id):
        raise ValueError('invalid plan id')
    path = directory / (plan_id + '.json')
    if path.is_symlink():
        raise ValueError('invalid plan file')
    return path


def public_plan(plan):
    return {k: v for k, v in plan.items() if k != 'upstream_identity'}


def create_plan(config, actions, directory=PLANS):
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise ValueError('plan must contain 1..100 actions')
    actions = [validate_action(x) for x in actions]
    encoded = [canonical(x) for x in actions]
    if len(encoded) != len(set(encoded)):
        raise ValueError('duplicate actions')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    plan_id = secrets.token_hex(16)
    previews = []
    ids = sorted({x['bookmark_id'] for x in actions if 'bookmark_id' in x})
    for bookmark_id in ids:
        raw, _ = upstream(config, 'GET', '/api/v1/bookmarks/' + bookmark_id)
        item = json.loads(raw)
        previews.append({'id': bookmark_id, 'title': str(item.get('title') or '')[:200],
                         'url': str((item.get('content') or {}).get('url') or '')[:1000]})
    plan = {'id': plan_id, 'state': 'pending', 'actions': actions, 'action_count': len(actions),
            'bookmark_count': len(ids), 'targets': previews, 'created': time.time(), 'expires': time.time() + 3600,
            'upstream_identity': fingerprint(config), 'sha256': hashlib.sha256(canonical(actions)).hexdigest(),
            'approve_command': 'dev secretary approve ' + plan_id}
    atomic_json(plan_path(plan_id, directory), plan)
    return public_plan(plan)


def apply_plan(plan_id, config, directory=PLANS, confirm=None):
    if os.geteuid() != 0:
        raise PermissionError('only the operator can approve a plan')
    path = plan_path(plan_id, directory)
    metadata = path.stat()
    with path.with_suffix('.lock').open('a+') as locked:
        fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = read_json(path)
        if plan['state'] != 'pending' or plan['expires'] < time.time():
            raise ValueError('plan is no longer pending; create a new plan')
        if plan['upstream_identity'] != fingerprint(config):
            raise ValueError('Karakeep connection changed; create a new plan')
        actions = [validate_action(x) for x in plan['actions']]
        ids = {a['bookmark_id'] for a in actions if 'bookmark_id' in a}
        if plan['action_count'] != len(actions) or plan['bookmark_count'] != len(ids):
            raise ValueError('plan count changed; create a new plan')
        digest = hashlib.sha256(canonical(actions)).hexdigest()
        if digest != plan['sha256']:
            raise ValueError('plan changed; create a new plan')
        if confirm is None or not confirm(public_plan(plan)):
            return {'state': 'cancelled', 'executed': 0}
        if plan['expires'] < time.time():
            raise ValueError('plan expired during confirmation; create a new plan')
        # Persist before the first request. Failure/crash never grants a reusable retry.
        def save():
            atomic_json(path, plan, owner=(metadata.st_uid, metadata.st_gid))
        plan.update(state='executing', approved=time.time(), results=[]); save()
        try:
            for action in actions:
                execute_action(config, action)
                plan['results'].append({'ok': True}); save()
            plan['state'] = 'completed'
        except Exception as error:
            plan.update(state='failed', error=type(error).__name__, retry='Create a new plan after checking partial results')
        plan['finished'] = time.time(); save()
        return public_plan(plan)


class Gateway:
    def __init__(self, config, directory=PLANS):
        self.config, self.directory = config, directory

    def dispatch(self, method, path, value=None):
        if method == 'GET' and allowed_read(path):
            return upstream(self.config, 'GET', path)
        if method == 'GET' and path.startswith('/plans/'):
            plan = read_json(plan_path(path[len('/plans/'):], self.directory))
            if not plan:
                raise ValueError('plan not found')
            result = public_plan(plan)
        elif method == 'POST' and path == '/actions/create':
            action = validate_action({'operation': 'create', **value})
            if action['operation'] != 'create':
                raise ValueError('wrong operation')
            result = execute_action(self.config, action)
        elif method == 'POST' and path == '/actions/tags':
            action = validate_action({'operation': 'tags', **value})
            if action['operation'] != 'tags':
                raise ValueError('wrong operation')
            result = execute_action(self.config, action)
        elif method == 'POST' and path == '/plans':
            if not isinstance(value, dict) or set(value) != {'actions'}:
                raise ValueError('expected actions')
            result = create_plan(self.config, value['actions'], self.directory)
        else:
            raise PermissionError('raw writes and plan execution are not exposed to AI clients')
        return canonical(result), 'application/json'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        gateway = self.server.gateway
        token = self.headers.get('Authorization', '')
        if not hmac.compare_digest(token, 'Bearer ' + gateway.config['proxy_token']):
            self.send_error(401); return
        try:
            value = None
            if self.command == 'POST':
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError('request too large or empty')
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError('expected object')
            body, content_type = gateway.dispatch(self.command, self.path, value)
            self.send_response(200); self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as error:
            body = canonical({'error': str(error) if isinstance(error, (ValueError, PermissionError)) else type(error).__name__})
            self.send_response(403 if isinstance(error, PermissionError) else 400)
            self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = handle_request


@contextlib.contextmanager
def user_parent(path):
    """Anchor every parent with openat/O_NOFOLLOW; root never follows an AI symlink."""
    path = Path(path).absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = next_fd
        yield fd, path.name
    finally:
        os.close(fd)


def runtime_owner(owner=None):
    if owner is not None:
        return owner
    account = pwd.getpwnam('secretary')
    return account.pw_uid, account.pw_gid


def read_user_file(path, owner):
    with user_parent(path) as (directory, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return ''
        with os.fdopen(fd) as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != owner[0] or metadata.st_nlink != 1 or metadata.st_size > 2 * 1024 * 1024:
                raise ValueError('runtime settings must be a single AI-owned regular file')
            content = stream.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError('runtime settings too large')
            return content


def write_user_file(path, text, owner):
    with user_parent(path) as (directory, name):
        temporary = '.secretary-' + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                os.fchown(stream.fileno(), *owner)
                stream.write(text); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass


def write_runtime(config, runtime=RUNTIME, env_file=ENV_FILE, owner=None):
    if not config.get('url') or not config.get('key'):
        return
    owner = runtime_owner(owner)
    text = read_user_file(runtime, owner)
    data = json.loads(text) if text else {}
    data['karakeep'] = {'url': ORIGIN, 'key': config['proxy_token'], 'managed_proxy': True}
    # Read and validate both destinations before replacing either file.
    env_text = read_user_file(env_file, owner) if env_file.parent.exists() else None
    content = None
    if env_text is not None:
        lines = [line for line in env_text.splitlines() if not re.match(r'\s*(?:export\s+)?(?:URL|API_KEY|KARAKEEP_API_KEY|KARAKEEP_SERVER_ADDR)\s*=', line)]
        lines = [line for line in lines if line != '# managed by secretary/tools-install']
        content = '# managed by secretary/tools-install\n' + '\n'.join(lines) + '\nURL=' + ORIGIN + '\nAPI_KEY=' + config['proxy_token'] + '\n'
    write_user_file(runtime, json.dumps(data, ensure_ascii=False, indent=2), owner)
    if content is not None:
        write_user_file(env_file, content, owner)


def configure_root(config_path=CONFIG, runtime=RUNTIME, env_file=ENV_FILE, interactive=False, owner=None):
    if os.geteuid() != 0:
        raise PermissionError('run setup through dev secretary setup karakeep')
    config = read_json(config_path)
    owner = runtime_owner(owner)
    text = read_user_file(runtime, owner)
    current = (json.loads(text) if text else {}).get('karakeep', {})
    if current.get('managed_proxy') and not config.get('key') and not interactive:
        raise ValueError('root Karakeep credentials missing; run setup karakeep')
    if current.get('key') and not current.get('managed_proxy'):
        if not config.get('key'):
            config.update(url=current['url'], key=current['key'])
        elif not interactive and (current.get('url', '').rstrip('/') != config.get('url', '').rstrip('/') or current['key'] != config['key']):
            raise ValueError('operator credentials are authoritative; run setup karakeep to reconcile runtime settings')
    if interactive:
        url = input('Karakeep URL [' + config.get('url', '') + ']: ').strip() or config.get('url', '')
        key = getpass.getpass('Karakeep API key (blank keeps existing): ') or config.get('key', '')
        config.update(url=url, key=key)
    if config.get('url'):
        parts = urllib.parse.urlsplit(config['url'])
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or config['url'].rstrip('/') == ORIGIN:
            raise ValueError('invalid upstream URL')
        if not re.fullmatch(r'ak[0-9]+_[A-Za-z0-9]+_[A-Za-z0-9]+', config.get('key', '')):
            raise ValueError('invalid Karakeep API key format')
    config.setdefault('proxy_token', 'ak2_proxy_' + secrets.token_hex(32))
    atomic_json(config_path, config, 0o640)
    write_runtime(config, runtime, env_file, owner)
    return config


def confirm_terminal(plan):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PermissionError('approval requires an operator terminal')
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    phrase = 'APPLY ' + str(plan['action_count']) + ' ' + plan['sha256'][:8]
    return input('Confirm exact targets/actions by typing ' + phrase + ': ') == phrase


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['serve', 'migrate', 'setup', 'approve'])
    parser.add_argument('plan_id', nargs='?')
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            server = ThreadingHTTPServer(('127.0.0.1', 8766), Handler)
            server.gateway = Gateway(read_json(CONFIG)); server.serve_forever()
        elif args.command in ('migrate', 'setup'):
            configure_root(interactive=args.command == 'setup')
            print('Karakeep gateway configured; raw credentials stay outside the AI account')
        else:
            result = apply_plan(args.plan_id, read_json(CONFIG), confirm=confirm_terminal)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result['state'] not in ('completed', 'cancelled'):
                raise SystemExit(1)
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr); raise SystemExit(1)
