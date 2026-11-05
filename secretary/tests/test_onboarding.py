import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('secretary_onboarding', Path(__file__).parents[1] / 'files/secretary.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class CodingReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'; self.bins = Path(self.temp.name) / 'bin'
        self.home.mkdir(); self.bins.mkdir()

    def states(self):
        return {key: state for key, state, _ in s.coding_readiness(self.home, self.bins)}

    def test_missing_tools_are_not_reported_as_login_failures(self):
        self.assertEqual(self.states(), {'codex': 'missing', 'dsh-model': 'missing'})

    def test_codex_status_is_hidden_and_timeout_is_unknown(self):
        (self.bins / 'secretary-codex').touch()
        with patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(self.states()['codex'], 'ready')
            self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs['stderr'], subprocess.DEVNULL)
        with patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            self.assertEqual(self.states()['codex'], 'pending')
        with patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=2)):
            self.assertEqual(self.states()['codex'], 'unknown')
        with patch.object(s.subprocess, 'run', side_effect=subprocess.TimeoutExpired('codex', 10)):
            self.assertEqual(self.states()['codex'], 'unknown')

    def test_dsh_uses_active_provider_record_not_any_credential_file(self):
        (self.bins / 'secretary-dsh').touch()
        profile = self.home / '.dsh/profiles/web/cordis.patch.yml'
        profile.parent.mkdir(parents=True)
        profile.write_text('- id: agent-default-model\n  config: {provider: ollama-cloud, model: sample}\n')
        creds = self.home / '.dsh/.credentials.yaml'
        creds.write_text('version: 1\nrecords:\n  llm-pi-ai/another-provider: {kind: api-key, key: PRIVATE}\n')
        self.assertEqual(self.states()['dsh-model'], 'pending')
        creds.write_text('version: 1\nrecords:\n  llm-pi-ai/ollama-cloud: {kind: api-key, key: PRIVATE}\n')
        self.assertEqual(self.states()['dsh-model'], 'ready')
        profile.write_text('- id: agent-default-model\n  config: !!js never_execute_this()\n')
        self.assertEqual(self.states()['dsh-model'], 'unknown')
