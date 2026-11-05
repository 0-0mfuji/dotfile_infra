#!/usr/bin/env python3
"""Add secretary MCP connections while preserving native Codex user settings."""
import os
from pathlib import Path
import tempfile
import tomlkit


def configure(path):
    path = Path(path)
    before = path.read_text() if path.exists() else ''
    doc = tomlkit.parse(before)
    doc.setdefault('approval_policy', 'on-request')
    doc.setdefault('sandbox_mode', 'workspace-write')
    servers = doc.setdefault('mcp_servers', {})
    expected = {
        'secretary': {'command': '/usr/bin/python3', 'args': ['/opt/secretary/secretary.py', 'mcp']},
        'secretary_tools': {'command': '/usr/bin/python3', 'args': ['/opt/secretary/secretary-tools.py', 'mcp']},
    }
    for name, settings in expected.items():
        if name in servers:
            if servers[name].get('command') != settings['command'] or list(servers[name].get('args', [])) != settings['args']:
                raise ValueError('Existing Codex MCP definition preserved; reconcile: ' + name)
        else:
            servers[name] = settings
    disabled = servers['secretary_tools'].setdefault('disabled_tools', [])
    if 'karakeep_write' not in disabled:
        disabled.append('karakeep_write')
    after = tomlkit.dumps(doc)
    if before == after:
        return False
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(after)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


if __name__ == '__main__':
    print('Codex secretary MCP config updated:', configure(Path.home() / '.codex/config.toml'))
