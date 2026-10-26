"""Credential isolation, read-only MCP and failure recovery checks; no live accounts."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('secretary', Path(__file__).parents[1] / 'files/secretary.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SecretaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.patches = patch.multiple(s, ROOT=root / 'config', HERMES=root / 'hermes', TT_ROOT=root / 'timetree')
        self.patches.start()
        self.nano_patch = patch.object(s, 'NANOMUSE', root / 'nanomuse')
        self.nano_patch.start()
        self.addCleanup(self.nano_patch.stop)
        self.addCleanup(self.patches.stop)

    def test_readiness_does_not_disclose_credentials_or_connect(self):
        from types import SimpleNamespace
        s.HERMES.mkdir()
        (s.HERMES / 'config.yaml').write_text('model:\n  provider: ollama-cloud\n  default: selected-model\n')
        (s.HERMES / '.env').write_text('OLLAMA_API_KEY=DO-NOT-PRINT\n')
        s.write_json(s.ROOT / 'gmail.json', {'client_id': 'private-id', 'refresh_token': 'private-token'})
        s.write_json(s.ROOT / 'connections.json', {'plane': {'url': 'https://private.invalid', 'key': 'plane_api_private-key', 'workspace': 'private-space'}})
        out = io.StringIO()
        with patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), patch.object(s, 'request_json') as req, contextlib.redirect_stdout(out):
            s.readiness()
        req.assert_not_called()
        report = out.getvalue()
        self.assertIn('model\tready\t', report)
        self.assertIn('gmail\tready\t', report)
        self.assertIn('outlook\tpending\t', report)
        self.assertIn('plane\tready\t', report)
        self.assertNotIn('DO-NOT-PRINT', report)
        self.assertNotIn('private-', report)
        self.assertNotIn('private.invalid', report)

    def test_nanomuse_readiness_uses_local_api_and_hides_token(self):
        from types import SimpleNamespace
        s.NANOMUSE.mkdir()
        (s.NANOMUSE / 'server_token').write_text('DO-NOT-PRINT-TOKEN')
        out = io.StringIO()
        with patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=3)), \
             patch.object(s, 'request_json', return_value={'llm': {'model': 'selected', 'key_source': 'vault'}}) as req, \
             contextlib.redirect_stdout(out):
            s.readiness()
        self.assertEqual(req.call_args.args[0], 'http://127.0.0.1:8787/api/connections')
        self.assertIn('nanomuse-model\tready\t', out.getvalue())
        self.assertNotIn('DO-NOT-PRINT', out.getvalue())

    def test_upstream_auto_defaults_are_not_configured(self):
        from types import SimpleNamespace
        s.HERMES.mkdir()
        (s.HERMES / 'config.yaml').write_text('model:\n  provider: auto\n  default: anthropic/default-model\n')
        out = io.StringIO()
        with patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=3)), contextlib.redirect_stdout(out):
            s.readiness()
        self.assertIn('model\tpending\t', out.getvalue())

    def test_readiness_checks_ollama_key_not_just_model_name(self):
        from types import SimpleNamespace
        s.HERMES.mkdir()
        (s.HERMES / 'config.yaml').write_text('model:\n  provider: ollama-cloud\n  default: selected-model\n')
        out = io.StringIO()
        with patch.dict(os.environ, {'OLLAMA_API_KEY': ''}), patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=3)), contextlib.redirect_stdout(out):
            s.readiness()
        self.assertIn('model\tpending\t', out.getvalue())
        self.assertIn('notes\tpending\t', out.getvalue())

    def test_api_setup_uses_private_defaults_without_enabling_unconfigured_tools(self):
        s.write_json(s.ROOT / 'connection-defaults.json', {
            'plane': {'url': 'https://api.example.invalid', 'workspace': 'personal-space'}})
        self.assertNotIn('plane_projects', [tool['name'] for tool in s.tool_specs()])
        with patch.object(s, 'prompt', side_effect=lambda label, default='': default), \
             patch.object(s.getpass, 'getpass', return_value='plane_api_private-key'), \
             contextlib.redirect_stdout(io.StringIO()):
            s.api_config('plane')
        config = s.read_json(s.ROOT / 'connections.json')['plane']
        self.assertEqual(config['url'], 'https://api.example.invalid')
        self.assertEqual(config['workspace'], 'personal-space')
        self.assertEqual(config['key'], 'plane_api_private-key')
        self.assertIn('plane_projects', [tool['name'] for tool in s.tool_specs()])

    def test_invalid_keys_are_rejected_without_disclosing_or_replacing_credentials(self):
        original = {'plane': {'url': 'https://example.invalid', 'key': 'plane_api_original', 'workspace': 'space'}}
        s.write_json(s.ROOT / 'connections.json', original)
        bad = 'plane_api_private\x1b[D'
        with patch.object(s, 'prompt', side_effect=lambda label, default='': default), \
             patch.object(s.getpass, 'getpass', return_value=bad):
            with self.assertRaises(s.InvalidAPIKeyError) as error:
                s.api_config('plane')
        self.assertNotIn('private', str(error.exception))
        self.assertEqual(s.read_json(s.ROOT / 'connections.json'), original)
        with self.assertRaises(s.InvalidAPIKeyError):
            s.validate_api_key('karakeep', 'my-key-name')
        self.assertEqual(s.validate_api_key('karakeep', ' ak2_identifier_secret '), 'ak2_identifier_secret')

    def test_private_atomic_credentials(self):
        path = s.ROOT / 'gmail.json'
        s.write_json(path, {'refresh_token': 'private'})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        s.write_json(path, {'refresh_token': 'rotated'})
        self.assertEqual(s.read_json(path)['refresh_token'], 'rotated')
        self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_refresh_rotation(self):
        path = s.ROOT / 'outlook.json'
        s.write_json(path, {'client_id': 'id', 'refresh_token': 'old', 'token_url': 'https://example.invalid/token'})
        with patch.object(s, 'request_json', return_value={'access_token': 'access', 'refresh_token': 'new'}):
            self.assertEqual(s.access_token('outlook'), 'access')
        self.assertEqual(s.read_json(path)['refresh_token'], 'new')

    def test_failed_refresh_preserves_credentials(self):
        path = s.ROOT / 'gmail.json'
        original = {'client_id': 'id', 'refresh_token': 'old', 'token_url': 'https://example.invalid/token'}
        s.write_json(path, original)
        with patch.object(s, 'request_json', side_effect=ValueError('failure')):
            with self.assertRaises(ValueError):
                s.access_token('gmail')
        self.assertEqual(s.read_json(path), original)

    def mcp_call(self, message):
        out = io.StringIO()
        with patch('sys.stdin', io.StringIO(json.dumps(message) + '\n')), contextlib.redirect_stdout(out):
            s.mcp()
        return json.loads(out.getvalue())

    def test_write_tool_unavailable(self):
        result = self.mcp_call({'id': 1, 'method': 'tools/call', 'params': {'name': 'outlook_send', 'arguments': {}}})
        self.assertTrue(result['result']['isError'])

    def test_unknown_arguments_rejected(self):
        with patch.object(s, 'invoke_tool') as invoke:
            result = self.mcp_call({'id': 1, 'method': 'tools/call', 'params': {'name': 'timetree_snapshot', 'arguments': {'url': 'https://example.invalid'}}})
        invoke.assert_not_called()
        self.assertTrue(result['result']['isError'])

    def test_errors_do_not_leak_upstream_content(self):
        with patch.object(s, 'invoke_tool', side_effect=urllib.error.HTTPError('https://private.invalid/?token=SECRET', 401, 'SECRET', {}, None)):
            result = self.mcp_call({'id': 1, 'method': 'tools/call', 'params': {'name': 'timetree_snapshot', 'arguments': {}}})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertIn('HTTP 401', str(result))

    def test_plane_path_escaped_and_get_only(self):
        s.write_json(s.ROOT / 'connections.json', {'plane': {'url': 'https://example.invalid', 'key': 'plane_api_private', 'workspace': 'personal'}})
        with patch.object(s, 'request_json', return_value={}) as req:
            s.invoke_tool('plane_work_items', {'project_id': '../elsewhere', 'cursor': 'a&b'})
        self.assertIn('..%2Felsewhere', req.call_args.args[0])
        self.assertIn('cursor=a%26b', req.call_args.args[0])
        self.assertNotIn('data', req.call_args.kwargs)

    def test_date_filter_in_japan_and_all_day(self):
        events = [
            {'id': 'jst', 'start_at': '2026-10-25T16:00:00Z', 'end_at': '2026-10-25T17:00:00Z'},
            {'id': 'all', 'all_day': True, 'start_at': '2026-10-26T00:00:00Z', 'end_at': '2026-10-26T00:00:00Z'},
            {'id': 'past', 'start_at': '2026-10-24T12:00:00Z'},
            {'id': 'removed', 'deactivated_at': 1},
            {'id': 'series', 'recurrences': ['RRULE:FREQ=WEEKLY']},
            {'id': 'unknown'},
        ]
        found, series, unknown = s.select_events(events, dt.date(2026, 10, 26), dt.date(2026, 10, 27))
        self.assertEqual({e['id'] for e in found}, {'jst', 'all'})
        self.assertEqual(series[0]['id'], 'series')
        self.assertEqual(unknown[0]['id'], 'unknown')

    def test_snapshot_reports_stale_and_retains_data_on_sync_failure(self):
        cache = {'fetched_at': '2026-10-26T00:00:00+00:00', 'events': []}
        s.write_json(s.TT_ROOT / 'cache/snapshot.json', cache)
        s.write_json(s.TT_ROOT / 'credentials.json', {'email': 'test', 'password': 'private', 'calendar_ids': ['1']})
        with patch.object(s, 'request_json', side_effect=ValueError('broken')):
            with self.assertRaises(ValueError):
                s.timetree_sync()
        self.assertEqual(s.read_json(s.TT_ROOT / 'cache/snapshot.json'), cache)
        result = s.invoke_tool('timetree_snapshot', {})
        self.assertTrue(result['stale'])
        self.assertEqual(result['last_error'], 'ValueError')

    def test_timetree_pagination_and_no_write_endpoints(self):
        s.write_json(s.TT_ROOT / 'credentials.json', {'email': 'test', 'password': 'private', 'calendar_ids': ['1']})
        calls = []
        replies = [{}, {'calendars': [{'id': 1}]},
                   {'events': [{'id': 'a', 'title': 'first'}], 'chunk': True, 'since': 2},
                   {'events': [{'id': 'a', 'title': 'updated'}, {'id': 'b'}], 'chunk': False}]
        def fake(url, **kwargs):
            calls.append((url, kwargs.get('method', 'GET')))
            return replies.pop(0)
        with patch.object(s, 'request_json', side_effect=fake):
            s.timetree_sync()
        cached = s.read_json(s.TT_ROOT / 'cache/snapshot.json')
        self.assertEqual(len(cached['events']), 2)
        self.assertEqual(cached['events'][0]['title'], 'updated')
        self.assertEqual([c[1] for c in calls], ['PUT', None, None, None])
        self.assertTrue(all('/events/sync?' in c[0] for c in calls[2:]))

    def test_timetree_partial_failure_keeps_old_failed_calendar_and_marks_incomplete(self):
        s.write_json(s.TT_ROOT / 'credentials.json', {'email': 'test', 'password': 'private', 'calendar_ids': ['1', '2']})
        s.write_json(s.TT_ROOT / 'cache/snapshot.json', {'fetched_at': '2026-10-26T00:00:00+00:00',
            'events': [{'id': 'old-1', 'calendar_id': '1'}, {'id': 'old-2', 'calendar_id': '2'}]})
        replies = [{}, {'calendars': [{'id': 1}, {'id': 2}]}, {'events': [{'id': 'new-1'}], 'chunk': False},
                   urllib.error.HTTPError('https://example.invalid', 400, 'private response', {}, None)]
        def fake(url, **kwargs):
            value = replies.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        with patch.object(s, 'request_json', side_effect=fake), contextlib.redirect_stdout(io.StringIO()):
            s.timetree_sync()
        cache = s.read_json(s.TT_ROOT / 'cache/snapshot.json')
        self.assertEqual({e['id'] for e in cache['events']}, {'new-1', 'old-2'})
        result = s.invoke_tool('timetree_snapshot', {})
        self.assertTrue(result['partial'])
        self.assertTrue(result['stale'])
        self.assertEqual(result['failed_calendars'], [{'calendar_id': '2', 'error': 'HTTP 400'}])
        self.assertNotIn('private response', str(result))

    def test_timetree_inactive_calendar_is_marked_without_fetching(self):
        s.write_json(s.TT_ROOT / 'credentials.json', {'email': 'test', 'password': 'private', 'calendar_ids': ['1', '2']})
        replies = [{}, {'calendars': [{'id': 1}, {'id': 2, 'deactivated_at': 123}]}, {'events': [], 'chunk': False}]
        with patch.object(s, 'request_json', side_effect=replies) as req, contextlib.redirect_stdout(io.StringIO()):
            s.timetree_sync()
        self.assertEqual(req.call_count, 3)
        self.assertEqual(s.read_json(s.TT_ROOT / 'cache/status.json')['failed_calendars'],
                         [{'calendar_id': '2', 'error': 'InactiveCalendar'}])

    def test_calendar_list_excludes_inactive_and_prints_copyable_ids(self):
        s.write_json(s.TT_ROOT / 'cache/calendars.json', [
            {'id': 1, 'name': 'Personal'}, {'id': 2, 'name': 'Old', 'deactivated_at': 123},
            {'id': 3, 'name': 'Family\ncalendar'}])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            s.timetree_calendars()
        self.assertEqual(out.getvalue(), '1\tPersonal\n3\tFamily calendar\n')

    def test_invalid_url_credentials_rejected(self):
        for url in ('file:///etc/passwd', 'https://user:pass@example.com', 'https://example.com/?secret=foo'):
            with self.assertRaises(ValueError):
                s.safe_url(url)

    def test_init_preserves_user_settings_and_soul(self):
        import yaml
        s.HERMES.mkdir()
        (s.HERMES / 'SOUL.md').write_text('my personal instructions')
        (s.HERMES / 'config.yaml').write_text('model:\n  provider: custom\n  default: private-model\nterminal:\n  cwd: /my/docs\nmcp_servers:\n  existing:\n    command: tool\n')
        s.configure_hermes()
        s.configure_hermes()
        value = yaml.safe_load((s.HERMES / 'config.yaml').read_text())
        self.assertEqual(value['model']['default'], 'private-model')
        self.assertEqual(value['terminal']['cwd'], '/my/docs')
        self.assertIn('existing', value['mcp_servers'])
        soul = (s.HERMES / 'SOUL.md').read_text()
        self.assertTrue(soul.startswith('my personal instructions'))
        self.assertEqual(soul.count('<!-- secretary operating instructions -->'), 1)
        self.assertIn('/srv/secretary/documents', soul)


if __name__ == '__main__':
    unittest.main()
