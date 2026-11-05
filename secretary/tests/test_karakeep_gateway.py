import importlib.util
import json
import os
import io
from types import SimpleNamespace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

BASE = Path(__file__).parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

g = load('gateway', BASE / 'files/karakeep-gateway.py')
t = load('tools_gateway_test', BASE / 'files/secretary-tools.py')
m = load('migration_gateway_test', BASE / 'tooling/migrate-config.py')


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'plans'
        self.cfg = {'url': 'https://example.invalid', 'key': 'ak2_fixture_original123', 'proxy_token': 'ak2_proxy_limited'}
        self.api = g.Gateway(self.cfg, self.directory)
        self.get = patch.object(g, 'upstream', return_value=(b'{"title":"Selected article","content":{"url":"https://example.invalid/item"}}', 'application/json'))
        self.upstream = self.get.start(); self.addCleanup(self.get.stop)

    def plan(self, actions=None):
        return g.create_plan(self.cfg, actions or [{'operation': 'delete', 'bookmark_id': 'article1'}], self.directory)

    def test_raw_write_paths_and_encoded_mutators_are_never_forwarded(self):
        for method, path in [('DELETE', '/api/v1/bookmarks/article1'), ('POST', '/api/trpc/bookmarks.deleteBookmark'),
                             ('GET', '/api/trpc/bookmarks.deleteBookmark'), ('GET', '/api/trpc/bookmarks.%64eleteBookmark'),
                             ('POST', '/plans/' + 'a' * 32 + '/approve')]:
            with self.assertRaises(PermissionError):
                self.api.dispatch(method, path, {})
        self.upstream.assert_not_called()

    def test_read_endpoints_remain_usable(self):
        self.api.dispatch('GET', '/api/v1/bookmarks/search?q=hello')
        self.api.dispatch('GET', '/api/trpc/bookmarks.getBookmarks,users.whoami?batch=1')
        self.assertEqual(self.upstream.call_count, 2)
        for path in ('//outside.invalid/path', '/api/v1/bookmarks/../admin', '/api/trpc/users.settings', '/api/v1/admin/api-keys'):
            self.assertFalse(g.allowed_read(path))

    def test_create_and_tag_handlers_cannot_be_used_for_deletion(self):
        with patch.object(g, 'execute_action', return_value={'ok': True}) as execute:
            for path in ('/actions/create', '/actions/tags'):
                with self.assertRaises(ValueError):
                    self.api.dispatch('POST', path, {'operation': 'delete', 'bookmark_id': 'article1'})
            execute.assert_not_called()
            self.api.dispatch('POST', '/actions/create', {'url': 'https://example.invalid/new'})
            self.assertEqual(execute.call_args.args[1]['operation'], 'create')
            self.api.dispatch('POST', '/actions/tags', {'bookmark_id': 'article1', 'add': ['reading']})
            self.assertEqual(execute.call_args.args[1]['operation'], 'tags')

    def test_plan_creation_does_not_execute_and_counts_exact_targets(self):
        with patch.object(g, 'execute_action') as execute:
            plan = self.plan([{'operation': 'delete', 'bookmark_id': 'article1'},
                              {'operation': 'update', 'bookmark_id': 'article2', 'archived': True}])
            execute.assert_not_called()
        self.assertEqual(plan['action_count'], 2)
        self.assertEqual(plan['bookmark_count'], 2)
        self.assertNotIn('upstream_identity', plan)
        self.assertNotIn(self.cfg['key'], json.dumps(plan))
        self.assertEqual(plan['approve_command'], 'dev secretary approve ' + plan['id'])

    def test_non_operator_cannot_apply_even_if_it_knows_plan_id(self):
        plan = self.plan()
        with patch.object(g.os, 'geteuid', return_value=1000), patch.object(g, 'execute_action') as execute:
            with self.assertRaises(PermissionError):
                g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            execute.assert_not_called()

    def test_single_confirmation_executes_exact_payload_once_and_replay_is_rejected(self):
        actions = [{'operation': 'delete', 'bookmark_id': 'article1'},
                   {'operation': 'tags', 'bookmark_id': 'article2', 'add': ['reviewed']}]
        plan = self.plan(actions)
        def confirm(preview):
            self.assertEqual(preview['bookmark_count'], 2)
            self.assertEqual([a.get('bookmark_id') for a in preview['actions']], ['article1', 'article2'])
            return True
        with patch.object(g.os, 'geteuid', return_value=0), patch.object(g, 'execute_action') as execute:
            done = g.apply_plan(plan['id'], self.cfg, self.directory, confirm=confirm)
            self.assertEqual(done['state'], 'completed')
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(execute.call_args_list[0].args[1], {'operation': 'delete', 'bookmark_id': 'article1'})
            with self.assertRaises(ValueError):
                g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            self.assertEqual(execute.call_count, 2)

    def test_cancel_expiry_changed_target_and_changed_account_do_not_execute(self):
        plan = self.plan()
        with patch.object(g.os, 'geteuid', return_value=0), patch.object(g, 'execute_action') as execute:
            cancelled = g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: False)
            self.assertEqual(cancelled['executed'], 0)
            with self.assertRaises(ValueError):
                g.apply_plan(plan['id'], {**self.cfg, 'key': 'another-account'}, self.directory, confirm=lambda p: True)
            path = g.plan_path(plan['id'], self.directory)
            value = json.loads(path.read_text()); value['actions'][0]['bookmark_id'] = 'different'; g.atomic_json(path, value)
            with self.assertRaises(ValueError):
                g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            value['expires'] = time.time() - 1; g.atomic_json(path, value)
            with self.assertRaises(ValueError):
                g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            execute.assert_not_called()

    def test_partial_failure_never_retries_approved_plan(self):
        plan = self.plan([{'operation': 'delete', 'bookmark_id': 'article1'}, {'operation': 'delete', 'bookmark_id': 'article2'}])
        with patch.object(g.os, 'geteuid', return_value=0), patch.object(g, 'execute_action', side_effect=[{'ok': True}, ValueError('uncertain result')]) as execute:
            failed = g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            self.assertEqual(failed['state'], 'failed'); self.assertEqual(len(failed['results']), 1)
            with self.assertRaises(ValueError):
                g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            self.assertEqual(execute.call_count, 2)

    def test_duplicate_or_oversized_delete_scope_is_rejected(self):
        for actions in ([{'operation': 'delete', 'bookmark_id': 'same'}] * 2,
                        [{'operation': 'delete', 'bookmark_id': str(i)} for i in range(101)]):
            with self.assertRaises(ValueError): self.plan(actions)

    def test_plan_expiring_while_operator_reads_is_not_executed(self):
        clock = [100.0]
        with patch.object(g.time, 'time', side_effect=lambda: clock[0]):
            plan = self.plan()
            def confirm(_):
                clock[0] = 3701.0
                return True
            with patch.object(g.os, 'geteuid', return_value=0), patch.object(g, 'execute_action') as execute:
                with self.assertRaises(ValueError):
                    g.apply_plan(plan['id'], self.cfg, self.directory, confirm=confirm)
                execute.assert_not_called()

    def test_concurrent_confirmation_is_locked(self):
        plan = self.plan()
        def confirm(_):
            with self.assertRaises(BlockingIOError):
                g.apply_plan(plan['id'], self.cfg, self.directory, confirm=lambda p: True)
            return True
        with patch.object(g.os, 'geteuid', return_value=0), patch.object(g, 'execute_action') as execute:
            g.apply_plan(plan['id'], self.cfg, self.directory, confirm=confirm)
            self.assertEqual(execute.call_count, 1)

    def test_http_handler_rejects_missing_or_wrong_token_before_dispatch(self):
        for header in ('', 'Bearer invalid'):
            handler = g.Handler.__new__(g.Handler)
            handler.headers = {'Authorization': header}
            gateway = SimpleNamespace(config={'proxy_token': 'limited'}, dispatch=lambda *a: self.fail('unauthorized dispatch'))
            handler.server = SimpleNamespace(gateway=gateway)
            with patch.object(handler, 'send_error') as error:
                handler.handle_request()
                error.assert_called_once_with(401)

    def test_upstream_delete_uses_only_fixed_rpc_and_exact_id(self):
        self.upstream.return_value = (b'[{"result":{"data":{"json":null}}}]', 'application/json')
        g.execute_action(self.cfg, {'operation': 'delete', 'bookmark_id': 'article1'})
        args = self.upstream.call_args.args
        self.assertEqual(args[1:3], ('POST', '/api/trpc/bookmarks.deleteBookmark?batch=1'))
        self.assertEqual(json.loads(args[3]), {'0': {'json': {'bookmarkId': 'article1'}}})
        self.upstream.return_value = (b'[{"error":{"json":{"message":"failed"}}}]', 'application/json')
        with self.assertRaises(ValueError):
            g.execute_action(self.cfg, {'operation': 'delete', 'bookmark_id': 'article1'})


