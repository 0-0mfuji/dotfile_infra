#!/usr/bin/env python3
"""Promote the trial workspace, retaining both originals in a private backup."""
import os
from pathlib import Path
import pwd
import re
import shutil
import tempfile


def migrate(documents, trial, config, backups):
    documents, trial, config, backups = map(Path, (documents, trial, config, backups))
    documents.mkdir(parents=True, exist_ok=True)
    backup = None
    if trial.exists() and not trial.is_symlink():
        backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = Path(tempfile.mkdtemp(prefix='nanomuse-migration-', dir=backups))
        backup.chmod(0o700)
        shutil.copytree(documents, backup / 'documents-before', symlinks=True)
        shutil.copy2(config, backup / 'config.toml')
        # Refuse symlinks rather than following them during a merge.
        sources = sorted(trial.rglob('*'))
        for source in sources:
            rel = source.relative_to(trial)
            if any(part.startswith('.silverbullet') for part in rel.parts):
                continue
            target = documents / rel
            if source.is_symlink() or target.is_symlink():
                raise ValueError('文書内のsymlinkを手動確認してください: ' + str(rel))
            if target.exists() and source.is_dir() != target.is_dir():
                raise ValueError('文書の種類が衝突しています: ' + str(rel))
        for source in sources:
            rel = source.relative_to(trial)
            if any(part.startswith('.silverbullet') for part in rel.parts):
                continue
            target = documents / rel
            if source.is_dir():
                target.mkdir(exist_ok=True)
                target.chmod(0o2770)
            elif source.is_file():
                shutil.copy2(source, target)
                target.chmod(0o660)
        shutil.move(str(trial), str(backup / 'nanomuse-workspace-before'))
    if not trial.exists():
        trial.symlink_to(documents, target_is_directory=True)
    if not trial.is_symlink() or trial.resolve() != documents.resolve():
        raise ValueError('旧workspaceのリンク先が一致しません')
    text = config.read_text()
    lines = text.splitlines(keepends=True)
    in_agent = False
    changed = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith('['):
            in_agent = line.strip() == '[agent]'
        elif in_agent and re.match(r'\s*workspace\s*=', line):
            lines[i] = 'workspace = ' + __import__('json').dumps(str(documents)) + '\n'
            changed = True
    if not changed:
        raise ValueError('config.tomlのagent.workspaceを確認してください')
    metadata = config.stat()
    fd, name = tempfile.mkstemp(dir=config.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(''.join(lines))
        os.chmod(name, metadata.st_mode & 0o777)
        os.chown(name, metadata.st_uid, metadata.st_gid)
        os.replace(name, config)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return backup


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('rootとして実行してください')
    result = migrate('/srv/secretary/documents', '/srv/secretary/nanomuse-workspace',
                     '/home/secretary/.nanomuse/config.toml', '/var/backups/secretary')
    uid = pwd.getpwnam('secretary').pw_uid
    import grp
    gid = grp.getgrnam('secretary-documents').gr_gid
    root = Path('/srv/secretary/documents')
    for path in [root, *root.rglob('*')]:
        if any(part.startswith('.silverbullet') for part in path.relative_to(root).parts):
            continue
        if not path.is_symlink():
            os.chown(path, uid, gid)
    print('文書統合完了。バックアップ:', result or '既に移行済み')
