#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge managed tools without replacing model credentials, user rules, or unrelated MCPs."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomlkit


def migrate(path, backups):
    path, backups = Path(path), Path(backups)
    text = path.read_text()
    doc = tomlkit.parse(text)
    sentinel = doc.setdefault('sentinel', {})
    # Keep explicit shell/send confirmations. Plain sandboxed Python computation uses
    # normal risk assessment; network/environment/filesystem warnings still ask.
    sentinel['always_ask_tools'] = [x for x in sentinel.get('always_ask_tools', []) if x != 'python_execute']
    skills = doc.setdefault('skills', {})
    skills['enabled'] = True
    # This installer owns the dedicated skill directory; custom skills remain there.
    skills['dir'] = '/home/secretary/.nanomuse/skills'
    agent = doc.setdefault('agent', {})
    instructions = str(agent.get('instructions', ''))
    old = '送信や外部データの更新は必ずユーザーに確認してください。'
    replacement = ('ユーザーが依頼した参照・集計・翻訳・新規文書作成は専用ツールで進めてください。'
                   '送信・削除・外部更新は対象範囲を明示し、ツールの承認画面で確認してください。'
                   '既に承認された同じ操作について会話で重複確認しないでください。')
    if old in instructions:
        agent['instructions'] = instructions.replace(old, replacement)
    servers = doc.setdefault('mcp', {}).setdefault('servers', [])
    managed = next((s for s in servers if s.get('name') == 'secretary_tools'), None)
    if managed is None:
        managed = tomlkit.table()
        managed.update(name='secretary_tools', command='/usr/bin/python3',
                       args=['/opt/secretary/secretary-tools.py', 'mcp'], risk='sensitive',
                       reads_private_data=True, egress=True, call_timeout_s=120.0)
        servers.append(managed)
    policies = managed.setdefault('tools', {})
    for name in ('catalog', 'inspect', 'job_status', 'doctor'):
        policies[name] = {'risk': 'safe', 'egress': False}
    for name in ('translate', 'dictionary'):
        policies[name] = {'risk': 'moderate', 'egress': False}
    # A fixed CLI against the configured user's own Karakeep; callers cannot select
    # another endpoint. Egress is mediated here, not arbitrary subprocess networking.
    policies['karakeep_read'] = {'risk': 'moderate', 'egress': False}
    policies['karakeep_write'] = {'risk': 'sensitive', 'egress': False}
    policies['run'] = {'risk': 'sensitive', 'egress': True}
    rendered = tomlkit.dumps(doc)
    if rendered == text:
        return False
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='tools-config-', dir=backups))
    shutil.copy2(path, folder / 'config.toml')
    metadata = path.stat()
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(rendered)
        os.chmod(temporary, metadata.st_mode & 0o777)
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


if __name__ == '__main__':
    changed = migrate('/home/secretary/.nanomuse/config.toml', '/var/backups/secretary')
    print('NanoMuse tools configuration:', 'updated (backup saved)' if changed else 'unchanged')