class MigrationTests(unittest.TestCase):
    def test_raw_key_moves_out_of_runtime_and_dotenv_and_other_connections_remain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); runtime = root / 'connections.json'; config = root / 'root.json'; env = root / '.env'
            raw = 'ak2_fixture_original123'
            runtime.write_text(json.dumps({'karakeep': {'url': 'https://example.invalid', 'key': raw}, 'plane': {'key': 'unchanged'}}))
            env.write_text('URL=https://example.invalid\nAPI_KEY=' + raw + '\nOTHER=preserved\n')
            with patch.object(g.os, 'geteuid', return_value=0):
                first = g.configure_root(config, runtime, env, owner=(os.getuid(), os.getgid()))
                second = g.configure_root(config, runtime, env, owner=(os.getuid(), os.getgid()))
            self.assertEqual(first, second)
            self.assertEqual(json.loads(runtime.read_text())['plane']['key'], 'unchanged')
            self.assertNotIn(raw, runtime.read_text()); self.assertNotIn(raw, env.read_text())
            self.assertIn(raw, config.read_text()); self.assertIn('OTHER=preserved', env.read_text())
            self.assertTrue(json.loads(runtime.read_text())['karakeep']['managed_proxy'])
            self.assertEqual(config.stat().st_mode & 0o777, 0o640)

    def test_ai_settings_cannot_replace_existing_operator_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); runtime = root / 'connections.json'; config = root / 'root.json'; env = root / '.env'
            protected = {'url': 'https://example.invalid', 'key': 'ak2_fixture_original123', 'proxy_token': 'ak2_proxy_limited'}
            config.write_text(json.dumps(protected))
            runtime.write_text(json.dumps({'karakeep': {'url': 'https://other.invalid', 'key': 'ak2_proxy_limited'}}))
            with patch.object(g.os, 'geteuid', return_value=0):
                with self.assertRaises(ValueError):
                    g.configure_root(config, runtime, env, owner=(os.getuid(), os.getgid()))
            self.assertEqual(json.loads(config.read_text()), protected)

    def test_root_migration_never_reads_secrets_through_runtime_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); secret = root / 'private.json'; runtime = root / 'connections.json'
            secret.write_text('{"key":"must-not-be-copied"}'); runtime.symlink_to(secret)
            with patch.object(g.os, 'geteuid', return_value=0):
                with self.assertRaises(OSError):
                    g.configure_root(root / 'root.json', runtime, root / '.env', owner=(os.getuid(), os.getgid()))
            self.assertEqual(secret.read_text(), '{"key":"must-not-be-copied"}')
            directory = root / 'real'; directory.mkdir(); link = root / 'linked'; link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(OSError):
                g.write_user_file(link / 'unsafe', 'content', (os.getuid(), os.getgid()))
            self.assertFalse((directory / 'unsafe').exists())

    def test_new_runtime_file_is_private_and_owned_by_ai_user(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); runtime = root / 'connections.json'
            config = {'url': 'https://example.invalid', 'key': 'ak2_fixture_original123', 'proxy_token': 'ak2_proxy_limited'}
            g.write_runtime(config, runtime, root / '.env', owner=(os.getuid(), os.getgid()))
            self.assertEqual(runtime.stat().st_uid, os.getuid())
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(config['key'], runtime.read_text())

    def test_retired_write_is_not_advertised_or_executable(self):
        names = {x['name'] for x in t.specs()}
        self.assertNotIn('karakeep_write', names)
        self.assertTrue({'karakeep_create', 'karakeep_tags', 'karakeep_delete_plan', 'karakeep_batch_plan'} <= names)
        with patch.object(t.subprocess, 'run') as execute:
            with self.assertRaises(ValueError): t.invoke('karakeep_write', {'args': ['bookmarks', 'delete', 'id']})
            execute.assert_not_called()

    def test_only_retired_grants_are_revoked_and_other_permissions_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); store = root / 'approvals.json'
            other = {'tool': 'send_email', 'key': 'send_email:recipient', 'scope': 'always'}
            store.write_text(json.dumps({'version': 2, 'grants': [other, {'tool': 'secretary_tools__karakeep_write', 'scope': 'always'}]}))
            self.assertTrue(m.revoke_legacy_grants(store, root / 'backups'))
            self.assertEqual(json.loads(store.read_text())['grants'], [other])
            self.assertFalse(m.revoke_legacy_grants(store, root / 'backups'))

    def test_v1_legacy_grants_are_also_revoked_without_losing_other_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); store = root / 'approvals.json'
            store.write_text(json.dumps(['send_email', 'secretary_tools__karakeep_write']))
            self.assertTrue(m.revoke_legacy_grants(store, root / 'backups'))
            self.assertEqual(json.loads(store.read_text()), ['send_email'])

    def test_legacy_mutating_batches_fail_explicitly_but_dry_run_remains(self):
        for path in ('tools/karakeep/sync_nas_pdfs_to_karakeep.py', 'tools/karakeep/recrawl/recrawl.sh'):
            with self.assertRaises(ValueError): t.check_legacy_access(path, [])
            t.check_legacy_access(path, ['--dry-run'])
        with self.assertRaises(ValueError): t.check_legacy_access('tools/karakeep/recrawl/manage_list.sh', ['sync'])
        t.check_legacy_access('tools/karakeep/recrawl/manage_list.sh', ['status'])

    def test_legacy_full_key_is_not_injected_into_generic_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'connections.json'
            config.write_text(json.dumps({'karakeep': {'url': 'https://example.invalid', 'key': 'raw-key'}}))
            with patch.object(t, 'CONFIG', config):
                with self.assertRaises(ValueError): t.child_env()
