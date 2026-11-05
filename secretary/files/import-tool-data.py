#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stream one manifest-checked data archive into the container without replacing files."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import sys
import tarfile
import tempfile

ROOT = Path('/srv/secretary/karakeep-tool')


def import_stream(stream, root=ROOT, uid=None, gid=None):
    """Archive starts with manifest.json, followed only by data/<repository-relative-path>."""
    count = 0
    root = Path(root).resolve()
    with tarfile.open(fileobj=stream, mode='r|*') as archive:
        members = iter(archive)
        first = next(members, None)
        if first is None or first.name != 'manifest.json' or not first.isfile() or first.size > 64 * 1024 * 1024:
            raise ValueError('archive must start with manifest.json')
        manifest = json.load(archive.extractfile(first))
        expected = {}
        for item in manifest:
            name = item['path']
            parts = Path(name).parts
            if not parts or Path(name).is_absolute() or '..' in parts or any(p.startswith('.') for p in parts):
                raise ValueError('invalid manifest path')
            if Path(name).suffix in {'.py', '.sh', '.js', '.swift', '.java'}:
                raise ValueError('source code is not data')
            path = (root / name).resolve()
            if not path.is_relative_to(root) or path == root:
                raise ValueError('path escapes data root')
            expected['data/' + name] = item
        for member in members:
            if member.isdir():
                continue
            if not member.isfile() or member.name not in expected:
                raise ValueError('unexpected archive entry: ' + member.name)
            item = expected.pop(member.name)
            if member.size != item['size']:
                raise ValueError('size mismatch: ' + item['path'])
            target = (root / item['path']).resolve()
            if not target.is_relative_to(root):
                raise ValueError('symlink escapes root')
            missing = []
            parent = target.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                parent.mkdir(mode=0o700)
                if uid is not None:
                    os.chown(parent, uid, gid)
            # Never overwrite: matching existing files are a successful resume, a
            # difference stops the import and leaves both originals intact.
            if target.exists():
                digest = hashlib.sha256()
                with target.open('rb') as existing:
                    for block in iter(lambda: existing.read(4 * 1024 * 1024), b''):
                        digest.update(block)
                if digest.hexdigest() != item['sha256']:
                    raise ValueError('existing file conflicts: ' + item['path'])
                # Consume and verify the archive even for an already imported file.
            fd, temporary = tempfile.mkstemp(dir=target.parent)
            try:
                digest = hashlib.sha256()
                with os.fdopen(fd, 'wb') as output, archive.extractfile(member) as source:
                    for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                        digest.update(block)
                        output.write(block)
                if digest.hexdigest() != item['sha256']:
                    raise ValueError('checksum mismatch: ' + item['path'])
                os.chmod(temporary, 0o600)
                if uid is not None:
                    os.chown(temporary, uid, gid)
                if not target.exists():
                    # Atomic exclusive installation, including a race with another importer.
                    os.link(temporary, target)
                count += 1
            finally:
                os.unlink(temporary)
        if expected:
            raise ValueError('archive incomplete: ' + str(len(expected)) + ' files missing')
    return count


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('run through incus exec as root')
    user = pwd.getpwnam('secretary')
    count = import_stream(sys.stdin.buffer, uid=user.pw_uid, gid=user.pw_gid)
    # Only local data trees; source code and the Git checkout keep root ownership.
    print('Verified imported files:', count)
