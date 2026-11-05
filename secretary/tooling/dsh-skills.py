#!/usr/bin/env python3
"""Copy managed skills with DSH tool names; preserve customized destination skills."""
import hashlib
import json
from pathlib import Path
import sys


def sync(source, destination, runtime='DSH'):
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = destination / '.secretary-managed.json'
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    new = {}
    planned = []
    for path in sorted(source.glob('*/SKILL.md')):
        target = destination / path.parent.name / 'SKILL.md'
        text = path.read_text().replace('secretary_tools__', 'mcp__secretary_tools__')
        text = text.replace('NanoMuseの会話モデルはOllama Cloud', runtime + 'で設定した会話モデルは外部サービス')
        text = text.replace('ツールの承認画面', runtime + 'の権限設定とユーザーの指示')
        if target.exists():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if old.get(path.parent.name) != digest:
                raise ValueError('Customized DSH skill was preserved; reconcile first: ' + path.parent.name)
        planned.append((target, text))
        new[path.parent.name] = hashlib.sha256(text.encode()).hexdigest()
    for target, text in planned:
        target.parent.mkdir(exist_ok=True, mode=0o700)
        target.write_text(text)
        target.chmod(0o600)
    stamp.write_text(json.dumps(new, indent=2))
    stamp.chmod(0o600)
    return len(new)


if __name__ == '__main__':
    print('DSH secretary skills:', sync(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'DSH'))
